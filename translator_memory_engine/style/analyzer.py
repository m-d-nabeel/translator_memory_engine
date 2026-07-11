"""Style analyzer — deterministic stylometry and LLM-based profile extraction.

compute_deterministic_profile() runs spaCy to produce cheap, verifiable metrics.
compute_llm_profile() calls an LLM to extract qualitative style notes.
extract_tendencies() analyzes paired MTL→original diffs for editorial patterns.
"""

import re
from collections import Counter
from typing import Callable, Dict, List

import spacy

from translator_memory_engine.style.schema import StyleProfile

_NLP = None


def _nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


_DIALOGUE_RE = re.compile(r'"[^"]+"|\u201c[^\u201d]+\u201d')
_CONTRACTION_RE = re.compile(
    r"\b(?:can't|won't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't|"
    r"hasn't|haven't|hadn't|couldn't|shouldn't|wouldn't|mustn't|needn't|"
    r"let's|that's|who's|what's|here's|there's|where's|when's|how's|"
    r"I'm|you're|he's|she's|it's|we're|they're|I've|you've|we've|they've|"
    r"I'll|you'll|he'll|she'll|it'll|we'll|they'll|I'd|you'd|he'd|she'd|we'd|they'd)\b",
    re.IGNORECASE,
)
_CONTENT_RE = re.compile(r"[a-z']{3,}")


def _sentences(text: str) -> List[str]:
    doc = _nlp()(text)
    return [s.text.strip() for s in doc.sents if s.text.strip()]


def compute_deterministic_profile(text: str) -> Dict[str, float]:
    """Compute stylometry metrics using spaCy (no LLM).

    Returns a dict of:
        avg_sentence_length: mean words per sentence
        sentence_length_variance: variance of words-per-sentence
        lexical_richness: type-token ratio (unique content words / total content words)
        hapax_ratio: words appearing once / total content words
        contraction_rate: contractions per sentence
        dialog_share: fraction of sentences containing dialogue
    """
    sents = _sentences(text)
    if not sents:
        return {}

    words_per_sent = []
    all_content_tokens: List[str] = []
    contraction_count = 0
    dialogue_count = 0

    for s in sents:
        tokens = s.split()
        words_per_sent.append(len(tokens))

        content = _CONTENT_RE.findall(s.lower())
        all_content_tokens.extend(content)

        if _CONTRACTION_RE.search(s):
            contraction_count += 1
        if _DIALOGUE_RE.search(s):
            dialogue_count += 1

    n_sents = len(sents)
    n_words = len(all_content_tokens)

    avg_len = sum(words_per_sent) / n_sents
    variance = sum((w - avg_len) ** 2 for w in words_per_sent) / n_sents if n_sents > 1 else 0.0

    token_counts = Counter(all_content_tokens)
    ttr = len(token_counts) / n_words if n_words > 0 else 0.0
    hapax = sum(1 for c in token_counts.values() if c == 1) / n_words if n_words > 0 else 0.0

    return {
        "avg_sentence_length": round(avg_len, 2),
        "sentence_length_variance": round(variance, 2),
        "lexical_richness": round(ttr, 4),
        "hapax_ratio": round(hapax, 4),
        "contraction_rate": round(contraction_count / n_sents, 4),
        "dialog_share": round(dialogue_count / n_sents, 4),
    }


def stylometry_delta(gen: str, orig: str) -> Dict[str, float]:
    """Absolute difference in deterministic metrics between generated and original."""
    gen_p = compute_deterministic_profile(gen)
    orig_p = compute_deterministic_profile(orig)
    all_keys = set(gen_p) | set(orig_p)
    return {k: round(abs(gen_p.get(k, 0.0) - orig_p.get(k, 0.0)), 4) for k in all_keys}


def voice_richness_score(text: str) -> float:
    """Composite score: higher = richer voice (dialogue, TTR, sentence variance)."""
    p = compute_deterministic_profile(text)
    if not p:
        return 0.0
    ttr = p.get("lexical_richness", 0.0)
    dialog = p.get("dialog_share", 0.0)
    # Normalize sentence-length variance (cap at 500 for scaling)
    slv = min(p.get("sentence_length_variance", 0.0), 500.0) / 500.0
    return round(0.4 * ttr + 0.3 * dialog + 0.3 * slv, 4)


def compute_llm_profile(
    text: str,
    llm_fn: Callable[[str], str],
) -> StyleProfile:
    """LLM-analyzed style profile: register, narration notes, dialogue notes.

    ``llm_fn`` is a callable that takes a prompt string and returns the LLM's
    text response.
    """
    prompt = (
        "Analyze the following translated web-novel text. Return a brief style "
        "profile with these fields (use the exact labels):\n"
        "REGISTER: (one line: narrative POV, formality, tone)\n"
        "NARRATION: (2-3 sentences on narration patterns: sentence rhythm, "
        "vocabulary level, use of metaphor, etc.)\n"
        "DIALOGUE: (2-3 sentences on dialogue patterns: register shifts, "
        "punctuation habits, formality, etc.)\n\n"
        f"TEXT (first ~2000 chars):\n{text[:2000]}"
    )
    raw = llm_fn(prompt)

    register = ""
    narration = ""
    dialogue = ""
    for line in raw.splitlines():
        low = line.strip().lower()
        if low.startswith("register:"):
            register = line.split(":", 1)[1].strip()
        elif low.startswith("narration:"):
            narration = line.split(":", 1)[1].strip()
        elif low.startswith("dialogue:"):
            dialogue = line.split(":", 1)[1].strip()

    diagnostics = compute_deterministic_profile(text)
    return StyleProfile(
        register=register,
        narration_notes=narration,
        dialogue_notes=dialogue,
        diagnostics=diagnostics,
    )


def extract_tendencies(
    mtl_text: str,
    original_text: str,
    llm_fn: Callable[[str], str],
) -> Dict[str, str]:
    """Extract editorial tendencies from a Case 1 paired diff.

    ``llm_fn`` is a callable that takes a prompt string and returns the LLM's
    text response. Returns a dict like {"passive→active": "...", ...}.
    """
    prompt = (
        "Compare this MACHINE TRANSLATION (A) with the HUMAN TRANSLATION (B) of "
        "the same chapter. Identify the key editorial patterns the human translator "
        "applied. Return a list of tendencies, each on its own line, in the format:\n"
        "LABEL: description\n\n"
        "Examples of labels: passive→active, stilted→colloquial, verbose→concise, "
        "formal→informal, literal→idiomatic\n\n"
        f"=== (A) MACHINE TRANSLATION (first ~1500 chars) ===\n{mtl_text[:1500]}\n\n"
        f"=== (B) HUMAN TRANSLATION (first ~1500 chars) ===\n{original_text[:1500]}"
    )
    raw = llm_fn(prompt)

    tendencies: Dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            label, _, desc = line.partition(":")
            label = label.strip()
            desc = desc.strip()
            if label and desc:
                tendencies[label] = desc
    return tendencies
