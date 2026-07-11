"""Policy Store — single typed store with JSON backend.

Implements the store interface from PLAN.md §5:
  store.add(policy)
  store.get(id) → Policy
  store.query(trigger) → [Policy]
  store.all() → [Policy]
  store.export_glossary() → derived glossary view
  store.save(path)
  store.load(path)

Backend: JSON lines for prototype. SQLite for production (future).
"""

import json
import os
from typing import Any, Dict, List, Optional

from translator_memory_engine.policy import Policy


class PolicyStore:
    """In-memory policy store with JSON-lines persistence."""

    def __init__(self) -> None:
        self._policies: Dict[str, Policy] = {}
        # Index: normalized trigger → list of policy IDs
        self._trigger_index: Dict[str, List[str]] = {}
        # Index: all match forms → policy ID
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
            glossary.append({
                "canonical": p.trigger,
                "aliases": aliases,
                "type": p.type,
                "confidence": p.confidence,
                "chapters": p.evidence,
                "needs_review": p.needs_review,
            })
        return glossary

    def save(self, path: str) -> None:
        """Write policies as JSON lines to a file."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for policy in self.all():
                f.write(json.dumps(policy.to_dict(), ensure_ascii=False) + "\n")

    def load(self, path: str) -> None:
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

    def __len__(self) -> int:
        return len(self._policies)

    def __repr__(self) -> str:
        return f"PolicyStore({len(self._policies)} policies)"
