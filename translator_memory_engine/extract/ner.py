"""NER-based entity extraction using spaCy with POS-based filtering.

Complements the heuristic entity extractor by using a pre-trained NER model
that understands what named entities are, not just what capitalization looks like.

Key improvements over bare spaCy NER:
- POS-tag validation: entities led by verbs/gerunds are dropped (fixes
  "Ignoring Calron", "Hearing Dominic" fragments)
- Single-token entities must be PROPN (proper noun), filtering common nouns
  that spaCy over-labels ("Rice", "Cook", "Magic", "Village")
- Onomatopoeia / repetition detection filters sound effects

NOTE: GLiNER (zero-shot fiction NER) would be ideal here but is currently
incompatible with transformers>=5.x due to embedding size mismatches in all
v2.1 checkpoints. When upstream fixes land, swap _get_spacy_nlp() for GLiNER.
"""

from typing import List, Optional, Set

from translator_memory_engine.extract.signals import Signal
from translator_memory_engine.models import Chapter

# Lazy-loaded spaCy model
_nlp = None

# ----------------------------------------------------------------------- #
# Noise filters
# ----------------------------------------------------------------------- #

# Common onomatopoeia / sound effects that NER misclassifies as entities
_ONOMATOPOEIA: Set[str] = {
    "haha",
    "hahaha",
    "hahahaha",
    "hehe",
    "hehehe",
    "hoho",
    "hohoho",
    "kyaha",
    "kyahaha",
    "kya",
    "pfft",
    "hmm",
    "hmmm",
    "hmph",
    "tsk",
    "tch",
    "ugh",
    "argh",
    "ahem",
    "phew",
    "gulp",
    "eek",
    "thud",
    "thump",
    "bang",
    "crash",
    "creak",
    "screech",
    "swoosh",
    "whoosh",
    "shoosh",
    "huff",
    "puff",
    "ding",
    "dong",
    "buzz",
    "click",
    "clack",
    "splash",
    "plop",
    "sizzle",
    "rumble",
    "wow",
    "whoa",
    "ooh",
    "aah",
}

# Gerund/participle POS tags that indicate sentence fragments, not entity names
_FRAGMENT_POS = {"VBG", "VBN", "VBD", "VB", "VBP", "VBZ"}

# spaCy entity labels we care about for translation consistency
_RELEVANT_LABELS = {
    "PERSON",  # character names
    "ORG",  # organizations, factions, companies
    "GPE",  # geopolitical entities (kingdoms, cities, countries)
    "FAC",  # buildings, landmarks (castles, palaces)
    "PRODUCT",  # items, weapons, artifacts
    "NORP",  # nationalities, religious/political groups
    "LOC",  # natural locations (mountains, rivers, forests)
    "EVENT",  # named events, battles
    "WORK_OF_ART",  # named works (techniques, arts, formations)
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
            pattern = text[i : i + window]
            if pattern == text[i + window : i + window * 2]:
                return True
    return False


def _is_noise(text: str) -> bool:
    """Check if an entity is noise (onomatopoeia, repetition, punctuation)."""
    if len(text.strip()) < 2:
        return True
    if not any(c.isalpha() for c in text):
        return True
    text_lower = text.lower().rstrip("!-")
    if text_lower in _ONOMATOPOEIA:
        return True
    if len(text_lower) >= 4 and _has_heavy_repetition(text_lower):
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
    """Extract named entities using spaCy NER with POS-based filtering.

    Filters applied:
    - Entity label must be in _RELEVANT_LABELS (PERSON, ORG, GPE, etc.)
    - Noise filter: onomatopoeia, heavy repetition, punctuation-only
    - POS validation: entities led by VBG/VBN/VBD are dropped
      (catches "Ignoring Calron", "Hearing Dominic" fragments)
    - Single-token entities must be PROPN (proper noun)
      (catches "Rice", "Cook", "Magic", "Village" false positives)

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

            text = ent.text.strip()
            if _is_noise(text):
                continue

            # POS-based validation: skip entities led by a verb/gerund
            # (e.g. "Ignoring Calron" where spaCy extends the PERSON boundary)
            first_token = ent[0] if len(ent) > 0 else None
            if first_token and first_token.tag_ in _FRAGMENT_POS:
                continue

            # For single-token entities, require PROPN (proper noun).
            # This filters common nouns that spaCy over-labels as entities
            # in fiction text: "Rice", "Cook", "Magic", "Village", etc.
            if len(ent) == 1 and first_token:
                if first_token.pos_ != "PROPN":
                    continue

            # Get sentence context
            context = ent.sent.text.strip()[:200] if ent.sent else ""

            signals.append(
                Signal(
                    text=text,
                    chapter=ch.chapter,
                    type="entity",
                    context=context,
                    extractor=f"ner.spacy.{ent.label_}",
                )
            )

    return signals
