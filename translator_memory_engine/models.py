from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class Chapter:
    chapter: int
    title: str
    text: str
    paragraphs: List[str] = field(default_factory=list)


@dataclass
class Policy:
    id: str
    type: str
    store: str
    trigger: str
    action: Dict[str, Any]
    confidence: float
    evidence: List[int]
    match: List[str] = field(default_factory=list)
    applies: str = "deterministic"
    valid_from: Optional[int] = None
    valid_until: Optional[int] = None
    superseded_by: Optional[str] = None
    scores: Dict[str, float] = field(default_factory=dict)
    category: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
