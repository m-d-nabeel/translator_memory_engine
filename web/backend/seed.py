"""Seed the database with existing data from the data/ directory.

Run with:
    uv run python -m web.backend.seed

Idempotent: skips seeding if data already exists, but will import
policies/glossary from JSONL files if the tables are empty for a novel.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _PROJECT_ROOT / "data"

NOVEL_NAME = "Feasting Lord in Another World"
NOVEL_TITLE = "Feasting Lord in Another World"


async def seed() -> None:
    from sqlalchemy import func, select

    from web.backend.db.database import async_session, init_db
    from web.backend.db.models import Chapter, GlossaryEntry, Novel, Policy

    await init_db()

    async with async_session() as db:
        existing = await db.execute(select(Novel).where(Novel.name == NOVEL_NAME))
        novel = existing.scalar_one_or_none()

        if novel is None:
            novel = Novel(
                name=NOVEL_NAME,
                title=NOVEL_TITLE,
                source_language="korean",
            )
            db.add(novel)
            await db.commit()
            await db.refresh(novel)
            logger.info("Created novel: %s (id=%d)", novel.name, novel.id)
        else:
            logger.info("Novel '%s' already exists (id=%d).", NOVEL_NAME, novel.id)

        # -----------------------------------------------------------
        # Idempotent reconciliation: import from JSONL if table is empty
        # -----------------------------------------------------------

        # Policies: import if empty for this novel
        policy_count_result = await db.execute(
            select(func.count()).select_from(Policy).where(Policy.novel_id == novel.id)
        )
        policy_count = policy_count_result.scalar() or 0

        if policy_count == 0:
            policies_file = _DATA_DIR / "policies" / "policies.jsonl"
            if policies_file.exists():
                count = 0
                with open(policies_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        p = json.loads(line)
                        db_policy = Policy(
                            novel_id=novel.id,
                            policy_id=p["id"],
                            type=p["type"],
                            trigger=p["trigger"],
                            match_forms=json.dumps(p.get("match", [])),
                            action=json.dumps(p.get("action", {})),
                            confidence=p.get("confidence", 0.0),
                            evidence_chapters=json.dumps(p.get("evidence", [])),
                            applies=p.get("applies", "deterministic"),
                            scores=json.dumps(p.get("scores", {})) if p.get("scores") else None,
                            category=p.get("category"),
                            note=p.get("note"),
                            needs_review=str(p.get("needs_review", False)).lower(),
                            llm_rejected=str(p.get("llm_rejected", False)).lower(),
                            contexts=json.dumps(p.get("contexts", [])) if p.get("contexts") else None,
                        )
                        db.add(db_policy)
                        count += 1
                await db.commit()
                logger.info("Seeded %d policies from %s", count, policies_file)
            else:
                logger.info("No policies file found at %s, skipping policy seed.", policies_file)
        else:
            logger.info("Policies table already has %d entries, skipping import.", policy_count)

        # Glossary: import if empty for this novel
        glossary_count_result = await db.execute(
            select(func.count()).select_from(GlossaryEntry).where(GlossaryEntry.novel_id == novel.id)
        )
        glossary_count = glossary_count_result.scalar() or 0

        if glossary_count == 0:
            glossary_file = _DATA_DIR / "policies" / "glossary.json"
            if glossary_file.exists():
                with open(glossary_file, encoding="utf-8") as f:
                    glossary_data = json.load(f)
                count = 0
                for entry in glossary_data:
                    db_entry = GlossaryEntry(
                        novel_id=novel.id,
                        canonical=entry["canonical"],
                        aliases=json.dumps(entry.get("aliases", [])),
                        entity_type=entry.get("type"),
                        confidence=entry.get("confidence"),
                    )
                    db.add(db_entry)
                    count += 1
                await db.commit()
                logger.info("Seeded %d glossary entries from %s", count, glossary_file)
            else:
                logger.info("No glossary file found at %s, skipping glossary seed.", glossary_file)
        else:
            logger.info("Glossary table already has %d entries, skipping import.", glossary_count)

        # Chapters: import if empty for this novel
        chapter_count_result = await db.execute(
            select(func.count()).select_from(Chapter).where(Chapter.novel_id == novel.id)
        )
        chapter_count = chapter_count_result.scalar() or 0

        if chapter_count == 0:
            originals_dir = _DATA_DIR / "originals"
            if originals_dir.exists():
                count = 0
                for txt_file in sorted(originals_dir.glob("*.txt")):
                    parts = txt_file.stem.split("-")
                    try:
                        ch_num = int(parts[0])
                    except (ValueError, IndexError):
                        continue
                    text = txt_file.read_text(encoding="utf-8")
                    chapter = Chapter(
                        novel_id=novel.id,
                        chapter_number=ch_num,
                        source_type="original",
                        raw_text=text,
                        status="completed",
                    )
                    db.add(chapter)
                    count += 1
                await db.commit()
                logger.info("Seeded %d original chapters", count)

            mtl_dir = _DATA_DIR / "mtl"
            if mtl_dir.exists():
                count = 0
                for txt_file in sorted(mtl_dir.glob("*.txt")):
                    parts = txt_file.stem.split("-")
                    try:
                        ch_num = int(parts[1])
                    except (ValueError, IndexError):
                        continue
                    text = txt_file.read_text(encoding="utf-8")
                    chapter = Chapter(
                        novel_id=novel.id,
                        chapter_number=ch_num,
                        source_type="mtl",
                        raw_text=text,
                        status="pending",
                    )
                    db.add(chapter)
                    count += 1
                await db.commit()
                logger.info("Seeded %d MTL chapters", count)

            output_dir = _DATA_DIR / "output"
            if output_dir.exists():
                updated = 0
                for txt_file in sorted(output_dir.glob("rewritten_chapter-*.txt")):
                    name = txt_file.stem.replace("rewritten_chapter-", "")
                    try:
                        ch_num = int(name.split("-")[0])
                    except (ValueError, IndexError):
                        continue
                    result = await db.execute(
                        select(Chapter).where(
                            Chapter.novel_id == novel.id,
                            Chapter.chapter_number == ch_num,
                            Chapter.source_type == "mtl",
                        )
                    )
                    chapter = result.scalar_one_or_none()
                    if chapter and not chapter.refined_text:
                        chapter.refined_text = txt_file.read_text(encoding="utf-8")
                        chapter.status = "completed"
                        updated += 1
                await db.commit()
                if updated:
                    logger.info("Updated %d chapters with existing refined text", updated)
        else:
            logger.info("Chapters table already has %d entries, skipping import.", chapter_count)

        logger.info("Seed complete!")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await seed()


if __name__ == "__main__":
    asyncio.run(main())
