import json
import logging

from sqlalchemy import select

from translator_memory_engine.extract import extract_signals
from translator_memory_engine.memory.store import PolicyStore
from translator_memory_engine.policy.miner import mine_policies
from web.backend.db.database import async_session
from web.backend.db.models import GlossaryEntry, Policy

logger = logging.getLogger(__name__)


async def extract_policies_for_novel(novel_id: int):
    """
    Background task to re-extract policies and glossary entries
    from the original chapters stored in the database.
    """
    job_id = None
    try:
        async with async_session() as session:
            from web.backend.db.models import Chapter, Novel, ProcessingJob
            from datetime import datetime

            # Fetch novel for source language
            novel_result = await session.execute(select(Novel).where(Novel.id == novel_id))
            novel = novel_result.scalar_one_or_none()
            source_language = novel.source_language if novel else "korean"

            # 1. Fetch all original chapters
            result = await session.execute(
                select(Chapter)
                .where(Chapter.novel_id == novel_id)
                .where(Chapter.source_type == "original")
                .order_by(Chapter.chapter_number)
            )
            original_chapters = result.scalars().all()

            if not original_chapters:
                logger.warning(
                    f"No original chapters found for novel {novel_id}. Cannot extract policies."
                )
                return

            first_ch = original_chapters[0]
            job = ProcessingJob(
                chapter_id=first_ch.id,
                job_type="extract_policies",
                status="running",
                started_at=datetime.utcnow(),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

            from translator_memory_engine.models import Chapter as PipelineChapter

            # Format for extract_signals: List[PipelineChapter]
            pipeline_chapters = []
            for ch in original_chapters:
                pipeline_chapters.append(
                    PipelineChapter(
                        chapter=ch.chapter_number,
                        title=f"Chapter {ch.chapter_number}",
                        text=ch.raw_text,
                        paragraphs=[p for p in ch.raw_text.split("\n") if p.strip()],
                    )
                )
            total_chapters = len(pipeline_chapters)
            logger.info(f"Loaded {total_chapters} original chapters for extraction.")

            # 2. Extract signals
            signals = extract_signals(pipeline_chapters, source_languages=[source_language])
            logger.info(f"Extracted {len(signals)} raw signals.")

            # 3. Mine policies
            policies = mine_policies(
                signals,
                total_chapters=total_chapters,
                min_support=2,
                min_confidence=0.4,
                similarity_threshold=0.3,
                confidence_base=0.5,
                confidence_per_occurrence=0.03,
                confidence_cap=0.99,
            )
            logger.info(f"Mined {len(policies)} policies.")

            # 4. Save to DB directly
            # First, clear existing policies and glossary for this novel to regenerate
            await session.execute(Policy.__table__.delete().where(Policy.novel_id == novel_id))
            await session.execute(
                GlossaryEntry.__table__.delete().where(GlossaryEntry.novel_id == novel_id)
            )

            # Since the CLI uses PolicyStore which has its own sync sqlite saving,
            # we will just add them using SQLAlchemy here directly to the unified DB.
            store = PolicyStore()
            for p in policies:
                store.add(p)

            glossary = store.export_glossary()

            # Insert policies
            for p in policies:
                db_policy = Policy(
                    novel_id=novel_id,
                    policy_id=p.id,
                    type=p.type,
                    trigger=p.trigger,
                    match_forms=json.dumps(p.match),
                    action=json.dumps(p.action),
                    confidence=p.confidence,
                    evidence_chapters=json.dumps(p.evidence),
                    applies=getattr(p, "applies", "deterministic"),
                    scores=json.dumps(getattr(p, "scores", {})),
                    category=getattr(p, "category", ""),
                    note=getattr(p, "note", ""),
                    needs_review="true" if getattr(p, "needs_review", False) else "false",
                    llm_rejected="true" if getattr(p, "llm_rejected", False) else "false",
                    contexts=json.dumps(getattr(p, "contexts", [])),
                    metadata_json=json.dumps(p.metadata) if getattr(p, "metadata", None) else None,
                )
                session.add(db_policy)

            # Insert glossary
            for entry in glossary:
                db_entry = GlossaryEntry(
                    novel_id=novel_id,
                    canonical=entry["canonical"],
                    aliases=json.dumps(entry.get("aliases", [])),
                    entity_type=entry.get("type"),
                    confidence=entry.get("confidence"),
                    metadata_json=json.dumps(entry.get("metadata")) if entry.get("metadata") else None,
                )
                session.add(db_entry)

            if job_id:
                job_result = await session.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
                job = job_result.scalar_one_or_none()
                if job:
                    job.status = "completed"
                    job.completed_at = datetime.utcnow()
                    job.result_summary = json.dumps({"policies": len(policies), "glossary": len(glossary)})

            await session.commit()
            logger.info(
                f"Successfully saved {len(policies)} policies and {len(glossary)} glossary entries for novel {novel_id}."
            )

    except Exception as e:
        logger.error(f"Error during policy extraction for novel {novel_id}: {e}", exc_info=True)
        if job_id:
            try:
                async with async_session() as session:
                    from web.backend.db.models import ProcessingJob
                    from datetime import datetime
                    job_result = await session.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
                    job = job_result.scalar_one_or_none()
                    if job:
                        job.status = "failed"
                        job.completed_at = datetime.utcnow()
                        job.error_message = str(e)
                    await session.commit()
            except Exception as err:
                logger.error(f"Failed to mark extraction job as failed: {err}")
