"""Terminology extraction — Layer 2 (phrasal).

Finds candidate recurring terms: bracketed terms, quoted special terms,
and frequently recurring capitalized bigrams/trigrams that may represent
standardized terminology (technique names, item names, concepts).
"""

import re
from typing import List

from translator_memory_engine.extract.signals import Signal
from translator_memory_engine.models import Chapter

# Patterns for bracketed or specially formatted terms
_BRACKET_PATTERN = re.compile(r"\[([^\]]{2,50})\]")
_SINGLE_QUOTE_TERM = re.compile(r"'([A-Z][^']{2,50})'")

# Possessive-form terms that may indicate named items/concepts
# e.g. "Devil's Hand", "Farmer's Market"
_POSSESSIVE_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:'s?\s+[A-Z][a-z]+)+)\b")

# Recurring compound terms (capitalized bigrams/trigrams that aren't entity names)
# These are terms like "Farmer Turtles", "Devil's Hand", "Groot Spiders"
_COMPOUND_TERM = re.compile(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")


def extract_terminology(chapters: List[Chapter], min_support: int = 2) -> List[Signal]:
    """Extract candidate terminology from chapters.

    Targets Layer 2 patterns: bracketed terms, possessive constructs,
    and recurring compound terms that represent standardized vocabulary.

    Args:
        chapters: Normalized chapter objects.
        min_support: Minimum chapters a term must appear in.

    Returns:
        List of Signal objects with type="terminology".
    """
    signals: List[Signal] = []

    # Track chapter presence for filtering
    term_chapters: dict[str, set[int]] = {}

    for ch in chapters:
        text = ch.text

        # --- Bracketed terms [like this] ---
        for m in _BRACKET_PATTERN.finditer(text):
            term = m.group(1).strip()
            if not term or term.startswith("#"):
                continue
            # Skip if it looks like dialogue (starts lowercase, has spaces)
            if term[0].islower() and " " in term:
                continue
            ctx = _get_context(text, m.start(), m.end())
            signals.append(
                Signal(
                    text=term,
                    chapter=ch.chapter,
                    type="terminology",
                    context=ctx,
                    extractor="terminology.bracket",
                )
            )
            term_chapters.setdefault(term, set()).add(ch.chapter)

        # --- Single-quoted special terms 'Like This' ---
        for m in _SINGLE_QUOTE_TERM.finditer(text):
            term = m.group(1).strip()
            if len(term.split()) < 2:
                continue  # Single words handled by entity extractor
            ctx = _get_context(text, m.start(), m.end())
            signals.append(
                Signal(
                    text=term,
                    chapter=ch.chapter,
                    type="terminology",
                    context=ctx,
                    extractor="terminology.quoted",
                )
            )
            term_chapters.setdefault(term, set()).add(ch.chapter)

        # --- Possessive-form terms (Devil's Hand, Farmer's Market) ---
        for m in _POSSESSIVE_PATTERN.finditer(text):
            term = m.group(0)
            ctx = _get_context(text, m.start(), m.end())
            signals.append(
                Signal(
                    text=term,
                    chapter=ch.chapter,
                    type="terminology",
                    context=ctx,
                    extractor="terminology.possessive",
                )
            )
            term_chapters.setdefault(term, set()).add(ch.chapter)

    # Filter by min_support
    if min_support > 1:
        passing = {t for t, chaps in term_chapters.items() if len(chaps) >= min_support}
        signals = [s for s in signals if s.text in passing]

    return signals


def _get_context(text: str, start: int, end: int) -> str:
    """Extract surrounding sentence for context."""
    ctx_start = start
    while ctx_start > 0 and text[ctx_start - 1] not in ".!?\n":
        ctx_start -= 1
    ctx_end = end
    while ctx_end < len(text) and text[ctx_end] not in ".!?\n":
        ctx_end += 1
    return text[ctx_start:ctx_end].strip()[:200]
