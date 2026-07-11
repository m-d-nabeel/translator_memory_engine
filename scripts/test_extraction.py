import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from web.backend.services.extraction_service import extract_policies_for_novel


async def test_extract():
    print("Testing policy extraction directly...")
    await extract_policies_for_novel(novel_id=1)
    print("Test finished.")


if __name__ == "__main__":
    asyncio.run(test_extract())
