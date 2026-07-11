from dataclasses import dataclass, field
from typing import List


@dataclass
class Chapter:
    """A normalized chapter loaded from a corpus file.

    Shared across packages (ingest, extract, policy).
    """

    chapter: int
    title: str
    text: str
    paragraphs: List[str] = field(default_factory=list)
