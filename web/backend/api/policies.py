from __future__ import annotations

import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.db.database import get_db
from web.backend.db.models import GlossaryEntry, Novel, Policy
from web.backend.schemas.novel import (
    DuplicateClusterResponse,
    ExtractLoreRequest,
    GlossaryMetadataUpdate,
    GlossaryResponse,
    MergeGlossaryRequest,
    PolicyCreate,
    PolicyResponse,
    PolicyUpdate,
)
from web.backend.services.extraction_service import extract_policies_for_novel
from translator_memory_engine.policy.miner import _normalize, _normalized_edit_distance

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


@router.post("/api/v1/novels/{novel_id}/glossary/merge", response_model=GlossaryResponse)
async def merge_glossary_entries(
    novel_id: int, merge_in: MergeGlossaryRequest, db: AsyncSession = Depends(get_db)
):
    target = await db.get(GlossaryEntry, merge_in.target_id)
    if not target or target.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Target glossary entry not found")

    target_policy_res = await db.execute(
        select(Policy).where(Policy.novel_id == novel_id, Policy.trigger == target.canonical)
    )
    target_policy = target_policy_res.scalar_one_or_none()

    target_aliases = set()
    if target.aliases:
        try:
            target_aliases = set(json.loads(target.aliases))
        except Exception:
            pass
    target_aliases.add(target.canonical)

    target_evidence = []
    if target.evidence_contexts:
        try:
            target_evidence = json.loads(target.evidence_contexts)
        except Exception:
            pass

    target_meta = {}
    if target.metadata_json:
        try:
            target_meta = json.loads(target.metadata_json)
        except Exception:
            pass

    deterministic_aliases = {target.canonical}
    for src_id in merge_in.source_ids:
        if src_id == merge_in.target_id:
            continue
        src = await db.get(GlossaryEntry, src_id)
        if not src or src.novel_id != novel_id:
            continue

        target_aliases.add(src.canonical)
        if merge_in.deterministic_ids is not None and src_id in merge_in.deterministic_ids:
            deterministic_aliases.add(src.canonical)

        if src.aliases:
            try:
                for a in json.loads(src.aliases):
                    target_aliases.add(a)
            except Exception:
                pass

        if src.evidence_contexts:
            try:
                for ev in json.loads(src.evidence_contexts):
                    if ev and ev not in target_evidence and len(target_evidence) < 5:
                        target_evidence.append(ev)
            except Exception:
                pass

        if src.metadata_json:
            try:
                src_meta = json.loads(src.metadata_json)
                for k, v in src_meta.items():
                    if not target_meta.get(k) and v:
                        target_meta[k] = v
            except Exception:
                pass

        src_policy_res = await db.execute(
            select(Policy).where(Policy.novel_id == novel_id, Policy.trigger == src.canonical)
        )
        src_policy = src_policy_res.scalar_one_or_none()
        if src_policy:
            src_policy.llm_rejected = "true"
            src_policy.needs_review = "false"
            src_policy.match_forms = json.dumps([])

        await db.delete(src)

    def _is_spelling_or_typo_variant(form: str, canon: str) -> bool:
        if form == canon:
            return True
        k1, k2 = _normalize(form), _normalize(canon)
        if set(k1.split()) == set(k2.split()) and len(k1.split()) > 0:
            return True
        if _normalized_edit_distance(k1, k2) <= 0.3 and min(len(k1), len(k2)) >= 4:
            return True
        return False

    aliases_list = sorted(list(target_aliases - {target.canonical}))
    if merge_in.deterministic_ids is not None:
        deterministic_match_forms = sorted(list(deterministic_aliases))
    else:
        deterministic_match_forms = sorted(list({
            alias for alias in target_aliases if _is_spelling_or_typo_variant(alias, target.canonical)
        }))
    if not deterministic_match_forms:
        deterministic_match_forms = [target.canonical]

    target.aliases = json.dumps(aliases_list)
    target.evidence_contexts = json.dumps(target_evidence) if target_evidence else None
    target.metadata_json = json.dumps(target_meta) if target_meta else None

    if target_policy:
        target_policy.match_forms = json.dumps(deterministic_match_forms)
        target_policy.contexts = json.dumps(target_evidence) if target_evidence else None
        target_policy.metadata_json = target.metadata_json

    await db.commit()
    await db.refresh(target)
    return target


@router.get("/api/v1/novels/{novel_id}/glossary/duplicates", response_model=list[DuplicateClusterResponse])
async def get_glossary_duplicates(novel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GlossaryEntry)
        .where(GlossaryEntry.novel_id == novel_id)
        .order_by(GlossaryEntry.canonical)
    )
    entries = result.scalars().all()

    TITLE_STOPWORDS = {
        "count", "countess", "lord", "lady", "sir", "madam", "chief", "elder", "master",
        "saint", "king", "queen", "prince", "princess", "captain", "general", "brother",
        "sister", "patriarch", "matriarch", "young", "old", "senior", "junior", "wizard",
        "apprentice", "guard", "soldier", "village", "city", "town", "castle", "palace",
        "sect", "clan", "family", "house", "mountain", "river", "forest", "valley", "lake",
        "sword", "blade", "demon", "divine", "holy", "dark", "light", "grand", "great",
        "high", "supreme", "emperor", "empress", "duke", "duchess", "baron", "baroness",
        "marquis", "the", "and", "of", "in", "at", "to", "for", "with"
    }

    def _tokens(key: str) -> set[str]:
        return set(_normalize(key).split())

    def _core_tokens(key: str) -> set[str]:
        t = _tokens(key)
        core = {tok for tok in t if tok not in TITLE_STOPWORDS and len(tok) >= 2}
        return core if core else t

    clusters: list[DuplicateClusterResponse] = []
    visited: set[int] = set()

    for i, e1 in enumerate(entries):
        if e1.id in visited:
            continue
        k1 = _normalize(e1.canonical)
        t1 = _tokens(k1)
        t1_core = _core_tokens(k1)
        cluster_cands = []
        cluster_reasons = []

        for j in range(i + 1, len(entries)):
            e2 = entries[j]
            if e2.id in visited:
                continue
            k2 = _normalize(e2.canonical)
            t2 = _tokens(k2)
            t2_core = _core_tokens(k2)

            match_reason = None
            if t1 == t2 and len(t1) > 0:
                match_reason = "Identical tokens in different word order"
            elif t1_core == t2_core and len(t1_core) > 0:
                match_reason = "Identical core name (shared entity with different title/prefix)"
            elif (k1 in k2 or k2 in k1) and min(len(k1), len(k2)) >= 4:
                shorter_tokens = t1 if len(k1) <= len(k2) else t2
                if any(tok not in TITLE_STOPWORDS for tok in shorter_tokens):
                    match_reason = f"Substring overlap ({e1.canonical} / {e2.canonical})"
            else:
                shared_core = t1_core & t2_core
                if any(len(tok) >= 4 for tok in shared_core) and len(t1_core) >= 1 and len(t2_core) >= 1:
                    match_reason = f"Shared core name tokens ({', '.join(sorted(shared_core))})"
                elif _normalized_edit_distance(k1, k2) <= 0.3 and min(len(k1), len(k2)) >= 4:
                    match_reason = "Near-duplicate spelling (Levenshtein distance <= 0.3)"

            if match_reason:
                cluster_cands.append(e2)
                cluster_reasons.append(match_reason)
                visited.add(e2.id)

        if cluster_cands:
            visited.add(e1.id)
            all_in_cluster = [e1] + cluster_cands
            all_in_cluster.sort(key=lambda x: len(x.canonical))
            target = all_in_cluster[0]
            candidates = [x for x in all_in_cluster if x.id != target.id]
            reasons_str = "; ".join(sorted(set(cluster_reasons)))
            clusters.append(
                DuplicateClusterResponse(
                    cluster_id=f"cluster-{target.id}",
                    target=target,
                    candidates=candidates,
                    reason=reasons_str,
                )
            )

    return clusters


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
