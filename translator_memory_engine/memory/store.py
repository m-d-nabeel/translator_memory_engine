"""Policy Store — single typed store with SQLite backend.

Implements the store interface from PLAN.md §5:
  store.add(policy)
  store.get(id) -> Policy
  store.query(trigger) -> [Policy]
  store.all() -> [Policy]
  store.export_glossary() -> derived glossary view

Persistence:
  store.save_to_db(db_path, novel_id)   — write to SQLite (primary store)
  store.load_from_db(db_path, novel_id)  — read from SQLite
  store.export_jsonl(path)               — export to JSONL (backup/legacy)
  store.import_jsonl(path)               — import from JSONL (migration)

Backend: SQLite for production. JSONL for backup/legacy compatibility.
"""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from translator_memory_engine.policy import Policy


class PolicyStore:
    """In-memory policy store with SQLite persistence."""

    def __init__(self) -> None:
        self._policies: Dict[str, Policy] = {}
        # Index: normalized trigger -> list of policy IDs
        self._trigger_index: Dict[str, List[str]] = {}
        # Index: all match forms -> policy ID
        self._match_index: Dict[str, List[str]] = {}

    def add(self, policy: Policy) -> None:
        """Add a policy to the store."""
        self._policies[policy.id] = policy
        # Index by trigger
        trigger_key = policy.trigger.lower()
        self._trigger_index.setdefault(trigger_key, []).append(policy.id)
        # Index by all match forms
        for form in policy.match:
            form_key = form.lower()
            self._match_index.setdefault(form_key, []).append(policy.id)

    def get(self, policy_id: str) -> Optional[Policy]:
        """Get a policy by ID."""
        return self._policies.get(policy_id)

    def query(self, trigger: str) -> List[Policy]:
        """Find policies matching a trigger (case-insensitive).

        Checks both the trigger index and the match-form index.
        """
        key = trigger.lower()
        policy_ids: set[str] = set()

        # Exact trigger match
        if key in self._trigger_index:
            policy_ids.update(self._trigger_index[key])

        # Match form lookup
        if key in self._match_index:
            policy_ids.update(self._match_index[key])

        return [self._policies[pid] for pid in policy_ids if pid in self._policies]

    def all(self) -> List[Policy]:
        """Return all policies, sorted by confidence descending."""
        return sorted(self._policies.values(), key=lambda p: p.confidence, reverse=True)

    def export_glossary(self) -> List[Dict[str, Any]]:
        """Export a derived glossary view.

        Each entry has: canonical, aliases, type, confidence, chapters.
        """
        glossary = []
        for p in self.all():
            # Rejected policies are retained for review but excluded from the
            # usable glossary (they must not be applied downstream).
            if p.llm_rejected:
                continue
            aliases = [f for f in p.match if f != p.trigger]
            glossary.append(
                {
                    "canonical": p.trigger,
                    "match": p.match,  # all surface forms (shield.py / rewriter.py expect "match")
                    "aliases": aliases,
                    "type": p.type,
                    "confidence": p.confidence,
                    "chapters": p.evidence,
                    "needs_review": p.needs_review,
                }
            )
        return glossary

    # ------------------------------------------------------------------
    # SQLite persistence (primary store)
    # ------------------------------------------------------------------

    def save_to_db(self, db_path: str, novel_id: int) -> None:
        """Write all policies in this store to the SQLite database.

        Uses INSERT OR REPLACE to handle idempotent upserts.
        The ``novel_id`` links policies to a specific novel in the web schema.
        """
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            for policy in self.all():
                conn.execute(
                    """INSERT OR REPLACE INTO policies
                       (novel_id, policy_id, type, trigger, match_forms, action,
                        confidence, evidence_chapters, applies, scores, category,
                        note, needs_review, llm_rejected, contexts, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        novel_id,
                        policy.id,
                        policy.type,
                        policy.trigger,
                        json.dumps(policy.match, ensure_ascii=False),
                        json.dumps(policy.action, ensure_ascii=False),
                        policy.confidence,
                        json.dumps(policy.evidence),
                        policy.applies,
                        json.dumps(policy.scores) if policy.scores else None,
                        policy.category or None,
                        policy.note or None,
                        str(policy.needs_review).lower(),
                        str(policy.llm_rejected).lower(),
                        json.dumps(policy.contexts, ensure_ascii=False) if policy.contexts else None,
                        json.dumps(policy.metadata, ensure_ascii=False) if policy.metadata else None,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def load_from_db(self, db_path: str, novel_id: int) -> None:
        """Load policies from the SQLite database into this store.

        Queries the ``policies`` table for the given ``novel_id`` and
        populates the in-memory indexes.
        """
        if not os.path.exists(db_path):
            return
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                "SELECT policy_id, type, trigger, match_forms, action, "
                "confidence, evidence_chapters, applies, scores, category, "
                "note, needs_review, llm_rejected, contexts, metadata_json "
                "FROM policies WHERE novel_id = ?",
                (novel_id,),
            )
            for row in cursor:
                (
                    policy_id,
                    ptype,
                    trigger,
                    match_forms_json,
                    action_json,
                    confidence,
                    evidence_json,
                    applies,
                    scores_json,
                    category,
                    note,
                    needs_review,
                    llm_rejected,
                    contexts_json,
                    metadata_json,
                ) = row
                policy = Policy(
                    id=policy_id,
                    type=ptype,
                    trigger=trigger,
                    match=json.loads(match_forms_json) if match_forms_json else [],
                    action=json.loads(action_json) if action_json else {},
                    confidence=confidence,
                    evidence=json.loads(evidence_json) if evidence_json else [],
                    applies=applies or "deterministic",
                    scores=json.loads(scores_json) if scores_json else {},
                    category=category or "",
                    note=note or "",
                    needs_review=(needs_review or "false").lower() == "true",
                    llm_rejected=(llm_rejected or "false").lower() == "true",
                    contexts=json.loads(contexts_json) if contexts_json else [],
                    metadata=json.loads(metadata_json) if metadata_json else {},
                )
                self.add(policy)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # JSONL export/import (backup / legacy compatibility)
    # ------------------------------------------------------------------

    def export_jsonl(self, path: str) -> None:
        """Write policies as JSON lines to a file (backup format)."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for policy in self.all():
                f.write(json.dumps(policy.to_dict(), ensure_ascii=False) + "\n")

    def import_jsonl(self, path: str) -> None:
        """Load policies from a JSON-lines file."""
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                policy = Policy(**data)
                self.add(policy)

    # Keep legacy aliases for backwards compatibility
    save = export_jsonl
    load = import_jsonl

    def __len__(self) -> int:
        return len(self._policies)

    def __repr__(self) -> str:
        return f"PolicyStore({len(self._policies)} policies)"
