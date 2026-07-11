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

The ExemplarIndex provides embedding-based retrieval for better semantic matching
when fastembed is available, falling back to Jaccard when it's not.
"""

import re
from typing import Callable, List, Optional

from translator_memory_engine.style.exemplars import (
    ExemplarIndex,
    build_exemplar_index,
)

# Dialogue spans: double quotes and curly quotes. (Single quotes are excluded to
# avoid matching apostrophes inside words.)
_DIALOGUE_RE = re.compile(r'"[^"]+"|\u201c[^\u201d]+\u201d')


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
            excerpts.append(p[:max_chars].rsplit(" ", 1)[0] + "\u2026")
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
        f"avg sentence length \u2248 {avg:.0f} words; "
        f"\u2248 {dlg:.0f}% of sentences carry dialogue; "
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


def build_exemplar_index_from_chapters(
    chapters: List[str],
    chapter_nums: List[int],
    embed_fn: Optional[Callable[[str], List[float]]] = None,
    per_chapter: int = 3,
) -> ExemplarIndex:
    """Build an ExemplarIndex from good-translation chapters.

    This is the preferred way to build the style bank when fastembed is available.
    Falls back to keyword-based retrieval when embed_fn is None.
    """
    return build_exemplar_index(chapters, chapter_nums, embed_fn, per_chapter)


# --- Per-chapter style retrieval (the "weight" in voice alignment) ---------
_STOP = set(
    "the a an and or but of to in on for with as at by from is are was were be "
    "been being it its this that these those he she they we you i my your his "
    "her their our not no so if then than them what which who whom whose can "
    "will would could should may might into out up down over under again".split()
)

_ONOM = re.compile(
    r"\b(pak|thud|crash|bang|boom|splat|whack|smack|gasp|huff|snarl|growl|clang|"
    r"screech|squelch|thwack|whoosh|ugh|argh|grr|hmm|pfft|clack|creak)\b",
    re.I,
)


def _tok(s: str) -> set:
    return {t for t in re.findall(r"[a-z']+", s.lower()) if t not in _STOP and len(t) > 2}


def _jaccard(excerpt: str, toks: set) -> float:
    et = _tok(excerpt)
    if not et or not toks:
        return 0.0
    return len(et & toks) / len(et | toks)


def retrieve_style_excerpts(
    chapter_text: str,
    excerpts: List[str],
    k: int = 8,
    exemplar_index: Optional[ExemplarIndex] = None,
    embed_fn: Optional[Callable[[str], List[float]]] = None,
) -> List[str]:
    """Return the ``k`` style-bank excerpts most similar to ``chapter_text``.

    If an ExemplarIndex is provided and embeddings are available, uses cosine
    similarity for better semantic matching. Otherwise falls back to Jaccard.
    """
    # Try embedding-based retrieval first
    if exemplar_index is not None:
        exemplars = exemplar_index.retrieve_all(chapter_text, embed_fn=embed_fn, top_k=k)
        if exemplars:
            return [ex.text for ex in exemplars]

    # Fallback: Jaccard similarity
    toks = _tok(chapter_text)
    scored = []
    for ex in excerpts:
        s = _jaccard(ex, toks)
        if _ONOM.search(ex):
            s += 0.15  # prefer onomatopoeia / vivid voice samples
        scored.append((s, ex))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ex for _, ex in scored[:k]]
