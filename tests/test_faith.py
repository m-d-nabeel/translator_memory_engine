"""Tests for the faithfulness evaluation (the 1st eval pillar)."""

from translator_memory_engine.eval.faith import faithfulness_vs_source


def test_invented_name_flagged():
    src = "The boy scowled. Dominic laughed."
    gen = "Ian nodded. Dominic laughed."
    r = faithfulness_vs_source(gen, src)
    assert "Ian" in r["novel_persons"]
    assert "Dominic" not in r["novel_persons"]


def test_present_name_not_flagged_as_novel():
    # Regression for the ch040 false alarm: Dominic IS in the source.
    src = "Dominic laughed at the village."
    gen = "Chief Dominic laughed at the village."
    r = faithfulness_vs_source(gen, src)
    assert r["novel_person_count"] == 0


def test_intrusion_detected():
    src = "The bell rang. The boy left."
    gen = "The bell rang. A completely new subplot about a dragon appeared suddenly."
    r = faithfulness_vs_source(gen, src)
    assert r["intrusion_score"] > 0


def test_no_invention_when_faithful():
    src = "Calron ate the porridge. The elder watched."
    gen = "Calron ate the porridge, and the elder watched him."
    r = faithfulness_vs_source(gen, src)
    assert r["novel_person_count"] == 0
    assert r["intrusion_score"] == 0.0
