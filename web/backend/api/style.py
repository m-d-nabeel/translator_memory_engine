from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.db.database import get_db
from web.backend.db.models import Novel, StyleSnippet
from web.backend.schemas.novel import StyleSnippetCreate, StyleSnippetResponse, StyleSnippetUpdate

router = APIRouter(tags=["style"])


@router.get("/api/v1/novels/{novel_id}/style-snippets", response_model=list[StyleSnippetResponse])
async def list_style_snippets(novel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(StyleSnippet).where(StyleSnippet.novel_id == novel_id).order_by(StyleSnippet.created_at.desc())
    )
    return result.scalars().all()


@router.post("/api/v1/novels/{novel_id}/style-snippets", response_model=StyleSnippetResponse)
async def create_style_snippet(novel_id: int, snippet_in: StyleSnippetCreate, db: AsyncSession = Depends(get_db)):
    novel = await db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    new_snippet = StyleSnippet(
        novel_id=novel_id,
        text=snippet_in.text,
        note=snippet_in.note,
    )
    db.add(new_snippet)
    await db.commit()
    await db.refresh(new_snippet)
    return new_snippet


@router.put("/api/v1/novels/{novel_id}/style-snippets/{snippet_id}", response_model=StyleSnippetResponse)
async def update_style_snippet(
    novel_id: int, snippet_id: int, snippet_in: StyleSnippetUpdate, db: AsyncSession = Depends(get_db)
):
    snippet = await db.get(StyleSnippet, snippet_id)
    if not snippet or snippet.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Style snippet not found")

    if snippet_in.text is not None:
        snippet.text = snippet_in.text
    if snippet_in.note is not None:
        snippet.note = snippet_in.note

    await db.commit()
    await db.refresh(snippet)
    return snippet


@router.delete("/api/v1/novels/{novel_id}/style-snippets/{snippet_id}")
async def delete_style_snippet(novel_id: int, snippet_id: int, db: AsyncSession = Depends(get_db)):
    snippet = await db.get(StyleSnippet, snippet_id)
    if not snippet or snippet.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Style snippet not found")

    await db.delete(snippet)
    await db.commit()
    return {"status": "deleted"}
