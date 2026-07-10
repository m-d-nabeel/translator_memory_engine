"""Tests for Policy Miner."""

from translator_memory_engine.extract.signals import Signal
from translator_memory_engine.policy.miner import mine_policies, _normalize, _normalized_edit_distance
from translator_memory_engine.policy.scorer import score_frequency, score_consistency, compute_confidence


class TestNormalization:
    def test_lowercases(self):
        assert _normalize("Lord Theodore") == "lord theodore"

    def test_collapses_whitespace(self):
        assert _normalize("Lord  Theodore") == "lord theodore"

    def test_collapses_hyphens(self):
        assert _normalize("Li-Qing") == "li qing"

    def test_removes_possessive(self):
        assert _normalize("Devil's Hand") == "devil hand"


class TestEditDistance:
    def test_identical(self):
        assert _normalized_edit_distance("abc", "abc") == 0.0

    def test_completely_different(self):
        assert _normalized_edit_distance("abc", "xyz") == 1.0

    def test_partial_similarity(self):
        dist = _normalized_edit_distance("tianxuan", "tian xuan")
        assert 0.0 < dist < 0.5  # Close enough to cluster


class TestScoring:
    def test_frequency(self):
        assert score_frequency(10, 30) == 10 / 30
        assert score_frequency(30, 30) == 1.0
        assert score_frequency(0, 30) == 0.0
        assert score_frequency(5, 0) == 0.0

    def test_consistency(self):
        assert score_consistency(30, 30) == 1.0
        assert score_consistency(15, 30) == 0.5
        assert score_consistency(0, 30) == 0.0
        assert score_consistency(10, 0) == 0.0

    def test_confidence_basic(self):
        scores = {"frequency": 0.5, "consistency": 1.0, "context": 1.0}
        conf = compute_confidence(scores, base=0.5, per_occurrence=0.03,
                                  occurrence_count=10, cap=0.99)
        assert 0.5 < conf <= 0.99

    def test_confidence_cap(self):
        scores = {"frequency": 1.0, "consistency": 1.0, "context": 1.0}
        conf = compute_confidence(scores, base=0.5, per_occurrence=0.1,
                                  occurrence_count=100, cap=0.99)
        assert conf == 0.99

    def test_consistency_penalizes(self):
        scores_consistent = {"consistency": 1.0}
        scores_inconsistent = {"consistency": 0.2}
        conf_good = compute_confidence(scores_consistent, occurrence_count=10)
        conf_bad = compute_confidence(scores_inconsistent, occurrence_count=10)
        assert conf_good > conf_bad


class TestMiner:
    def _make_signals(self):
        """Signals simulating 'Dominic' appearing across 5 chapters."""
        signals = []
        for ch in range(1, 6):
            signals.append(Signal(
                text="Dominic", chapter=ch, type="entity",
                context=f"Dominic did something in chapter {ch}.",
                extractor="entity.single_cap",
            ))
        # Add a variant
        signals.append(Signal(
            text="dominic", chapter=1, type="entity",
            context="dominic was there.", extractor="entity.single_cap",
        ))
        # Add another entity with fewer appearances
        for ch in [1, 3]:
            signals.append(Signal(
                text="Ian", chapter=ch, type="entity",
                context=f"Ian was in chapter {ch}.",
                extractor="entity.single_cap",
            ))
        return signals

    def test_produces_policies(self):
        signals = self._make_signals()
        policies = mine_policies(signals, total_chapters=10, min_support=2)
        assert len(policies) > 0

    def test_canonical_form_is_most_frequent(self):
        signals = self._make_signals()
        policies = mine_policies(signals, total_chapters=10, min_support=1)
        # "Dominic" (5 occurrences) should be canonical over "dominic" (1)
        dominic_policy = [p for p in policies if p.trigger.lower() == "dominic"]
        assert len(dominic_policy) >= 1
        assert dominic_policy[0].trigger == "Dominic"

    def test_respects_min_support(self):
        signals = self._make_signals()
        # Ian only appears in 2 chapters
        policies_strict = mine_policies(signals, total_chapters=10, min_support=3)
        triggers = {p.trigger.lower() for p in policies_strict}
        assert "ian" not in triggers

    def test_assigns_deterministic_mode(self):
        signals = self._make_signals()
        policies = mine_policies(signals, total_chapters=10, min_support=1,
                                 deterministic_threshold=0.7)
        for p in policies:
            if p.confidence >= 0.7:
                assert p.applies == "deterministic"
            else:
                assert p.applies == "prompted"

    def test_sorted_by_confidence(self):
        signals = self._make_signals()
        policies = mine_policies(signals, total_chapters=10, min_support=1)
        for i in range(len(policies) - 1):
            assert policies[i].confidence >= policies[i + 1].confidence

    def test_evidence_lists_chapters(self):
        signals = self._make_signals()
        policies = mine_policies(signals, total_chapters=10, min_support=1)
        dominic = [p for p in policies if p.trigger == "Dominic"][0]
        assert set(dominic.evidence) == {1, 2, 3, 4, 5}
