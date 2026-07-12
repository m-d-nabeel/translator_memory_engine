"""Tests for stylometry analysis (style/analyzer.py)."""

from translator_memory_engine.style.analyzer import (
    compute_deterministic_profile,
    stylometry_delta,
    voice_richness_score,
)


class TestDeterministicProfile:
    def test_basic_metrics(self):
        text = '"Hello there!" she said. The boy ran across the field. He didn\'t stop. "Come back!" she shouted.'
        p = compute_deterministic_profile(text)
        assert "avg_sentence_length" in p
        assert "sentence_length_variance" in p
        assert "lexical_richness" in p
        assert "contraction_rate" in p
        assert "dialog_share" in p
        assert p["avg_sentence_length"] > 0
        assert p["dialog_share"] > 0

    def test_empty_text(self):
        p = compute_deterministic_profile("")
        assert p == {}

    def test_contraction_detection(self):
        text = "He didn't stop. She wouldn't wait. They can't leave."
        p = compute_deterministic_profile(text)
        assert p["contraction_rate"] > 0

    def test_dialog_detection(self):
        text = '"Hello!" she said. He ran across the field.'
        p = compute_deterministic_profile(text)
        assert p["dialog_share"] > 0


class TestStylometryDelta:
    def test_identical_texts(self):
        text = "He ran. She walked. They played."
        d = stylometry_delta(text, text)
        assert all(v == 0.0 for v in d.values())

    def test_different_texts(self):
        gen = "He ran fast. She walked slowly."
        orig = "The man sprinted. The woman strolled leisurely through the park."
        d = stylometry_delta(gen, orig)
        assert any(v > 0 for v in d.values())


class TestVoiceRichnessScore:
    def test_returns_float(self):
        text = '"Hello!" she said. He ran across the field. She didn\'t stop. He wondered what to do next.'
        score = voice_richness_score(text)
        assert isinstance(score, float)
        assert 0 <= score <= 1

    def test_empty_text(self):
        score = voice_richness_score("")
        assert score == 0.0
