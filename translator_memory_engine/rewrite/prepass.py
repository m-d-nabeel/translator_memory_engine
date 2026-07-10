"""Deterministic Pre-pass (PLAN.md §8, Mechanism 1).

High-confidence (`applies: "deterministic"`) policies are applied as literal
string substitution *before* the LLM sees the text. This is the most reliable
path to terminology consistency and does not depend on the LLM following
instructions. It handles the bulk of Layer 1 (entity names, honorifics).

Only winning, deterministic, non-rejected policies are applied. The losers of
any conflict are skipped (resolved by the Conflict Resolver). A change trace
is returned for every edit (PLAN.md §11 explainability).
"""

from typing import List, Dict, Any

from translator_memory_engine.policy import Policy
from translator_memory_engine.rewrite.conflict import Resolution, SpanMatch


def apply_prepass(
    text: str,
    resolution: Resolution,
) -> tuple[str, List[Dict[str, Any]]]:
    """Apply deterministic winner substitutions to `text`.

    Args:
        text: The (pre-pass) MTL passage.
        resolution: Output of the Conflict Resolver.

    Returns:
        (rewritten_text, change_trace)
        change_trace is a list of dicts: original, output, policy, confidence,
        evidence, span.
    """
    # Keep only deterministic, non-rejected winners, sorted by span start desc
    # (desc so earlier replacements don't shift later indices).
    winners: List[SpanMatch] = [
        w for w in resolution.winners
        if w.policy.applies == "deterministic" and not w.policy.llm_rejected
    ]
    winners.sort(key=lambda w: w.start, reverse=True)

    trace: List[Dict[str, Any]] = []
    out = text
    for w in winners:
        render_as = w.policy.action.get("render_as", w.policy.trigger)
        original = out[w.start:w.end]
        # Only record if something actually changes
        if original != render_as:
            trace.append({
                "original": original,
                "output": render_as,
                "policy": w.policy.id,
                "trigger": w.policy.trigger,
                "confidence": w.policy.confidence,
                "evidence": w.policy.evidence,
                "span": [w.start, w.end],
            })
        out = out[:w.start] + render_as + out[w.end:]

    return out, trace
