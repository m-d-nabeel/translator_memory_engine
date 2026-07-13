from __future__ import annotations

import asyncio
import datetime
import json
import logging
import time
import traceback
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.config import settings
from web.backend.db.converters import db_glossary_to_list, db_policies_to_list
from web.backend.db.models import Chapter, GlossaryEntry, Novel, Policy, ProcessingJob, StyleSnippet

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
    chapter.status = "cleaning"
    start_dt = datetime.datetime.utcnow()
    job = ProcessingJob(
        chapter_id=chapter.id,
        job_type="rewrite",
        status="running: cleaning",
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

        if chapter.source_type != "mtl":
            raise ValueError("Only MTL chapters can be rewritten; original chapters are reference material.")

        logs.append(f"{_ts()} Pre-processing: Executing clean_mtl_artifacts to strip formatting noise.")
        cleaned_text = clean_mtl_artifacts(chapter.raw_text)
        orig_len = len(chapter.raw_text)
        clean_len = len(cleaned_text)
        logs.append(
            f"{_ts()} Cleaned text length: {clean_len} chars (stripped {orig_len - clean_len} noisy characters)."
        )

        # ---------------------------------------------------------------
        # Load policies and glossary from SQLite (single source of truth)
        # ---------------------------------------------------------------
        policies_result = await db.execute(select(Policy).where(Policy.novel_id == chapter.novel_id))
        db_policies = policies_result.scalars().all()
        verified_policies = [
            policy
            for policy in db_policies
            if (policy.needs_review or "false").lower() != "true" and (policy.llm_rejected or "false").lower() != "true"
        ]
        policy_list = db_policies_to_list(verified_policies)
        policy_count = len(policy_list)

        glossary_result = await db.execute(select(GlossaryEntry).where(GlossaryEntry.novel_id == chapter.novel_id))
        db_glossary = glossary_result.scalars().all()
        verified_canonicals = {policy.trigger.lower() for policy in verified_policies}
        glossary_data = [
            entry
            for entry in db_glossary_to_list(db_glossary)
            if entry.get("canonical", "").lower() in verified_canonicals
        ]
        glossary_count = len(glossary_data)

        # The caller controls whether an LLM is used. A style profile or a
        # reference must never override an explicit deterministic-only run.
        do_llm_flag = do_llm

        reference_result = await db.execute(
            select(Chapter)
            .where(
                Chapter.novel_id == chapter.novel_id,
                Chapter.chapter_number == chapter.chapter_number,
                Chapter.source_type == "original",
            )
            .limit(1)
        )
        reference_chapter = reference_result.scalar_one_or_none()
        reference_text = reference_chapter.raw_text if reference_chapter else None

        snippets_result = await db.execute(select(StyleSnippet).where(StyleSnippet.novel_id == chapter.novel_id))
        style_candidates = [s.text for s in snippets_result.scalars().all()]
        generated_style_count = 0
        if reference_text is None:
            # For MTL-only chapters, derive a compact voice bank from prior
            # trusted chapters when the user has not curated enough snippets.
            originals_result = await db.execute(
                select(Chapter)
                .where(
                    Chapter.novel_id == chapter.novel_id,
                    Chapter.source_type == "original",
                    Chapter.chapter_number < chapter.chapter_number,
                )
                .order_by(Chapter.chapter_number)
            )
            original_texts = [ch.raw_text for ch in originals_result.scalars().all() if ch.raw_text.strip()]
            if original_texts:
                from translator_memory_engine.memory.style_bank import build_style_bank

                generated = build_style_bank(original_texts, per_chapter=1, max_chars=300, include_stats=False)
                generated_style_count = len(generated)
                style_candidates.extend(generated)

        # Avoid a prompt stuffed with unrelated scenes. Retrieval is lexical and
        # scene-adjacent; it never controls document chunk boundaries.
        style_profile: list[str] = []
        if reference_text is None and style_candidates:
            from translator_memory_engine.memory.style_bank import retrieve_style_excerpts

            style_profile = retrieve_style_excerpts(cleaned_text, list(dict.fromkeys(style_candidates)), k=4)

        logs.append(
            f"{_ts()} Memory Engine loaded: {policy_count} active AI policies, "
            f"{glossary_count} glossary terms, {len(style_profile)} selected style snippets "
            f"({generated_style_count} derived from trusted chapters)."
        )

        previous_result = await db.execute(
            select(Chapter)
            .where(
                Chapter.novel_id == chapter.novel_id,
                Chapter.source_type == "mtl",
                Chapter.chapter_number < chapter.chapter_number,
                Chapter.status == "completed",
                Chapter.refined_text.is_not(None),
            )
            .order_by(Chapter.chapter_number.desc())
            .limit(1)
        )
        previous_chapter = previous_result.scalar_one_or_none()
        previous_tail = previous_chapter.refined_text if previous_chapter else None
        logs.append(
            f"{_ts()} Executing translator_memory_engine pipeline "
            f"(deterministic pre-pass + {'LLM contextual polish' if do_llm_flag else 'deterministic only'})..."
        )
        if do_llm_flag:
            chapter.status = "rewriting"
            job.status = "running: rewriting"
        else:
            chapter.status = "applying_rules"
            job.status = "running: applying_rules"
        await db.commit()

        # The core rewriter makes synchronous HTTP calls. Keep them off the
        # FastAPI event loop so status polling and other chapters remain usable.
        result = await asyncio.to_thread(
            core_rewrite,
            text=cleaned_text,
            policies=policy_list,
            model=settings.REWRITE_LLM_MODEL,
            base_url=settings.REWRITE_LLM_BASE_URL,
            api_key_env=settings.REWRITE_LLM_API_KEY_ENV,
            do_llm=do_llm_flag,
            reference_text=reference_text,
            style_profile=style_profile if style_profile else None,
            glossary=glossary_data,
            previous_tail=previous_tail,
            temperature=settings.REWRITE_LLM_TEMPERATURE,
            max_output_tokens=settings.REWRITE_LLM_MAX_TOKENS,
            enable_alias_bridging=settings.ENABLE_ALIAS_BRIDGING,
        )

        det_count = result.get("deterministic_count", 0)
        prm_count = result.get("prompted_count", 0)
        mode = result.get("mode", "unknown")
        trace = result.get("trace", [])

        logs.append(f"{_ts()} Deterministic pre-pass complete: {det_count} exact term/entity rules matched & enforced.")

        # Run Entity Consistency Validator
        chapter.status = "validating"
        job.status = "running: validating"
        await db.commit()

        from translator_memory_engine.validate.entity import validate_entity_consistency

        warnings = validate_entity_consistency(result.get("rewritten_text") or "", trace)
        warnings.extend(result.get("integrity_warnings", []))
        warnings = sorted(set(warnings))
        if warnings:
            chapter.warnings = json.dumps(warnings)
            logs.append(f"{_ts()} Validation warnings: {len(warnings)} entity consistency issues detected.")
        else:
            chapter.warnings = None
        if do_llm_flag:
            logs.append(
                f"{_ts()} Contextual LLM rewrite complete: {prm_count} semantic context "
                f"corrections applied via {settings.REWRITE_LLM_MODEL}."
            )

        chapter.refined_text = result.get("rewritten_text") or result.get("prepassed_text", cleaned_text)
        chapter.status = "completed"
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        chapter.processing_time_ms = elapsed_ms

        logs.append(f"{_ts()} Chapter {chapter.chapter_number} refinement completed successfully in {elapsed_ms} ms!")

        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        job.result_summary = json.dumps(
            {
                "mode": mode,
                "deterministic_count": det_count,
                "prompted_count": prm_count,
                "processing_time_ms": elapsed_ms,
                "logs": logs,
            }
        )

    except Exception as e:
        logger.error("Rewrite failed for chapter %d: %s", chapter.id, traceback.format_exc())
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logs.append(f"{_ts()} ERROR during AI rewrite: {str(e)}")
        chapter.status = "failed"
        chapter.error_message = str(e)
        job.status = "failed"
        job.completed_at = datetime.datetime.utcnow()
        job.error_message = str(e)
        job.result_summary = json.dumps(
            {
                "mode": "failed",
                "processing_time_ms": elapsed_ms,
                "logs": logs,
            }
        )

    await db.commit()

    # Launch asynchronous lore extraction (Phase 2)
    if chapter.status == "completed" and chapter.refined_text:
        from web.backend.db.database import async_session

        asyncio.create_task(
            _background_extract_lore(
                chapter_id=chapter.id,
                novel_id=chapter.novel_id,
                chapter_text=chapter.refined_text,
                session_maker=async_session,
            )
        )


async def _background_extract_lore(
    chapter_id: int, novel_id: int, chapter_text: str, session_maker: Any, bypass_review: bool = False
):
    import asyncio
    import json
    import uuid
    from datetime import datetime

    from sqlalchemy import select

    from translator_memory_engine.extract.lore import extract_chapter_lore
    from web.backend.db.models import Chapter, GlossaryEntry, Policy, ProcessingJob

    job_id = None
    try:
        async with session_maker() as db:
            chapter_res = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
            ch = chapter_res.scalar_one_or_none()
            if ch:
                ch.status = "extracting_lore"
                job = ProcessingJob(
                    chapter_id=chapter_id,
                    job_type="extract_lore",
                    status="running",
                    started_at=datetime.utcnow(),
                )
                db.add(job)
                await db.commit()
                await db.refresh(job)
                job_id = job.id

        # Run the synchronous LLM extraction in a thread pool to avoid blocking the event loop
        lore_data = await asyncio.to_thread(
            extract_chapter_lore,
            chapter_text,
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
            api_key_env=settings.LLM_API_KEY_ENV,
        )

        async with session_maker() as db:
            # 1. Save chapter summary
            chapter_result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
            chapter = chapter_result.scalar_one_or_none()
            if chapter and lore_data.get("chapter_summary"):
                chapter.summary = lore_data["chapter_summary"]

            # 2. Process character lore
            characters = lore_data.get("characters", [])
            for char in characters:
                name = char.get("name")
                if not name:
                    continue

                # Find existing entry
                entry_result = await db.execute(
                    select(GlossaryEntry)
                    .where(GlossaryEntry.novel_id == novel_id)
                    .where(GlossaryEntry.canonical == name)
                )
                entry = entry_result.scalar_one_or_none()

                new_meta = {
                    "gender": char.get("gender", ""),
                    "race_or_identity": char.get("race_or_identity", ""),
                    "speech_style": char.get("speech_style", ""),
                    "background": char.get("background", ""),
                }

                if not entry:
                    # New Entity -> insert directly to Glossary + add to Policy Store
                    # Check for policy as well
                    policy_result = await db.execute(
                        select(Policy).where(Policy.novel_id == novel_id).where(Policy.trigger == name)
                    )
                    policy = policy_result.scalar_one_or_none()

                    meta_to_save = dict(new_meta)
                    if bypass_review:
                        pass  # no review flag
                    else:
                        meta_to_save["needs_review"] = True

                    # Extract valid context evidence
                    evidence_list = []
                    intro_snippet = char.get("introduction_snippet") or char.get("background")
                    if intro_snippet and isinstance(intro_snippet, str) and len(intro_snippet.strip()) > 3:
                        for para in chapter_text.split("\n"):
                            para_str = para.strip()
                            if not para_str:
                                continue
                            if name in para_str or (
                                intro_snippet[:15] in para_str
                                if len(intro_snippet) >= 15
                                else intro_snippet in para_str
                            ):
                                evidence_list.append(para_str)
                                if len(evidence_list) >= 3:
                                    break
                        if not evidence_list:
                            valid_intro = intro_snippet.strip()
                            if not valid_intro.endswith((".", "!", "?", '"', "'")):
                                valid_intro += "."
                            evidence_list.append(valid_intro)

                    if not entry:
                        new_entry = GlossaryEntry(
                            novel_id=novel_id,
                            canonical=name,
                            aliases="[]",
                            entity_type="Character",
                            confidence=0.9,
                            metadata_json=json.dumps(meta_to_save),
                            evidence_contexts=json.dumps(evidence_list) if evidence_list else None,
                        )
                        db.add(new_entry)

                    if not policy:
                        new_policy = Policy(
                            novel_id=novel_id,
                            policy_id=int(uuid.uuid4().int >> 96),
                            type="entity",
                            trigger=name,
                            match_forms=json.dumps([name]),
                            action=json.dumps(name),
                            confidence=0.9,
                            evidence_chapters=json.dumps([chapter.chapter_number if chapter else 1]),
                            applies="deterministic",
                            category="Character",
                            note=f"Extracted from Chapter {chapter.chapter_number if chapter else 1} Lore",
                            needs_review="false" if bypass_review else "true",
                            llm_rejected="false",
                            contexts=json.dumps(evidence_list) if evidence_list else None,
                            metadata_json=json.dumps(meta_to_save),
                        )
                        db.add(new_policy)
                else:
                    # Existing Entity -> Update Metadata
                    policy_result = await db.execute(
                        select(Policy).where(Policy.novel_id == novel_id).where(Policy.trigger == name)
                    )
                    policy = policy_result.scalar_one_or_none()

                    if not entry.evidence_contexts:
                        evidence_list = []
                        intro_snippet = char.get("introduction_snippet") or char.get("background")
                        if intro_snippet and isinstance(intro_snippet, str) and len(intro_snippet.strip()) > 3:
                            for para in chapter_text.split("\n"):
                                para_str = para.strip()
                                if not para_str:
                                    continue
                                if name in para_str or (
                                    intro_snippet[:15] in para_str
                                    if len(intro_snippet) >= 15
                                    else intro_snippet in para_str
                                ):
                                    evidence_list.append(para_str)
                                    if len(evidence_list) >= 3:
                                        break
                            if not evidence_list:
                                valid_intro = intro_snippet.strip()
                                if not valid_intro.endswith((".", "!", "?", '"', "'")):
                                    valid_intro += "."
                                evidence_list.append(valid_intro)
                            entry.evidence_contexts = json.dumps(evidence_list)
                            if policy:
                                policy.contexts = json.dumps(evidence_list)

                    existing_meta = {}
                    if entry.metadata_json:
                        try:
                            existing_meta = json.loads(entry.metadata_json)
                        except Exception:
                            pass

                    is_verified = (policy.needs_review == "false") if policy else False

                    if bypass_review:
                        # Bypass review = True: directly overwrite and auto-verify
                        existing_meta.update(new_meta)
                        existing_meta.pop("proposed_updates", None)
                        entry.metadata_json = json.dumps(existing_meta)
                        if policy:
                            policy.metadata_json = json.dumps(existing_meta)
                            policy.needs_review = "false"
                    elif not is_verified:
                        # Needs review = True: LLM can overwrite and refine
                        existing_meta.update(new_meta)
                        entry.metadata_json = json.dumps(existing_meta)
                        if policy:
                            policy.metadata_json = json.dumps(existing_meta)
                    else:
                        # Verified (needs_review = false): Gated Update for Character Arcs
                        proposed = {}
                        if new_meta.get("speech_style") and new_meta["speech_style"] != existing_meta.get(
                            "speech_style"
                        ):
                            proposed["speech_style"] = new_meta["speech_style"]
                        if new_meta.get("race_or_identity") and new_meta["race_or_identity"] != existing_meta.get(
                            "race_or_identity"
                        ):
                            proposed["race_or_identity"] = new_meta["race_or_identity"]

                        if proposed:
                            existing_meta["proposed_updates"] = proposed
                            entry.metadata_json = json.dumps(existing_meta)
                            if policy:
                                policy.metadata_json = json.dumps(existing_meta)
                                policy.needs_review = "true"  # Flip for review

            if chapter and chapter.status == "extracting_lore":
                chapter.status = "completed" if chapter.refined_text else "unprocessed"
            if job_id:
                job_res = await db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
                job = job_res.scalar_one_or_none()
                if job:
                    job.status = "completed"
                    job.completed_at = datetime.utcnow()
                    job.result_summary = json.dumps({"characters_extracted": len(characters)})
            await db.commit()
    except Exception as e:
        logger.error(f"Background lore extraction failed for chapter {chapter_id}: {e}", exc_info=True)
        try:
            async with session_maker() as db:
                chapter_res = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
                ch = chapter_res.scalar_one_or_none()
                if ch and ch.status == "extracting_lore":
                    ch.status = "completed" if ch.refined_text else "unprocessed"
                if job_id:
                    job_res = await db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
                    job = job_res.scalar_one_or_none()
                    if job:
                        job.status = "failed"
                        job.completed_at = datetime.utcnow()
                        job.error_message = str(e)
                await db.commit()
        except Exception:
            pass


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

    import logging

    from openai import OpenAI
    from starlette.concurrency import run_in_threadpool

    from translator_memory_engine.extract import extract_signals
    from translator_memory_engine.policy.miner import mine_policies

    logger = logging.getLogger(__name__)

    corpus_chapters = []
    for ch in chapters:
        corpus_chapters.append(
            {
                "text": ch.raw_text,
                "chapter": ch.chapter_number,
            }
        )

    signals = await run_in_threadpool(extract_signals, corpus_chapters, source_languages=[novel.source_language])

    # Setup LLM client for semantic verification
    try:
        llm_client = OpenAI(
            base_url=settings.LOCAL_LLM_BASE_URL,
            api_key=settings.LOCAL_LLM_API_KEY,
        )
    except Exception as e:
        logger.warning(f"Could not instantiate OpenAI client for semantic verification: {e}")
        llm_client = None

    policies = await run_in_threadpool(
        mine_policies,
        signals,
        total_chapters=len(chapters),
        llm_client=llm_client,
        llm_model=settings.LOCAL_LLM_MODEL,
    )

    # ---------------------------------------------------------------
    # Clear old policies for this novel, then write new ones to SQLite
    # ---------------------------------------------------------------
    from sqlalchemy import delete as sql_delete

    await db.execute(sql_delete(Policy).where(Policy.novel_id == novel_id))

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


async def extract_lore_for_chapters(
    novel_id: int,
    chapter_ids: list[int] | None,
    session_maker: Any,
    only_og_tl: bool = False,
    bypass_review: bool = False,
) -> None:
    import asyncio

    from sqlalchemy import select

    from web.backend.db.models import Chapter

    async with session_maker() as db:
        query = select(Chapter).where(Chapter.novel_id == novel_id)
        if chapter_ids and len(chapter_ids) > 0:
            query = query.where(Chapter.id.in_(chapter_ids))

        result = await db.execute(query.order_by(Chapter.chapter_number))
        chapters = result.scalars().all()

    # Group all retrieved chapters by chapter_number
    by_number: dict[int, list[Chapter]] = {}
    for ch in chapters:
        by_number.setdefault(ch.chapter_number, []).append(ch)

    # Determine tasks to run in exact order
    tasks_to_run = []
    is_explicit_selection = bool(chapter_ids and len(chapter_ids) > 0)

    for num in sorted(by_number.keys()):
        ch_list = by_number[num]

        # If running on All Chapters (no specific chapters chosen), skip if lore already extracted
        if not is_explicit_selection and any(c.summary and c.summary.strip() for c in ch_list):
            logger.info(f"Skipping lore extraction for Ch. {num} (lore/summary already extracted)...")
            continue

        target_ch = None
        target_text = None
        mode_str = ""

        if only_og_tl:
            # Strict OG TL mode: only pick source_type == "original"
            for c in ch_list:
                if c.source_type == "original" and c.raw_text and c.raw_text.strip():
                    target_ch, target_text, mode_str = c, c.raw_text, "Original (OG TL)"
                    break
        else:
            # Strict Priority Order: Original -> Refined -> MTL
            # 1. Original (`source_type == "original"`)
            for c in ch_list:
                if c.source_type == "original" and c.raw_text and c.raw_text.strip():
                    target_ch, target_text, mode_str = c, c.raw_text, "Original (OG TL)"
                    break
            # 2. Refined (`refined_text`)
            if not target_ch:
                for c in ch_list:
                    if c.refined_text and c.refined_text.strip():
                        target_ch, target_text, mode_str = c, c.refined_text, "Refined TL"
                        break
            # 3. MTL (`raw_text` from non-original)
            if not target_ch:
                for c in ch_list:
                    if c.raw_text and c.raw_text.strip():
                        target_ch, target_text, mode_str = c, c.raw_text, "MTL"
                        break

        if target_ch and target_text:
            tasks_to_run.append((target_ch, target_text, mode_str))

    for i, (target_ch, text, mode_str) in enumerate(tasks_to_run):
        logger.info(f"Extracting lore ({mode_str}) for chapter {target_ch.id} (Ch. {target_ch.chapter_number})...")
        await _background_extract_lore(
            target_ch.id, target_ch.novel_id, text, session_maker, bypass_review=bypass_review
        )

        # Add brief pacing between chapter calls to prevent Groq API 429 Too Many Requests
        if i < len(tasks_to_run) - 1:
            await asyncio.sleep(2.5)
