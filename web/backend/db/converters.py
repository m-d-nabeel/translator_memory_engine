"""Converters between SQLAlchemy ORM models and core engine dataclasses.

Provides db_policy_to_dataclass() and db_glossary_to_dict() for translating
between the web backend's ORM layer and the core engine's in-memory types.
"""

import json
from typing import Any, Dict, List

from translator_memory_engine.policy import Policy


def db_policy_to_dataclass(db_policy: Any) -> Policy:
    """Convert an SQLAlchemy Policy ORM model to a core Policy dataclass.

    Args:
        db_policy: A row from the ``policies`` table (SQLAlchemy model).

    Returns:
        A ``Policy`` dataclass instance ready for the core engine.
    """
    return Policy(
        id=db_policy.policy_id,
        type=db_policy.type,
        trigger=db_policy.trigger,
        match=json.loads(db_policy.match_forms) if db_policy.match_forms else [],
        action=json.loads(db_policy.action) if db_policy.action else {},
        confidence=db_policy.confidence,
        evidence=json.loads(db_policy.evidence_chapters) if db_policy.evidence_chapters else [],
        applies=db_policy.applies or "deterministic",
        scores=json.loads(db_policy.scores) if db_policy.scores else {},
        category=db_policy.category or "",
        note=db_policy.note or "",
        needs_review=(db_policy.needs_review or "false").lower() == "true",
        llm_rejected=(db_policy.llm_rejected or "false").lower() == "true",
        contexts=json.loads(db_policy.contexts) if db_policy.contexts else [],
    )


def db_policies_to_list(db_policies: List[Any]) -> List[Policy]:
    """Convert a list of SQLAlchemy Policy ORM models to core Policy dataclasses."""
    return [db_policy_to_dataclass(p) for p in db_policies]


def db_glossary_to_dict(db_entry: Any) -> Dict[str, Any]:
    """Convert an SQLAlchemy GlossaryEntry ORM model to a standard dict.

    Args:
        db_entry: A row from the ``glossary`` table (SQLAlchemy model).

    Returns:
        A dict with keys: canonical, match (all surface forms), aliases, type, confidence.
    """
    aliases = json.loads(db_entry.aliases) if db_entry.aliases else []
    # "match" includes canonical + all aliases (shield.py / rewriter.py expect this key)
    match = [db_entry.canonical] + aliases if db_entry.canonical else aliases
    return {
        "canonical": db_entry.canonical,
        "match": match,
        "aliases": aliases,
        "type": db_entry.entity_type,
        "confidence": db_entry.confidence,
    }


def db_glossary_to_list(db_entries: List[Any]) -> List[Dict[str, Any]]:
    """Convert a list of SQLAlchemy GlossaryEntry ORM models to dicts."""
    return [db_glossary_to_dict(e) for e in db_entries]
