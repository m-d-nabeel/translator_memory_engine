import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select, update

from web.backend.db.database import async_session
from web.backend.db.models import Chapter


async def migrate():
    async with async_session() as session:
        # Find chapters that are pending
        result = await session.execute(select(Chapter).where(Chapter.status == "pending"))
        chapters = result.scalars().all()

        if not chapters:
            print("No pending chapters found.")
            return

        print(f"Found {len(chapters)} pending chapters. Updating to 'unprocessed'...")

        # Update them to unprocessed
        await session.execute(update(Chapter).where(Chapter.status == "pending").values(status="unprocessed"))
        await session.commit()

        print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())
