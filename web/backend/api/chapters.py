from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.db.database import get_db
from web.backend.db.models import Chapter, Novel
from web.backend.schemas.novel import (
    ChapterCreate,
    ChapterRead,
    ChapterResponse,
    ChapterStatusResponse,
    ProcessRequest,
)

router = APIRouter(tags=["chapters"])


@router.post("/api/v1/novels/{novel_id}/chapters", response_model=ChapterResponse, status_code=201)
async def create_chapter(novel_id: int, body: ChapterCreate, db: AsyncSession = Depends(get_db)):
    novel_result = await db.execute(select(Novel).where(Novel.id == novel_id))
    if not novel_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Novel not found")

    existing = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == novel_id,
            Chapter.chapter_number == body.chapter_number,
            Chapter.source_type == body.source_type,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Chapter {body.chapter_number} ({body.source_type}) already exists",
        )

    chapter = Chapter(
        novel_id=novel_id,
        chapter_number=body.chapter_number,
        source_type=body.source_type,
        raw_text=body.raw_text,
    )
    db.add(chapter)
    await db.commit()
    await db.refresh(chapter)
    return chapter


@router.get("/api/v1/novels/{novel_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(
    novel_id: int,
    source_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Chapter).where(Chapter.novel_id == novel_id)
    if source_type:
        stmt = stmt.where(Chapter.source_type == source_type)
    stmt = stmt.order_by(Chapter.chapter_number, Chapter.source_type)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get(
    "/api/v1/novels/{novel_id}/chapters/{chapter_number}",
    response_model=ChapterResponse,
)
async def get_chapter(
    novel_id: int,
    chapter_number: int,
    source_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Chapter).where(
        Chapter.novel_id == novel_id,
        Chapter.chapter_number == chapter_number,
    )
    if source_type:
        stmt = stmt.where(Chapter.source_type == source_type)
    else:
        stmt = stmt.order_by(Chapter.source_type.desc()).limit(1)
    result = await db.execute(stmt)
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.get("/api/v1/novels/{novel_id}/readable")
async def list_readable_chapters(novel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Chapter)
        .where(
            Chapter.novel_id == novel_id,
            Chapter.refined_text.isnot(None),
        )
        .order_by(Chapter.chapter_number)
    )
    chapters = result.scalars().all()
    return [
        {
            "id": c.id,
            "chapter_number": c.chapter_number,
            "source_type": c.source_type,
            "status": c.status,
        }
        for c in chapters
    ]


@router.get("/api/v1/novels/{novel_id}/neighbors/{chapter_id}")
async def chapter_neighbors(novel_id: int, chapter_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    current = result.scalar_one_or_none()
    if not current:
        raise HTTPException(status_code=404, detail="Chapter not found")

    prev_result = await db.execute(
        select(Chapter)
        .where(
            Chapter.novel_id == novel_id,
            Chapter.chapter_number < current.chapter_number,
        )
        .order_by(Chapter.chapter_number.desc())
        .limit(1)
    )
    prev_ch = prev_result.scalar_one_or_none()

    next_result = await db.execute(
        select(Chapter)
        .where(
            Chapter.novel_id == novel_id,
            Chapter.chapter_number > current.chapter_number,
        )
        .order_by(Chapter.chapter_number.asc())
        .limit(1)
    )
    next_ch = next_result.scalar_one_or_none()

    return {
        "prev": {"id": prev_ch.id, "chapter_number": prev_ch.chapter_number} if prev_ch else None,
        "next": {"id": next_ch.id, "chapter_number": next_ch.chapter_number} if next_ch else None,
    }


async def _run_bg_rewrite(chapter_id: int, do_llm: bool):
    from web.backend.db.database import async_session
    from web.backend.services.rewrite_service import rewrite_chapter

    async with async_session() as session:
        res = await session.execute(select(Chapter).where(Chapter.id == chapter_id))
        ch = res.scalar_one_or_none()
        if ch:
            await rewrite_chapter(session, ch, do_llm=do_llm)


@router.post("/api/v1/chapters/{chapter_id}/process", response_model=ChapterResponse)
async def process_chapter(
    chapter_id: int,
    background_tasks: BackgroundTasks,
    body: ProcessRequest = ProcessRequest(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    active_statuses = {
        "processing",
        "queued",
        "cleaning",
        "applying_rules",
        "rewriting",
        "validating",
        "extracting_lore",
        "extracting",
    }
    if chapter.status in active_statuses:
        raise HTTPException(status_code=409, detail="Chapter is already being processed")

    chapter.status = "queued"
    chapter.error_message = None
    await db.commit()
    await db.refresh(chapter)

    background_tasks.add_task(_run_bg_rewrite, chapter_id, body.do_llm)
    return chapter


@router.post("/api/v1/chapters/{chapter_id}/reprocess", response_model=ChapterResponse)
async def reprocess_chapter(
    chapter_id: int,
    background_tasks: BackgroundTasks,
    body: ProcessRequest = ProcessRequest(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    active_statuses = {
        "processing",
        "queued",
        "cleaning",
        "applying_rules",
        "rewriting",
        "validating",
        "extracting_lore",
        "extracting",
    }
    if chapter.status in active_statuses:
        raise HTTPException(status_code=409, detail="Chapter is already being processed")

    chapter.status = "queued"
    chapter.error_message = None
    # Don't clear refined_text here — preserve old result until new one succeeds.
    # The rewrite service will overwrite refined_text on completion.
    await db.commit()
    await db.refresh(chapter)

    background_tasks.add_task(_run_bg_rewrite, chapter_id, body.do_llm)
    return chapter


@router.get("/api/v1/chapters/{chapter_id}/status", response_model=ChapterStatusResponse)
async def chapter_status(chapter_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.get("/api/v1/chapters/{chapter_id}/read", response_model=ChapterRead)
async def read_chapter(chapter_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return ChapterRead(
        id=chapter.id,
        chapter_number=chapter.chapter_number,
        raw_text=chapter.raw_text,
        refined_text=chapter.refined_text,
        status=chapter.status,
        source_type=chapter.source_type,
    )
