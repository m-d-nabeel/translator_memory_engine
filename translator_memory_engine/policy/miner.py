"""Policy Miner — Signals → verified Policies.

Three stages:
1. Aggregation: group signals by normalized text
2. Variant clustering: merge near-duplicates, pick canonical form
3. Confidence scoring: compute frequency, consistency, overall confidence

This is the heart of the system (PLAN.md §7).
"""

import re
import unicodedata
from collections import defaultdict
from typing import List, Dict, Set, Tuple

from translator_memory_engine.extract.signals import Signal
from translator_memory_engine.policy import Policy
from translator_memory_engine.policy.scorer import (
    score_frequency,
    score_consistency,
    compute_confidence,
)


def _normalize(text: str) -> str:
    """Normalize text for grouping: lowercase, strip accents, collapse whitespace/hyphens."""
    text = unicodedata.normalize("NFKD", text)
    # Remove accent marks
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    # Collapse hyphens and whitespace
    text = re.sub(r'[-\s]+', ' ', text)
    # Remove possessive
    text = re.sub(r"'s\b", "", text)
    return text


def _edit_distance(a: str, b: str) -> int:
    """Simple Levenshtein edit distance."""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[len(b)]


def _normalized_edit_distance(a: str, b: str) -> float:
    """Edit distance normalized by max length. 0.0 = identical, 1.0 = completely different."""
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0
    return _edit_distance(a, b) / max_len


# ----------------------------------------------------------------------- #
# Stage 1: Aggregation
# ----------------------------------------------------------------------- #

def _aggregate_signals(signals: List[Signal]) -> Dict[str, List[Signal]]:
    """Group signals by normalized text.

    Returns a dict mapping normalized form → list of signals.
    Each group represents a candidate policy.
    """
    groups: Dict[str, List[Signal]] = defaultdict(list)
    for s in signals:
        key = _normalize(s.text)
        groups[key].append(s)
    return groups


# ----------------------------------------------------------------------- #
# Stage 2: Variant clustering
# ----------------------------------------------------------------------- #

def _cluster_variants(
    groups: Dict[str, List[Signal]],
    similarity_threshold: float = 0.3,
) -> Dict[str, List[Signal]]:
    """Merge groups whose normalized keys are near-duplicates.

    Uses normalized edit distance. If two keys are within threshold,
    the group with more signals absorbs the other.

    Args:
        groups: Output of _aggregate_signals.
        similarity_threshold: Max normalized edit distance to merge.

    Returns:
        Merged groups.
    """
    keys = sorted(groups.keys())
    merged: Dict[str, List[Signal]] = {}
    absorbed: Set[str] = set()

    for i, k1 in enumerate(keys):
        if k1 in absorbed:
            continue
        cluster = list(groups[k1])
        for j in range(i + 1, len(keys)):
            k2 = keys[j]
            if k2 in absorbed:
                continue
            if _normalized_edit_distance(k1, k2) <= similarity_threshold:
                cluster.extend(groups[k2])
                absorbed.add(k2)
        merged[k1] = cluster

    return merged


def _pick_canonical(signals: List[Signal]) -> Tuple[str, List[str]]:
    """Pick the canonical form (most frequent variant) and collect aliases.

    Returns:
        (canonical_form, list_of_aliases)
    """
    # Count each exact surface form
    form_counts: Dict[str, int] = defaultdict(int)
    for s in signals:
        form_counts[s.text] += 1

    # Most frequent = canonical
    canonical = max(form_counts, key=form_counts.get)  # type: ignore
    aliases = [form for form in form_counts if form != canonical]

    return canonical, aliases


# ----------------------------------------------------------------------- #
# Stage 3: Scoring + Policy construction
# ----------------------------------------------------------------------- #

def _infer_type(signals: List[Signal]) -> str:
    """Infer the policy type from the signal extractors that produced it."""
    extractors = {s.extractor for s in signals}
    types = {s.type for s in signals}

    if "honorific" in types:
        return "honorific"
    if any(e.startswith("terminology.") for e in extractors):
        return "terminology"
    return "entity-naming"


def mine_policies(
    signals: List[Signal],
    total_chapters: int,
    min_support: int = 2,
    min_confidence: float = 0.4,
    similarity_threshold: float = 0.3,
    confidence_base: float = 0.5,
    confidence_per_occurrence: float = 0.03,
    confidence_cap: float = 0.99,
    deterministic_threshold: float = 0.8,
) -> List[Policy]:
    """Convert raw signals into verified policies.

    Args:
        signals: Raw signals from extractors.
        total_chapters: Total number of chapters in the corpus.
        min_support: Minimum chapters a candidate must appear in.
        min_confidence: Minimum confidence to emit a policy.
        similarity_threshold: Max edit distance for variant clustering.
        confidence_base: Base confidence score.
        confidence_per_occurrence: Confidence increment per occurrence.
        confidence_cap: Maximum confidence score.
        deterministic_threshold: Confidence above which policy is deterministic.

    Returns:
        List of Policy objects, sorted by confidence (descending).
    """
    # Stage 1: Aggregate
    groups = _aggregate_signals(signals)

    # Stage 2: Cluster variants
    clustered = _cluster_variants(groups, similarity_threshold=similarity_threshold)

    # Stage 3: Score and build policies
    policies: List[Policy] = []
    policy_id = 0

    for _norm_key, group_signals in clustered.items():
        # Check min_support: how many distinct chapters?
        chapters_present: Set[int] = {s.chapter for s in group_signals}
        if len(chapters_present) < min_support:
            continue

        # Pick canonical form and aliases
        canonical, aliases = _pick_canonical(group_signals)

        # Count occurrences
        form_counts: Dict[str, int] = defaultdict(int)
        for s in group_signals:
            form_counts[s.text] += 1
        total_occurrences = sum(form_counts.values())
        canonical_count = form_counts[canonical]

        # Compute scores
        freq = score_frequency(len(chapters_present), total_chapters)
        consistency = score_consistency(canonical_count, total_occurrences)

        scores = {
            "frequency": round(freq, 3),
            "consistency": round(consistency, 3),
            "context": 1.0,  # placeholder for v0
        }

        confidence = compute_confidence(
            scores,
            base=confidence_base,
            per_occurrence=confidence_per_occurrence,
            occurrence_count=total_occurrences,
            cap=confidence_cap,
        )

        if confidence < min_confidence:
            continue

        # Build match list: canonical + all aliases
        match_forms = [canonical] + sorted(set(aliases))

        # Determine applies mode
        applies = "deterministic" if confidence >= deterministic_threshold else "prompted"

        # Infer type
        policy_type = _infer_type(group_signals)

        policy_id += 1
        policies.append(Policy(
            id=f"p_{policy_id:03d}",
            type=policy_type,
            trigger=canonical,
            match=match_forms,
            action={"render_as": canonical},
            applies=applies,
            confidence=round(confidence, 3),
            scores=scores,
            evidence=sorted(chapters_present),
        ))

    # Sort by confidence descending
    policies.sort(key=lambda p: p.confidence, reverse=True)

    # Re-number IDs after sorting
    for i, p in enumerate(policies, start=1):
        p.id = f"p_{i:03d}"

    return policies
