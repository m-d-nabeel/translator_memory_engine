import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select

from web.backend.db.database import async_session
from web.backend.db.models import Chapter, GlossaryEntry, Policy


async def check():
    async with async_session() as session:
        # Check Chapters
        ch_res = await session.execute(select(Chapter))
        chapters = ch_res.scalars().all()
        print(f"Total Chapters: {len(chapters)}")
        for ch in chapters[:3]:
            print(f"  {ch.chapter_number} ({ch.source_type}): status={ch.status}, length={len(ch.raw_text)}")

        # Check Policies
        pol_res = await session.execute(select(Policy))
        policies = pol_res.scalars().all()
        print(f"\nTotal Policies: {len(policies)}")
        for p in policies[:3]:
            print(f"  [{p.type}] {p.trigger} -> {p.action}")
            print(f"    match_forms: {p.match_forms}")

        # Check Glossary
        glos_res = await session.execute(select(GlossaryEntry))
        glossary = glos_res.scalars().all()
        print(f"\nTotal Glossary Entries: {len(glossary)}")
        for g in glossary[:3]:
            print(f"  {g.canonical} (aliases: {g.aliases})")


if __name__ == "__main__":
    asyncio.run(check())
