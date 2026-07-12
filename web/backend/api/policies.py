from __future__ import annotations

import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.db.database import get_db
from web.backend.db.models import GlossaryEntry, Novel, Policy
from web.backend.schemas.novel import (
    ExtractLoreRequest,
    GlossaryMetadataUpdate,
    GlossaryResponse,
    PolicyCreate,
    PolicyResponse,
    PolicyUpdate,
)
from web.backend.services.extraction_service import extract_policies_for_novel

router = APIRouter(tags=["policies"])


@router.post("/api/v1/novels/{novel_id}/extract")
async def extract_policies_and_glossary(novel_id: int, background_tasks: BackgroundTasks):
    background_tasks.add_task(extract_policies_for_novel, novel_id)
    return {"status": "Extraction started in background."}


@router.post("/api/v1/novels/{novel_id}/extract-lore")
async def extract_lore_endpoint(novel_id: int, background_tasks: BackgroundTasks, req: ExtractLoreRequest | None = None):
    from web.backend.db.database import async_session
    from web.backend.services.rewrite_service import extract_lore_for_chapters
    chapter_ids = req.chapter_ids if req else None
    only_og_tl = req.only_og_tl if req else False
    bypass_review = req.bypass_review if req else False
    background_tasks.add_task(extract_lore_for_chapters, novel_id, chapter_ids, async_session, only_og_tl, bypass_review)
    return {"status": "Lore extraction started in background."}



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

@router.put("/api/v1/novels/{novel_id}/glossary/{entry_id}/metadata", response_model=GlossaryResponse)
async def update_glossary_metadata(
    novel_id: int, entry_id: int, update_in: GlossaryMetadataUpdate, db: AsyncSession = Depends(get_db)
):
    entry = await db.get(GlossaryEntry, entry_id)
    if not entry or entry.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Glossary entry not found")

    # If apply_proposed is true, we merge the proposed updates into the main fields
    if update_in.apply_proposed and entry.metadata_json:
        try:
            meta = json.loads(entry.metadata_json)
            if "proposed_updates" in meta:
                proposed = meta.pop("proposed_updates")
                meta.update(proposed)
                entry.metadata_json = json.dumps(meta)
        except Exception:
            pass
    else:
        entry.metadata_json = update_in.metadata_json

    # Find the corresponding policy to update its metadata_json and needs_review status
    policy_result = await db.execute(
        select(Policy)
        .where(Policy.novel_id == novel_id)
        .where(Policy.trigger == entry.canonical)
    )
    policy = policy_result.scalar_one_or_none()
    if policy:
        policy.metadata_json = entry.metadata_json
        policy.needs_review = "true" if update_in.needs_review else "false"

    await db.commit()
    await db.refresh(entry)
    return entry


@router.post("/api/v1/novels/{novel_id}/policies", response_model=PolicyResponse)
async def create_policy(novel_id: int, policy_in: PolicyCreate, db: AsyncSession = Depends(get_db)):
    novel = await db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    new_policy = Policy(
        novel_id=novel_id,
        policy_id=f"MANUAL-{int(time.time() * 1000)}",
        type="ENTITY-NAMING",
        trigger=policy_in.trigger,
        match_forms=json.dumps([policy_in.trigger], ensure_ascii=False),
        action=json.dumps({"render_as": policy_in.replacement}, ensure_ascii=False),
        confidence=1.0,
        applies="deterministic",
        note=policy_in.note,
    )
    db.add(new_policy)
    await db.commit()
    await db.refresh(new_policy)
    return new_policy


@router.put("/api/v1/novels/{novel_id}/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    novel_id: int, policy_id: int, policy_in: PolicyUpdate, db: AsyncSession = Depends(get_db)
):
    policy = await db.get(Policy, policy_id)
    if not policy or policy.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Policy not found")

    if policy_in.trigger is not None:
        policy.trigger = policy_in.trigger
        try:
            forms = json.loads(policy.match_forms)
            if policy_in.trigger not in forms:
                forms.append(policy_in.trigger)
            policy.match_forms = json.dumps(forms, ensure_ascii=False)
        except Exception:
            policy.match_forms = json.dumps([policy_in.trigger], ensure_ascii=False)

    if policy_in.replacement is not None:
        try:
            action = json.loads(policy.action)
            action["render_as"] = policy_in.replacement
            policy.action = json.dumps(action, ensure_ascii=False)
        except Exception:
            policy.action = json.dumps({"render_as": policy_in.replacement}, ensure_ascii=False)

    if policy_in.note is not None:
        policy.note = policy_in.note

    # Manual edit implies high confidence
    policy.confidence = 1.0

    await db.commit()
    await db.refresh(policy)
    return policy


@router.delete("/api/v1/novels/{novel_id}/policies/{policy_id}")
async def delete_policy(novel_id: int, policy_id: int, db: AsyncSession = Depends(get_db)):
    policy = await db.get(Policy, policy_id)
    if not policy or policy.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Policy not found")

    await db.delete(policy)
    await db.commit()
    return {"status": "deleted"}
