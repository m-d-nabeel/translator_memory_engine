"""Signal extraction orchestrator.

Runs all signal extractors and merges results into a single signal list.
Supports both heuristic extractors and ML-based extractors (spaCy NER).
"""

from typing import List, Optional

from translator_memory_engine.models import Chapter
from translator_memory_engine.extract.signals import Signal
from translator_memory_engine.extract.entity import extract_entities
from translator_memory_engine.extract.terminology import extract_terminology
from translator_memory_engine.extract.honorific import extract_honorifics


def extract_signals(
    chapters: List[Chapter],
    min_support: int = 2,
    source_languages: Optional[List[str]] = None,
    use_ner: bool = True,
) -> List[Signal]:
    """Run all extractors and return merged signals.

    Args:
        chapters: Normalized chapter objects from ingest.
        min_support: Minimum chapters a term must appear in.
        source_languages: Source languages for honorific detection.
        use_ner: Whether to run spaCy NER extraction (default True).

    Returns:
        Combined list of signals from all extractors.
    """
    signals: List[Signal] = []

    # Heuristic extractors (always run)
    signals.extend(extract_entities(chapters, min_support=min_support))
    signals.extend(extract_terminology(chapters, min_support=min_support))
    signals.extend(extract_honorifics(chapters, source_languages=source_languages))

    # ML-based extractors
    if use_ner:
        try:
            from translator_memory_engine.extract.ner import extract_ner_entities
            signals.extend(extract_ner_entities(chapters))
        except ImportError:
            pass  # spaCy not installed, skip NER

    return signals
