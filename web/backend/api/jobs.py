from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from web.backend.db.database import get_db
from web.backend.db.models import ProcessingJob
from web.backend.schemas.novel import JobResponse

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/chapter/{chapter_id}", response_model=list[JobResponse])
async def list_chapter_jobs(chapter_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ProcessingJob)
        .options(selectinload(ProcessingJob.chapter))
        .where(ProcessingJob.chapter_id == chapter_id)
        .order_by(ProcessingJob.id.desc())
        .limit(30)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/novel/{novel_id}", response_model=list[JobResponse])
async def list_novel_jobs(novel_id: int, db: AsyncSession = Depends(get_db)):
    from web.backend.db.models import Chapter

    stmt = (
        select(ProcessingJob)
        .join(Chapter, ProcessingJob.chapter_id == Chapter.id)
        .options(selectinload(ProcessingJob.chapter))
        .where(Chapter.novel_id == novel_id)
        .order_by(ProcessingJob.id.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProcessingJob)
        .options(selectinload(ProcessingJob.chapter))
        .where(ProcessingJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
