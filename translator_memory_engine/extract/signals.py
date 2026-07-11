"""Signal types — the Evidence layer.

A Signal is a single observation from a single chapter. Signals are cheap and
over-produced; the Policy Miner decides which ones become Policies.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    """A single observation extracted from a chapter.

    Attributes:
        text: The surface form observed (e.g. "Lord Theodore").
        chapter: Which chapter number this was found in.
        type: Signal category: "entity", "terminology", or "honorific".
        context: The surrounding sentence, for debugging/review.
        extractor: Which extractor produced this signal.
    """

    text: str
    chapter: int
    type: str
    context: str
    extractor: str
