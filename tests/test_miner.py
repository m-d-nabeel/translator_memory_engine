"""Tests for Policy Miner."""

from translator_memory_engine.extract.signals import Signal
from translator_memory_engine.policy.miner import (
    _normalize,
    _normalized_edit_distance,
    mine_policies,
)
from translator_memory_engine.policy.scorer import (
    compute_confidence,
    score_consistency,
    score_frequency,
)


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
        conf = compute_confidence(
            scores, base=0.5, per_occurrence=0.03, occurrence_count=10, cap=0.99
        )
        assert 0.5 < conf <= 0.99

    def test_confidence_cap(self):
        scores = {"frequency": 1.0, "consistency": 1.0, "context": 1.0}
        conf = compute_confidence(
            scores, base=0.5, per_occurrence=0.1, occurrence_count=100, cap=0.99
        )
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
            signals.append(
                Signal(
                    text="Dominic",
                    chapter=ch,
                    type="entity",
                    context=f"Dominic did something in chapter {ch}.",
                    extractor="entity.single_cap",
                )
            )
        # Add a variant
        signals.append(
            Signal(
                text="dominic",
                chapter=1,
                type="entity",
                context="dominic was there.",
                extractor="entity.single_cap",
            )
        )
        # Add another entity with fewer appearances
        for ch in [1, 3]:
            signals.append(
                Signal(
                    text="Ian",
                    chapter=ch,
                    type="entity",
                    context=f"Ian was in chapter {ch}.",
                    extractor="entity.single_cap",
                )
            )
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
        policies = mine_policies(
            signals, total_chapters=10, min_support=1, deterministic_threshold=0.7
        )
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


class TestRegressionFixes:
    """Permanent tests for bugs found during M0 extraction (PLAN.md §12)."""

    def _signals(self, texts_by_chapter):
        signals = []
        for ch, texts in texts_by_chapter.items():
            for t in texts:
                signals.append(
                    Signal(
                        text=t,
                        chapter=ch,
                        type="entity",
                        context=f"{t} appeared.",
                        extractor="ner.spacy",
                    )
                )
        return signals

    def test_ner_generic_nouns_dropped(self):
        # spaCy NER mislabels common nouns as entities; the rules backend must drop them.
        signals = self._signals(
            {
                1: ["Earth", "Rice", "Magic"],
                2: ["Earth", "Cook", "Village"],
                3: ["Wizard", "Rice"],
            }
        )
        policies = mine_policies(signals, total_chapters=5, min_support=2)
        triggers = {p.trigger for p in policies}
        assert not (triggers & {"Earth", "Rice", "Magic", "Cook", "Village", "Wizard"})

    def test_word_order_variants_merged(self):
        # "Sinclair Count" and "Count Sinclair" are the same entity in different word order.
        signals = self._signals(
            {
                1: ["Count Sinclair", "Sinclair Count"],
                2: ["Count Sinclair"],
                3: ["Count Sinclair", "Sinclair Count"],
            }
        )
        policies = mine_policies(signals, total_chapters=5, min_support=2)
        triggers = {p.trigger for p in policies}
        assert "Sinclair Count" not in triggers
        assert "Count Sinclair" in triggers

    def test_title_prefix_not_penalized_as_canonical(self):
        # "Count Sinclair" must beat the word-order variant "Sinclair Count" as canonical,
        # even though "Count" is in the stop-word list (it is a legitimate title prefix).
        signals = self._signals(
            {
                1: ["Count Sinclair"] * 5 + ["Sinclair Count"],
                2: ["Count Sinclair"] * 5,
            }
        )
        policies = mine_policies(signals, total_chapters=5, min_support=2)
        sinclair = [p for p in policies if p.trigger == "Count Sinclair"]
        assert sinclair, "Count Sinclair should be the canonical form"
        assert "Sinclair Count" in sinclair[0].match  # kept as an alias

    def test_bare_surname_flagged_for_review(self):
        # "Sinclair" alone is a redundant subset of "Count Sinclair" -> flag, don't drop blindly.
        signals = self._signals(
            {
                1: ["Count Sinclair", "Sinclair"],
                2: ["Count Sinclair", "Sinclair"],
                3: ["Count Sinclair"],
            }
        )
        policies = mine_policies(signals, total_chapters=5, min_support=2)
        sinclair_bare = [p for p in policies if p.trigger == "Sinclair"]
        assert sinclair_bare
        assert sinclair_bare[0].needs_review is True
        assert sinclair_bare[0].applies == "prompted"

    def test_fragment_alias_dropped(self):
        # "Behind Dominic" is a sentence fragment, not a name variant of "Chief Dominic".
        signals = self._signals(
            {
                1: ["Chief Dominic", "Behind Dominic"],
                2: ["Chief Dominic"],
            }
        )
        policies = mine_policies(signals, total_chapters=5, min_support=2)
        chief = [p for p in policies if p.trigger == "Chief Dominic"]
        assert chief
        assert "Behind Dominic" not in chief[0].match

    def test_real_name_survives_fragments(self):
        # "Calron" is a real character name. Extractors also emit clause-start
        # fragments like "Hearing Calron" / "Ignoring Calron". These fragments
        # are distinct clusters (edit distance > 0.3) and get flagged/dropped,
        # but the standalone name CALRON must still survive as its own policy.
        # Regression guard: never drop the person just because fragments exist.
        signals = self._signals(
            {
                1: ["Calron"] * 3 + ["Hearing Calron", "Ignoring Calron"],
                2: ["Calron"] * 3 + ["Hearing Calron"],
                3: ["Calron"] * 3 + ["Ignoring Calron"],
                4: ["Calron"] * 3,
                5: ["Calron"] * 3,
            }
        )
        policies = mine_policies(signals, total_chapters=5, min_support=2)
        triggers = {p.trigger for p in policies}
        assert "Calron" in triggers, "The real character name Calron must never be lost"
        # The bare fragments must not become canonical entities.
        assert "Hearing Calron" not in triggers
        assert "Ignoring Calron" not in triggers
