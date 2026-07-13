"""Tests for entity shielding (rewrite/shield.py)."""

from translator_memory_engine.rewrite.shield import restore_entities, shield_entities


class TestShieldEntities:
    def test_shields_canonical_name(self):
        text = "Dominic laughed at the village. Li Qing smiled."
        glossary = [{"canonical": "Dominic", "match": ["Dominic"]}]
        shielded, restore_map = shield_entities(text, glossary)
        assert "Dominic" not in shielded
        assert "__ENT_" in shielded
        assert len(restore_map) == 1

    def test_shields_multiple_forms(self):
        text = "Li Qing walked. Li smiled."
        glossary = [{"canonical": "Li Qing", "match": ["Li Qing", "Li"]}]
        shielded, restore_map = shield_entities(text, glossary)
        assert "Li Qing" not in shielded
        assert " Li smiled" not in shielded
        restored = restore_entities(shielded, restore_map)
        assert restored == "Li Qing walked. Li Qing smiled."

    def test_global_longest_match_wins_across_glossary_rows(self):
        text = "Li Qing arrived."
        glossary = [
            {"canonical": "Li", "match": ["Li"]},
            {"canonical": "Li Qing", "match": ["Li Qing"]},
        ]
        shielded, restore_map = shield_entities(text, glossary)
        assert shielded == "__ENT_0__ arrived."
        assert restore_map == {"__ENT_0__": "Li Qing"}

    def test_preserves_non_glossary_text(self):
        text = "The boy ate the porridge."
        glossary = [{"canonical": "Dominic", "match": ["Dominic"]}]
        shielded, restore_map = shield_entities(text, glossary)
        assert shielded == text  # Nothing to shield

    def test_empty_glossary(self):
        text = "Dominic laughed."
        shielded, restore_map = shield_entities(text, [])
        assert shielded == text
        assert restore_map == {}

    def test_case_insensitive(self):
        text = "dominic laughed. DOMINIC smiled."
        glossary = [{"canonical": "Dominic", "match": ["dominic"]}]
        shielded, restore_map = shield_entities(text, glossary)
        assert "dominic" not in shielded.lower() or "__ENT_" in shielded


class TestRestoreEntities:
    def test_restores_original(self):
        text = "__ENT_0__ laughed. __ENT_0__ smiled."
        restore_map = {"__ENT_0__": "Dominic"}
        restored = restore_entities(text, restore_map)
        assert "Dominic" in restored
        assert "__ENT_" not in restored

    def test_preserves_unrecognized_placeholders_for_validation(self):
        text = "__ENT_99__ laughed."
        restored = restore_entities(text, {})
        assert "__ENT_99__" in restored
        assert "laughed" in restored

    def test_roundtrip(self):
        text = "Dominic laughed at the village."
        glossary = [{"canonical": "Dominic", "match": ["Dominic"]}]
        shielded, restore_map = shield_entities(text, glossary)
        restored = restore_entities(shielded, restore_map)
        assert "Dominic" in restored
