from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.db.database import get_db
from web.backend.db.models import GlossaryEntry, Policy
from web.backend.schemas.novel import GlossaryResponse, PolicyResponse
from web.backend.services.extraction_service import extract_policies_for_novel

router = APIRouter(tags=["policies"])


@router.post("/api/v1/novels/{novel_id}/extract")
async def extract_policies_and_glossary(novel_id: int, background_tasks: BackgroundTasks):
    background_tasks.add_task(extract_policies_for_novel, novel_id)
    return {"status": "Extraction started in background."}


@router.get("/api/v1/novels/{novel_id}/policies", response_model=list[PolicyResponse])
async def list_policies(novel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Policy).where(Policy.novel_id == novel_id).order_by(Policy.confidence.desc())
    )
    return result.scalars().all()


@router.get("/api/v1/novels/{novel_id}/glossary", response_model=list[GlossaryResponse])
async def list_glossary(novel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GlossaryEntry)
        .where(GlossaryEntry.novel_id == novel_id)
        .order_by(GlossaryEntry.canonical)
    )
    return result.scalars().all()
