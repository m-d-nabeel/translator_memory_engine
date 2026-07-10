"""Honorific and title extraction — Layer 1 (lexical).

Detects source-language honorific patterns retained or translated in
the target text. Source-aware: patterns differ for Chinese, Japanese,
and Korean source material.
"""

import re
from typing import List

from translator_memory_engine.models import Chapter
from translator_memory_engine.extract.signals import Signal


# --- Source-specific honorific/title patterns ---

# Korean source patterns (retained in translation)
_KR_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(hyung|Hyung)\b'),
    re.compile(r'\b(noona|Noona)\b'),
    re.compile(r'\b(oppa|Oppa)\b'),
    re.compile(r'\b(unni|Unni)\b'),
    re.compile(r'\b(ahjussi|Ahjussi)\b'),
    re.compile(r'\b(sunbae|Sunbae|senpai|Senpai)\b'),
    re.compile(r'\b(hubae|Hubae)\b'),
    re.compile(r'\b(nim|Nim)\b'),  # often suffix: -nim
    re.compile(r'\b(ajumma|Ajumma)\b'),
]

# Japanese source patterns (retained honorific suffixes)
_JP_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b\w+-san\b'),
    re.compile(r'\b\w+-sama\b'),
    re.compile(r'\b\w+-kun\b'),
    re.compile(r'\b\w+-chan\b'),
    re.compile(r'\b\w+-sensei\b'),
    re.compile(r'\b\w+-senpai\b'),
    re.compile(r'\b\w+-dono\b'),
]

# Chinese source patterns (translated honorifics/titles common in xianxia/wuxia)
_CN_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(Senior\s+Brother|Junior\s+Brother)\b'),
    re.compile(r'\b(Senior\s+Sister|Junior\s+Sister)\b'),
    re.compile(r'\b(Elder\s+Brother|Elder\s+Sister)\b'),
    re.compile(r'\b(Martial\s+Uncle|Martial\s+Aunt)\b'),
    re.compile(r'\b(Martial\s+Brother|Martial\s+Sister)\b'),
    re.compile(r'\b(Dao\s+Friend|Fellow\s+Daoist)\b'),
    re.compile(r'\b(Sect\s+Master|Sect\s+Leader)\b'),
    re.compile(r'\b(Young\s+Master|Young\s+Miss)\b'),
    re.compile(r'\b(Patriarch|Matriarch)\b'),
    re.compile(r'\b(Ancestor)\b'),
]

# Universal patterns (translated titles used regardless of source)
_UNIVERSAL_TITLE_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(Your\s+Excellency)\b'),
    re.compile(r'\b(Your\s+Majesty)\b'),
    re.compile(r'\b(Your\s+Highness)\b'),
    re.compile(r'\b(Your\s+Honor)\b'),
    re.compile(r'\b(Your\s+Grace)\b'),
    re.compile(r'\b(Your\s+Lordship)\b'),
    re.compile(r'\b(My\s+Lord)\b', re.IGNORECASE),
    re.compile(r'\b(My\s+Lady)\b', re.IGNORECASE),
    re.compile(r'\b(Sir\s+Knight)\b'),
]

_SOURCE_PATTERNS = {
    "korean": _KR_PATTERNS,
    "japanese": _JP_PATTERNS,
    "chinese": _CN_PATTERNS,
}


def _get_context(text: str, start: int, end: int) -> str:
    """Extract surrounding sentence for context."""
    ctx_start = start
    while ctx_start > 0 and text[ctx_start - 1] not in '.!?\n':
        ctx_start -= 1
    ctx_end = end
    while ctx_end < len(text) and text[ctx_end] not in '.!?\n':
        ctx_end += 1
    return text[ctx_start:ctx_end].strip()[:200]


def extract_honorifics(
    chapters: List[Chapter],
    source_languages: List[str] | None = None,
) -> List[Signal]:
    """Extract honorific and title patterns from chapters.

    Args:
        chapters: Normalized chapter objects.
        source_languages: List of source languages to check patterns for.
            If None, checks all patterns. Values: "korean", "japanese", "chinese".

    Returns:
        List of Signal objects with type="honorific".
    """
    signals: List[Signal] = []

    # Build pattern list based on source languages
    patterns: List[re.Pattern] = list(_UNIVERSAL_TITLE_PATTERNS)
    if source_languages:
        for lang in source_languages:
            lang_key = lang.lower()
            if lang_key in _SOURCE_PATTERNS:
                patterns.extend(_SOURCE_PATTERNS[lang_key])
    else:
        # Check all source-specific patterns
        for lang_patterns in _SOURCE_PATTERNS.values():
            patterns.extend(lang_patterns)

    for ch in chapters:
        text = ch.text

        for pat in patterns:
            for m in pat.finditer(text):
                honorific = m.group(0)
                ctx = _get_context(text, m.start(), m.end())
                signals.append(Signal(
                    text=honorific, chapter=ch.chapter, type="honorific",
                    context=ctx, extractor="honorific.pattern",
                ))

    return signals
