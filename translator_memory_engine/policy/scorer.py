"""Decomposed confidence scoring for policies.

Separated from the miner for testability. Each score component is a pure
function that can be tested independently.
"""


def score_frequency(occurrences: int, total_chapters: int) -> float:
    """What fraction of chapters contain this term?

    Higher frequency = more likely to be a real policy, not a one-off.
    """
    if total_chapters <= 0:
        return 0.0
    return min(occurrences / total_chapters, 1.0)


def score_consistency(canonical_count: int, total_variant_count: int) -> float:
    """How consistently is the canonical form used vs alternatives?

    If the translator always writes "Li Qing" (30 times) and never "Li Ching",
    consistency = 1.0. If it's 15 / 30, consistency = 0.5.
    """
    if total_variant_count <= 0:
        return 0.0
    return canonical_count / total_variant_count


def compute_confidence(
    scores: dict[str, float],
    base: float = 0.5,
    per_occurrence: float = 0.03,
    occurrence_count: int = 0,
    cap: float = 0.99,
) -> float:
    """Compute overall confidence from decomposed scores.

    Formula: base + per_occurrence * count, weighted by consistency.
    Capped at `cap`.

    The confidence model:
    - Starts at `base` (default 0.5)
    - Each occurrence adds `per_occurrence` (default 0.03)
    - Multiplied by consistency score (penalizes inconsistent usage)
    - Capped to prevent overconfidence
    """
    raw = base + per_occurrence * occurrence_count
    consistency = scores.get("consistency", 1.0)
    # Consistency acts as a multiplier: inconsistent terms get lower confidence
    adjusted = raw * (0.5 + 0.5 * consistency)
    return min(adjusted, cap)
