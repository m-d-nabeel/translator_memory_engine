"""Style bank — Language Memory (lite).

Builds a voice profile from good-translation chapters so the rewriter can preserve
the translator's style on chapters that have NO original to reference (PLAN §15, D11).

The profile is a list of representative excerpts (dialogue- and voice-rich passages)
plus a short measurable-statistics summary. The rewriter feeds these to the LLM as
few-shot style anchors when no published translation exists for the chapter being
repaired. This keeps the engine learn/apply/evaluate-by-availability rather than by
chapter pairing (D11: chapters 40-41 and 51+ must still be servable from the bank).

The statistics here are intentionally cheap (string heuristics) — the heavy
stylometry lives in the evaluation stack (spaCy, separate from extract/rewrite).
"""

import re
from typing import List

# Dialogue spans: double quotes and curly quotes. (Single quotes are excluded to
# avoid matching apostrophes inside words.)
_DIALOGUE_RE = re.compile(r'"[^"]+"|“[^”]+”')


def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _pick_excerpts(text: str, per_chapter: int = 2, max_chars: int = 350) -> List[str]:
    """Return the most voice-rich paragraphs from a chapter (dialogue first)."""
    paras = _paragraphs(text)
    if not paras:
        return []
    ranked = sorted(
        paras,
        key=lambda p: (len(_DIALOGUE_RE.findall(p)), len(p)),
        reverse=True,
    )
    excerpts: List[str] = []
    for p in ranked:
        if len(excerpts) >= per_chapter:
            break
        if len(p) <= max_chars:
            excerpts.append(p)
        else:
            excerpts.append(p[:max_chars].rsplit(" ", 1)[0] + "…")
    return excerpts


def _stats(chapters: List[str]) -> str:
    sentences = 0
    words = 0
    dialogue = 0
    for t in chapters:
        for s in re.split(r"(?<=[.!?])\s+", t):
            s = s.strip()
            if not s:
                continue
            sentences += 1
            words += len(s.split())
            if _DIALOGUE_RE.search(s):
                dialogue += 1
    if sentences == 0:
        return ""
    avg = words / sentences
    dlg = 100 * dialogue / sentences
    return (
        f"Measured style across {len(chapters)} good-translation chapters: "
        f"avg sentence length ≈ {avg:.0f} words; "
        f"≈ {dlg:.0f}% of sentences carry dialogue; "
        f"translator favours close-third-person narration with snappy, "
        f"colloquial dialogue."
    )


def build_style_bank(
    chapters: List[str],
    per_chapter: int = 2,
    max_chars: int = 350,
    include_stats: bool = True,
) -> List[str]:
    """Return a voice profile (list of excerpt strings) from good-translation chapters.

    Each entry is either a representative excerpt or, as the final entry when
    ``include_stats`` is set, a one-line statistics summary.
    """
    if not chapters:
        return []
    profile: List[str] = []
    for ch in chapters:
        profile.extend(_pick_excerpts(ch, per_chapter=per_chapter, max_chars=max_chars))
    if include_stats:
        s = _stats(chapters)
        if s:
            profile.append(s)
    return profile
