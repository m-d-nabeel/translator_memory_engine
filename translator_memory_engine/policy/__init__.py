"""Policy schema — single source of truth for the Policy type.

Every other package (memory, retrieve, validate, rewrite) imports this.
None of them redefine it.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


@dataclass
class Policy:
    """An explicit editorial decision extracted from translator behavior.

    See PLAN.md §4 for the full abstraction (Evidence → Inference → Policy).

    Attributes:
        id: Unique identifier (e.g. "p_184").
        type: One of: entity-naming, honorific, terminology, formatting.
        trigger: The canonical form that activates this policy.
        match: All known surface forms (canonical + aliases + forbidden variants).
        action: What to do when triggered (e.g. {"render_as": "Li Qing"}).
        applies: "deterministic" (pre-pass substitution) or "prompted" (LLM guidance).
        confidence: Overall confidence score (0.0–1.0).
        scores: Decomposed confidence: frequency, consistency, context.
        evidence: Chapter numbers where this policy was observed.
        category: Optional sub-category for grouping.
        note: Optional human-readable note.
        needs_review: True when the policy is ambiguous / low-confidence / overlaps
            another policy. Per PLAN.md §3 and D10, ambiguous cases are flagged for
            human review, not silently applied or overwritten. Such policies are
            never used in the deterministic pre-pass.
    """
    id: str
    type: str
    trigger: str
    action: Dict[str, Any]
    confidence: float
    evidence: List[int]
    match: List[str] = field(default_factory=list)
    applies: str = "deterministic"
    scores: Dict[str, float] = field(default_factory=dict)
    category: str = ""
    note: str = ""
    needs_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
