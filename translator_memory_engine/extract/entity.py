"""Entity name extraction — Layer 1 (lexical).

Finds candidate character names, organization names, place names, and item names
using heuristic patterns. Produces Signal objects for the Policy Miner.
"""

import re
from typing import List, Set

from translator_memory_engine.extract.signals import Signal
from translator_memory_engine.models import Chapter

# Common English words that happen to be capitalized at sentence starts
# or are too generic to be entity names. Kept intentionally conservative —
# false negatives are cheaper than false positives at the extraction stage.
_STOP_WORDS: Set[str] = {
    "The",
    "This",
    "That",
    "These",
    "Those",
    "There",
    "Then",
    "Thus",
    "They",
    "Their",
    "Them",
    "What",
    "When",
    "Where",
    "Which",
    "While",
    "Who",
    "Whom",
    "Why",
    "How",
    "However",
    "Although",
    "Also",
    "Already",
    "After",
    "Again",
    "And",
    "Another",
    "Any",
    "Are",
    "Around",
    "Before",
    "Being",
    "Between",
    "Both",
    "But",
    "Can",
    "Could",
    "Did",
    "Does",
    "Don",
    "During",
    "Each",
    "Either",
    "Else",
    "Even",
    "Every",
    "For",
    "From",
    "Get",
    "Got",
    "Had",
    "Has",
    "Have",
    "Her",
    "Here",
    "Him",
    "His",
    "If",
    "Into",
    "Its",
    "Just",
    "Let",
    "Like",
    "May",
    "More",
    "Most",
    "Much",
    "Must",
    "Never",
    "Not",
    "Now",
    "Once",
    "Only",
    "Other",
    "Our",
    "Out",
    "Over",
    "Own",
    "Perhaps",
    "Please",
    "Rather",
    "Really",
    "Same",
    "She",
    "Should",
    "Since",
    "So",
    "Some",
    "Still",
    "Such",
    "Sure",
    "Than",
    "Thank",
    "Too",
    "Upon",
    "Very",
    "Was",
    "Well",
    "Were",
    "Will",
    "With",
    "Would",
    "Yet",
    "You",
    "Your",
    # Common dialogue/narration starters
    "Yes",
    "No",
    "Oh",
    "Ah",
    "Hmm",
    "Huh",
    "Hey",
    "Hehe",
    "Haha",
    "Wow",
    "Ugh",
    "Tsk",
    "Ahem",
    "Phew",
    "Eek",
    "Gulp",
    # Common non-entity capitalized words in fiction
    "Chapter",
    "Part",
    "Volume",
    "Book",
    "Act",
    "Scene",
    "Sir",
    "Lord",
    "Lady",
    "Count",
    "Countess",
    "Duke",
    "Duchess",
    "Prince",
    "Princess",
    "King",
    "Queen",
    "Emperor",
    "Empress",
    "Viscount",
    "Baron",
    "Marquis",
    # Domain-suffix words — valid as suffixes, NOT as standalone entities
    "Sect",
    "Palace",
    "Hall",
    "Peak",
    "Clan",
    "Court",
    "Kingdom",
    "Empire",
    "Tower",
    "Mountain",
    "Valley",
    "Gate",
    "Formation",
    "Pill",
    "Art",
    "Technique",
    "Realm",
    "Stage",
    "Academy",
    "Guild",
    "Order",
    "Temple",
    "Church",
    "Castle",
    "Estate",
    "Manor",
    "Company",
    "Group",
    "Village",
    "City",
    "Province",
    "Territory",
    "Forest",
    "Lake",
    "River",
    "Island",
    "Fortress",
    "Fort",
    "Regiment",
    "Corps",
    "Legion",
    "Brigade",
    "Squad",
    "Sword",
    "Blade",
    "Shield",
    "Spear",
    "Staff",
    # Common fiction nouns that appear capitalised but aren't proper names
    "Hand",
    "Hands",
    "Care",
    "Disease",
    "Farm",
    "Field",
    "Money",
    "Deal",
    "Diet",
    "Earth",
    "God",
    "Goddess",
    "Gods",
    "High",
    "Sea",
    "Opening",
    "Resort",
    "Restaurant",
    "Trade",
    "Trading",
    "Merchant",
    "Turns",
    "Appeared",
    "Appears",
    "Acquiring",
    "Incurable",
    "Postpartum",
    "Extermination",
    "Uninvited",
    "Guests",
    "Mercenary",
    "Lords",
    "Watching",
    "Observing",
    "Seeing",
    "Behind",
    "Under",
    "Unlike",
    "Regarding",
    "Master",
    "Monster",
    "Monsters",
    "Knight",
    "Knights",
    "Soldier",
    "Soldiers",
    "Warrior",
    "Warriors",
}

# Words that, when they START a multi-word phrase, indicate a sentence fragment
# rather than an entity name (e.g. "As Ian", "But Dominic")
_STOP_PREFIXES: Set[str] = {
    "As",
    "At",
    "But",
    "If",
    "In",
    "Is",
    "Or",
    "So",
    "To",
    "By",
    "Of",
    "On",
    "An",
    "Do",
    "Up",
    "Even",
    "Although",
    "After",
    "Before",
    "Behind",
    "During",
    "Despite",
    "Since",
    "While",
    "When",
    "Where",
    "Whether",
    "Under",
    "Unlike",
    "Until",
    "Upon",
    "Within",
    "Without",
    "Watching",
    "Observing",
    "Seeing",
    "Regarding",
    "Following",
}

# Domain suffixes that strongly indicate organization/place/item names
_DOMAIN_SUFFIXES: List[str] = [
    "Sect",
    "Palace",
    "Hall",
    "Peak",
    "Clan",
    "Court",
    "Kingdom",
    "Empire",
    "Tower",
    "Mountain",
    "Valley",
    "Gate",
    "Formation",
    "Pill",
    "Art",
    "Technique",
    "Realm",
    "Stage",
    "Academy",
    "Guild",
    "Order",
    "Temple",
    "Church",
    "Castle",
    "Estate",
    "Manor",
    "Company",
    "Group",
    "Village",
    "City",
    "Province",
    "Territory",
    "Forest",
    "Lake",
    "River",
    "Island",
    "Fortress",
    "Fort",
    "Regiment",
    "Corps",
    "Legion",
    "Brigade",
    "Squad",
    "Sword",
    "Blade",
    "Shield",
    "Spear",
    "Staff",
]

# Titles that precede names — we want "Lord Theodore" as a unit, not just "Theodore"
_TITLE_PREFIXES: List[str] = [
    "Lord",
    "Lady",
    "Sir",
    "Count",
    "Countess",
    "Duke",
    "Duchess",
    "Prince",
    "Princess",
    "King",
    "Queen",
    "Emperor",
    "Empress",
    "Viscount",
    "Baron",
    "Baroness",
    "Marquis",
    "Master",
    "Mistress",
    "Captain",
    "Commander",
    "General",
    "Chief",
    "Elder",
    "Saint",
    "Prophet",
    "Sage",
    "Grand",
]

# Pre-compiled patterns
_TITLE_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(t) for t in _TITLE_PREFIXES)
    + r")\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
)
_MULTI_CAP_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
_SINGLE_CAP_PATTERN = re.compile(r"\b([A-Z][a-z]{2,})\b")
_SUFFIX_PATTERN = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:"
    + "|".join(re.escape(s) for s in _DOMAIN_SUFFIXES)
    + r"))\b"
)


def _get_sentence_context(text: str, match_start: int, match_end: int) -> str:
    """Extract the sentence containing the match for context."""
    # Walk backwards to find sentence start
    start = match_start
    while start > 0 and text[start - 1] not in ".!?\n":
        start -= 1
    # Walk forwards to find sentence end
    end = match_end
    while end < len(text) and text[end] not in ".!?\n":
        end += 1
    return text[start:end].strip()[:200]  # cap context at 200 chars


def _is_sentence_start(text: str, match_start: int) -> bool:
    """Check if the match is at the start of a sentence."""
    # Walk backwards past whitespace
    pos = match_start - 1
    while pos >= 0 and text[pos] in " \t":
        pos -= 1
    if pos < 0:
        return True
    return text[pos] in '.!?\n""\''


def extract_entities(chapters: List[Chapter], min_support: int = 2) -> List[Signal]:
    """Extract candidate entity names from chapters.

    Produces one Signal per occurrence. The Policy Miner handles deduplication,
    frequency counting, and confidence scoring.

    Args:
        chapters: Normalized chapter objects.
        min_support: Minimum number of chapters a name must appear in.
                     Used here only for filtering single-word names.

    Returns:
        List of Signal objects with type="entity".
    """
    signals: List[Signal] = []

    # Track chapter presence for single-word name filtering
    single_word_chapters: dict[str, set[int]] = {}

    for ch in chapters:
        text = ch.text

        # --- Title + Name combinations (e.g. "Lord Theodore", "Count Sinclair") ---
        for m in _TITLE_PATTERN.finditer(text):
            title = m.group(1)
            name = m.group(2)
            full = f"{title} {name}"
            ctx = _get_sentence_context(text, m.start(), m.end())
            signals.append(
                Signal(
                    text=full,
                    chapter=ch.chapter,
                    type="entity",
                    context=ctx,
                    extractor="entity.title_name",
                )
            )
            # Also emit the bare name as a signal
            if name not in _STOP_WORDS:
                signals.append(
                    Signal(
                        text=name,
                        chapter=ch.chapter,
                        type="entity",
                        context=ctx,
                        extractor="entity.title_name_bare",
                    )
                )

        # --- Domain-suffix phrases (e.g. "Rondo Trading Company") ---
        for m in _SUFFIX_PATTERN.finditer(text):
            phrase = m.group(0)
            # Skip if all words are stop words
            words = phrase.split()
            if all(w in _STOP_WORDS for w in words):
                continue
            ctx = _get_sentence_context(text, m.start(), m.end())
            signals.append(
                Signal(
                    text=phrase,
                    chapter=ch.chapter,
                    type="entity",
                    context=ctx,
                    extractor="entity.domain_suffix",
                )
            )

        # --- Multi-word capitalized phrases (e.g. "Han Jeong-min") ---
        for m in _MULTI_CAP_PATTERN.finditer(text):
            phrase = m.group(0)
            words = phrase.split()
            # Skip if first word is a stop word or stop prefix
            if words[0] in _STOP_WORDS or words[0] in _STOP_PREFIXES:
                continue
            # Skip if all words are stop words
            if all(w in _STOP_WORDS for w in words):
                continue
            # Skip if it's already captured by title or suffix patterns
            # (the miner will deduplicate, but we can reduce noise)
            if len(words) > 4:
                continue  # Unlikely to be an entity name
            ctx = _get_sentence_context(text, m.start(), m.end())
            signals.append(
                Signal(
                    text=phrase,
                    chapter=ch.chapter,
                    type="entity",
                    context=ctx,
                    extractor="entity.multi_cap",
                )
            )

        # --- Single capitalized words (character names like "Dominic", "Calron") ---
        for m in _SINGLE_CAP_PATTERN.finditer(text):
            word = m.group(0)
            if word in _STOP_WORDS:
                continue
            # Only count non-sentence-start occurrences to reduce noise
            if _is_sentence_start(text, m.start()):
                continue
            single_word_chapters.setdefault(word, set()).add(ch.chapter)
            ctx = _get_sentence_context(text, m.start(), m.end())
            signals.append(
                Signal(
                    text=word,
                    chapter=ch.chapter,
                    type="entity",
                    context=ctx,
                    extractor="entity.single_cap",
                )
            )

    # Filter single-word names by min_support (must appear in multiple chapters)
    if min_support > 1:
        passing_singles = {
            name for name, chaps in single_word_chapters.items() if len(chaps) >= min_support
        }
        signals = [
            s for s in signals if s.extractor != "entity.single_cap" or s.text in passing_singles
        ]

    return signals
