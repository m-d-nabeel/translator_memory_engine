from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from web.backend.db.database import get_db
from web.backend.db.models import Chapter, GlossaryEntry, Novel, Policy
from web.backend.schemas.novel import (
    ChapterSummary,
    NovelCreate,
    NovelDetail,
    NovelResponse,
)

router = APIRouter(prefix="/api/v1/novels", tags=["novels"])


@router.post("", response_model=NovelResponse, status_code=201)
async def create_novel(body: NovelCreate, db: AsyncSession = Depends(get_db)):
    novel = Novel(name=body.name, title=body.title, source_language=body.source_language)
    db.add(novel)
    await db.commit()
    await db.refresh(novel)
    return NovelResponse(
        id=novel.id,
        name=novel.name,
        title=novel.title,
        source_language=novel.source_language,
        created_at=novel.created_at,
        updated_at=novel.updated_at,
        chapter_count=0,
    )


@router.get("", response_model=list[NovelResponse])
async def list_novels(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Novel).order_by(Novel.created_at.desc()))
    novels = result.scalars().all()
    responses = []
    for novel in novels:
        count_result = await db.execute(select(func.count()).where(Chapter.novel_id == novel.id))
        chapter_count = count_result.scalar() or 0
        responses.append(
            NovelResponse(
                id=novel.id,
                name=novel.name,
                title=novel.title,
                source_language=novel.source_language,
                created_at=novel.created_at,
                updated_at=novel.updated_at,
                chapter_count=chapter_count,
            )
        )
    return responses


@router.get("/{novel_id}", response_model=NovelDetail)
async def get_novel(novel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Novel).options(selectinload(Novel.chapters)).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    policy_count_result = await db.execute(select(func.count()).where(Policy.novel_id == novel_id))
    glossary_count_result = await db.execute(select(func.count()).where(GlossaryEntry.novel_id == novel_id))

    chapters = sorted(novel.chapters, key=lambda c: c.chapter_number)
    return NovelDetail(
        id=novel.id,
        name=novel.name,
        title=novel.title,
        source_language=novel.source_language,
        created_at=novel.created_at,
        updated_at=novel.updated_at,
        chapter_count=len(chapters),
        chapters=[
            ChapterSummary(
                id=c.id,
                chapter_number=c.chapter_number,
                source_type=c.source_type,
                status=c.status,
                created_at=c.created_at,
            )
            for c in chapters
        ],
        policy_count=policy_count_result.scalar() or 0,
        glossary_count=glossary_count_result.scalar() or 0,
    )


@router.delete("/{novel_id}", status_code=204)
async def delete_novel(novel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    await db.delete(novel)
    await db.commit()
