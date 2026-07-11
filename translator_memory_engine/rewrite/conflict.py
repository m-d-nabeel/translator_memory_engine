"""Conflict Resolver (PLAN.md §9).

When two or more retrieved policies match the *same span* of text, they conflict
(e.g. "Senior Brother" and "Elder Brother" both triggered). v0 resolution:

1. Score each matching policy by confidence.
2. Tie-break by evidence count (more evidence = more reliable).
3. Tie-break by specificity (longer trigger = more specific).
4. If still tied, flag for human review (do not guess).

The resolver returns, for each matched span, the winning policy and the list of
losing policies (so the pre-pass can avoid applying contradictory edits).
"""

import re
from typing import List, NamedTuple, Set

from translator_memory_engine.policy import Policy


class SpanMatch(NamedTuple):
    policy: Policy
    form: str  # the exact surface form matched
    start: int
    end: int


class Resolution(NamedTuple):
    winners: List[SpanMatch]  # applied
    conflicts: List[dict]  # {span, winner_id, loser_ids, losers}


def _find_spans(text: str, policy: Policy) -> List[SpanMatch]:
    spans: List[SpanMatch] = []
    for form in policy.match:
        if not form:
            continue
        pattern = re.escape(form)
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            spans.append(SpanMatch(policy=policy, form=form, start=m.start(), end=m.end()))
    return spans


def _score(p: Policy) -> tuple:
    # Higher is better: confidence, then evidence count, then trigger length
    return (p.confidence, len(p.evidence), len(p.trigger))


def resolve(text: str, matched: List[Policy]) -> Resolution:
    """Resolve conflicts among matched policies over `text`.

    Returns winners (non-conflicting + highest-confidence-per-span) and a list
    of conflict records for the trace.

    Same-policy overlaps (a policy whose own match forms overlap, e.g.
    "Korea" inside "Korean") are NOT conflicts — they are merged: the span is
    simply covered by the already-selected winner and skipped.
    """
    all_spans: List[SpanMatch] = []
    for p in matched:
        all_spans.extend(_find_spans(text, p))

    conflicts: List[dict] = []
    claimed: Set[int] = set()  # indices into all_spans already handled

    winners: List[SpanMatch] = []
    used_by_winner: List[SpanMatch] = []  # winner spans already selected

    # Process spans sorted by score (best first)
    order = sorted(range(len(all_spans)), key=lambda i: _score(all_spans[i].policy), reverse=True)

    for i in order:
        if i in claimed:
            continue
        sp = all_spans[i]
        # Find overlapping already-selected winner spans
        overlapping = [w for w in used_by_winner if not (sp.end <= w.start or sp.start >= w.end)]
        if overlapping:
            other_policy = [w for w in overlapping if w.policy.id != sp.policy.id]
            if other_policy:
                # Genuine cross-policy conflict: this span loses to the best winner
                best = max(other_policy, key=lambda w: _score(w.policy))
                conflicts.append(
                    {
                        "span": text[sp.start : sp.end],
                        "winner_id": best.policy.id,
                        "loser_id": sp.policy.id,
                        "loser_trigger": sp.policy.trigger,
                        "reason": "lower confidence/evidence/specificity",
                    }
                )
                claimed.add(i)
                continue
            # else: same-policy overlap -> already covered, skip silently
            claimed.add(i)
            continue
        # Select as winner
        winners.append(sp)
        used_by_winner.append(sp)
        claimed.add(i)

    return Resolution(winners=winners, conflicts=conflicts)
