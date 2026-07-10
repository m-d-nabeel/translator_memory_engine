"""Alignment evaluation (PLAN §13, D11).

Measures how close a generated (repaired) chapter is to its target, using a
dependency-free TF-IDF cosine similarity so the eval stack stays independent of
the extract/rewrite LLM stack.

Two tiers, by data availability (D11: learn/apply/evaluate by availability, not by
chapter pairing):

  * Tier-1 (paired): an original translation exists for the chapter. Compare
        sim(gen, orig)  vs  sim(mtl, orig)
    A good repair should raise closeness to the original over the raw MTL.
  * Tier-2 (unpaired / proxy): no original for the chapter (e.g. 40-41, 51+).
    Compare the generated text against the learned *style bank* (voice excerpts)
    and report name-adherence against the glossary's canonical forms.
"""

import math
import re
from collections import Counter
from typing import Dict, List, Optional


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z']+", text.lower())


def _idf(docs: List[str]) -> Dict[str, float]:
    n = len(docs)
    df: Counter = Counter()
    for d in docs:
        for t in set(_tokenize(d)):
            df[t] += 1
    # Smoothed idf.
    return {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}


def _vector(tokens: List[str], idf: Dict[str, float]) -> Dict[str, float]:
    tf: Counter = Counter(tokens)
    vec = {t: tf[t] * idf.get(t, 0.0) for t in tf}
    norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
    return {t: w / norm for t, w in vec.items()}


def cosine(a: str, b: str) -> float:
    """Cosine similarity between two texts (TF-IDF, dependency-free)."""
    idf = _idf([a, b])
    va = _vector(_tokenize(a), idf)
    vb = _vector(_tokenize(b), idf)
    common = set(va) & set(vb)
    return round(sum(va[t] * vb[t] for t in common), 4)


def align_paired(generated: str, original: str, mtl: str) -> Dict[str, float]:
    """Tier-1: generated vs original, benchmarked against raw MTL vs original."""
    sim_gen = cosine(generated, original)
    sim_mtl = cosine(mtl, original)
    return {
        "sim_generated_original": sim_gen,
        "sim_mtl_original": sim_mtl,
        "delta_vs_mtl": round(sim_gen - sim_mtl, 4),
    }


def align_unpaired(
    generated: str,
    style_profile: List[str],
    canonical: List[str],
) -> Dict[str, Optional[float]]:
    """Tier-2 proxy: closeness to the learned voice + glossary name adherence."""
    profile_text = "\n".join(style_profile)
    sim_style = cosine(generated, profile_text) if profile_text else 0.0
    gen_low = generated.lower()
    present = [c for c in canonical if c.lower() in gen_low]
    adherence = (len(present) / len(canonical)) if canonical else None
    return {
        "sim_generated_stylebank": round(sim_style, 4),
        "names_total": len(canonical),
        "names_present": len(present),
        "name_adherence": round(adherence, 4) if adherence is not None else None,
    }
