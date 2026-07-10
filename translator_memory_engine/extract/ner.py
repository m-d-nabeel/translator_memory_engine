"""NER-based entity extraction using spaCy.

Complements the heuristic entity extractor by using a pre-trained NER model
that understands what named entities are, not just what capitalization looks like.

Catches entities that heuristics miss (sentence-start names, uncapitalized terms)
and avoids false positives that heuristics can't filter (common nouns, roles).
"""

from typing import List, Optional

from translator_memory_engine.models import Chapter
from translator_memory_engine.extract.signals import Signal

# Lazy-load spaCy to avoid import cost when not used
_nlp = None

# Entity types we care about for translation consistency
_RELEVANT_LABELS = {
    "PERSON",    # character names
    "ORG",       # organizations, factions, companies
    "GPE",       # geopolitical entities (kingdoms, cities, countries)
    "FAC",       # buildings, landmarks (castles, palaces)
    "PRODUCT",   # items, weapons, artifacts
    "NORP",      # nationalities, religious/political groups
    "LOC",       # natural locations (mountains, rivers, forests)
    "EVENT",     # named events, battles
    "WORK_OF_ART",  # named works (techniques, arts, formations)
}

# Common onomatopoeia / sound effects that NER misclassifies as entities
_ONOMATOPOEIA = {
    "haha", "hahaha", "hahahaha", "hehe", "hehehe", "hoho", "hohoho",
    "kyaha", "kyahaha", "kya", "pfft", "hmm", "hmmm", "hmph",
    "tsk", "tch", "ugh", "argh", "ahem", "phew", "gulp", "eek",
    "thud", "thump", "bang", "crash", "creak", "screech", "swoosh",
    "whoosh", "shoosh", "huff", "puff", "ding", "dong", "buzz",
    "click", "clack", "splash", "plop", "sizzle", "rumble",
    "wow", "whoa", "ooh", "aah",
}


def _has_heavy_repetition(text: str) -> bool:
    """Detect strings with heavy character repetition (e.g. 'hahaha', 'screeech').

    Returns True if any 2-3 char subsequence repeats 2+ times.
    """
    text = text.lower()
    for window in (2, 3):
        if len(text) < window * 2:
            continue
        for i in range(len(text) - window * 2 + 1):
            pattern = text[i:i + window]
            if pattern == text[i + window:i + window * 2]:
                return True
    return False

def _get_nlp():
    """Lazy-load the spaCy model."""
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def extract_ner_entities(
    chapters: List[Chapter],
    model_name: Optional[str] = None,
) -> List[Signal]:
    """Extract named entities using spaCy NER.

    Args:
        chapters: Normalized chapter objects.
        model_name: spaCy model to use. Default: en_core_web_sm.

    Returns:
        List of Signal objects with type="entity" and extractor="ner.spacy".
    """
    if model_name:
        import spacy
        nlp = spacy.load(model_name)
    else:
        nlp = _get_nlp()

    signals: List[Signal] = []

    for ch in chapters:
        doc = nlp(ch.text)

        for ent in doc.ents:
            if ent.label_ not in _RELEVANT_LABELS:
                continue

            # Skip very short entities (single character, likely noise)
            text = ent.text.strip()
            if len(text) < 2:
                continue

            # Skip entities that are just punctuation or numbers
            if not any(c.isalpha() for c in text):
                continue

            # Skip onomatopoeia / sound effects that spaCy misclassifies
            text_lower = text.lower().rstrip("!-")
            if text_lower in _ONOMATOPOEIA:
                continue
            # Skip if it looks like repeated characters (hahaha, kyahaha, etc.)
            if len(text_lower) >= 4 and _has_heavy_repetition(text_lower):
                continue

            # Get sentence context
            context = ent.sent.text.strip()[:200] if ent.sent else ""

            signals.append(Signal(
                text=text,
                chapter=ch.chapter,
                type="entity",
                context=context,
                extractor=f"ner.spacy.{ent.label_}",
            ))

    return signals
