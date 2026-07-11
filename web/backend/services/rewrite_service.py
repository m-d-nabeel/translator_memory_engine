from __future__ import annotations

import datetime
import json
import logging
import time
import traceback

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.config import settings
from web.backend.db.converters import db_glossary_to_list, db_policies_to_list
from web.backend.db.models import Chapter, GlossaryEntry, Novel, Policy, ProcessingJob

logger = logging.getLogger(__name__)


def _load_known_errors() -> list[dict]:
    path = settings.DATA_DIR / "known_errors.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def rewrite_chapter(
    db: AsyncSession,
    chapter: Chapter,
    do_llm: bool = True,
) -> None:
    chapter.status = "processing"
    start_dt = datetime.datetime.utcnow()
    job = ProcessingJob(
        chapter_id=chapter.id,
        job_type="rewrite",
        status="running",
        started_at=start_dt,
    )
    db.add(job)
    await db.commit()

    start_time = time.monotonic()
    def _ts() -> str:
        ms = int((time.monotonic() - start_time) * 1000)
        secs, millis = divmod(ms, 1000)
        mins, secs = divmod(secs, 60)
        return f"[{mins:02d}:{secs:02d}.{millis:03d}]"

    logs: list[str] = [
        f"{_ts()} Job started: AI Translation Memory Rewrite for Chapter {chapter.chapter_number} ({chapter.source_type.upper()})"
    ]

    try:
        from translator_memory_engine.rewrite.clean import clean_mtl_artifacts
        from translator_memory_engine.rewrite.rewriter import rewrite as core_rewrite

        logs.append(f"{_ts()} Pre-processing: Executing clean_mtl_artifacts to strip formatting noise.")
        cleaned_text = clean_mtl_artifacts(chapter.raw_text)
        orig_len = len(chapter.raw_text)
        clean_len = len(cleaned_text)
        logs.append(f"{_ts()} Cleaned text length: {clean_len} chars (stripped {orig_len - clean_len} noisy characters).")

        # ---------------------------------------------------------------
        # Load policies and glossary from SQLite (single source of truth)
        # ---------------------------------------------------------------
        policies_result = await db.execute(
            select(Policy).where(Policy.novel_id == chapter.novel_id)
        )
        db_policies = policies_result.scalars().all()
        policy_list = db_policies_to_list(db_policies)
        policy_count = len(policy_list)

        glossary_result = await db.execute(
            select(GlossaryEntry).where(GlossaryEntry.novel_id == chapter.novel_id)
        )
        db_glossary = glossary_result.scalars().all()
        glossary_data = db_glossary_to_list(db_glossary)
        glossary_count = len(glossary_data)

        logs.append(
            f"{_ts()} Memory Engine loaded: {policy_count} active AI policies "
            f"& {glossary_count} glossary terms indexed from SQLite DB."
        )

        # The LLM is enabled when the caller requests it AND there are
        # policies available to apply. Previously this checked for a file
        # on disk, which caused a false fast-finish when policies.jsonl
        # was missing — the engine would skip the LLM entirely.
        do_llm_flag = do_llm and policy_count > 0
        logs.append(
            f"{_ts()} Executing translator_memory_engine pipeline "
            f"(deterministic pre-pass + {'LLM contextual polish' if do_llm_flag else 'deterministic only'})..."
        )

        result = core_rewrite(
            text=cleaned_text,
            policies=policy_list,
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
            api_key_env=settings.LLM_API_KEY_ENV,
            do_llm=do_llm_flag,
            glossary=glossary_data,
        )

        det_count = result.get("deterministic_count", 0)
        prm_count = result.get("prompted_count", 0)
        mode = result.get("mode", "unknown")

        logs.append(f"{_ts()} Deterministic pre-pass complete: {det_count} exact term/entity rules matched & enforced.")
        if do_llm_flag:
            logs.append(
                f"{_ts()} Contextual LLM rewrite complete: {prm_count} semantic context "
                f"corrections applied via {settings.LLM_MODEL}."
            )

        chapter.refined_text = (
            result.get("rewritten_text")
            or result.get("prepassed_text", cleaned_text)
        )
        chapter.status = "completed"
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        chapter.processing_time_ms = elapsed_ms

        logs.append(f"{_ts()} Chapter {chapter.chapter_number} refinement completed successfully in {elapsed_ms} ms!")

        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        job.result_summary = json.dumps({
            "mode": mode,
            "deterministic_count": det_count,
            "prompted_count": prm_count,
            "processing_time_ms": elapsed_ms,
            "logs": logs,
        })

    except Exception as e:
        logger.error("Rewrite failed for chapter %d: %s", chapter.id, traceback.format_exc())
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logs.append(f"{_ts()} ERROR during AI rewrite: {str(e)}")
        chapter.status = "failed"
        chapter.error_message = str(e)
        job.status = "failed"
        job.completed_at = datetime.datetime.utcnow()
        job.error_message = str(e)
        job.result_summary = json.dumps({
            "mode": "failed",
            "processing_time_ms": elapsed_ms,
            "logs": logs,
        })

    await db.commit()


async def extract_policies(
    db: AsyncSession,
    novel_id: int,
) -> None:
    novel_result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = novel_result.scalar_one_or_none()
    if not novel:
        raise ValueError(f"Novel {novel_id} not found")

    chapters_result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == novel_id,
            Chapter.source_type == "original",
        )
    )
    chapters = chapters_result.scalars().all()
    if not chapters:
        raise ValueError("No original chapters found for extraction")

    from translator_memory_engine.extract import extract_signals
    from translator_memory_engine.policy.miner import mine_policies

    corpus_chapters = []
    for ch in chapters:
        corpus_chapters.append({
            "text": ch.raw_text,
            "chapter": ch.chapter_number,
        })

    signals = extract_signals(corpus_chapters)
    policies = mine_policies(signals, total_chapters=len(chapters))

    # ---------------------------------------------------------------
    # Clear old policies for this novel, then write new ones to SQLite
    # ---------------------------------------------------------------
    from sqlalchemy import delete as sql_delete
    await db.execute(
        sql_delete(Policy).where(Policy.novel_id == novel_id)
    )

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
            applies=p.applies,
            scores=json.dumps(p.scores) if p.scores else None,
            category=p.category or None,
            note=p.note or None,
            needs_review=str(p.needs_review).lower(),
            llm_rejected=str(p.llm_rejected).lower(),
            contexts=json.dumps(p.contexts) if p.contexts else None,
        )
        db.add(db_policy)

    await db.commit()
