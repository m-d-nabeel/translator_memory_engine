"""Style module — voice fingerprinting and exemplar retrieval.

Provides:
    StyleProfile / Exemplar: dataclasses for the learned voice profile.
    compute_deterministic_profile: spaCy-based stylometry metrics.
    stylometry_delta: metric differences between generated and original.
    voice_richness_score: composite voice quality score.
    compute_llm_profile: LLM-analyzed qualitative style profile.
    extract_tendencies: editorial patterns from paired diffs.
    ExemplarIndex: embedding-based exemplar retrieval.
    build_exemplar_index: build index from good-translation chapters.
    classify_scene_type: heuristic scene classification.
"""

from translator_memory_engine.style.analyzer import (
    compute_deterministic_profile,
    compute_llm_profile,
    extract_tendencies,
    stylometry_delta,
    voice_richness_score,
)
from translator_memory_engine.style.exemplars import (
    ExemplarIndex,
    build_exemplar_index,
    classify_scene_type,
)
from translator_memory_engine.style.schema import SCENE_TYPES, Exemplar, StyleProfile

__all__ = [
    "StyleProfile",
    "Exemplar",
    "SCENE_TYPES",
    "compute_deterministic_profile",
    "stylometry_delta",
    "voice_richness_score",
    "compute_llm_profile",
    "extract_tendencies",
    "ExemplarIndex",
    "classify_scene_type",
    "build_exemplar_index",
]
