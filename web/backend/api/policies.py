from __future__ import annotations

import json
import time
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.db.database import get_db
from web.backend.db.models import GlossaryEntry, Policy, Novel
from web.backend.schemas.novel import GlossaryResponse, PolicyResponse, PolicyCreate, PolicyUpdate
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
