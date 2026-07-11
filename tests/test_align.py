"""Tests for the alignment evaluation (dependency-free TF-IDF cosine)."""

from translator_memory_engine.eval.align import (
    align_paired,
    align_unpaired,
    cosine,
    cosine_excluding,
)

GEN = "Calron ate the porridge and scowled at the village elder."
ORIG = "Calron ate his porridge and frowned at the village elder."
MTL = "Calron eat porridge and black at village old man."


def test_cosine_identical_is_one():
    assert cosine("the cat sat", "the cat sat") == 1.0


def test_cosine_disjoint_is_low():
    assert cosine("alpha beta", "gamma delta") == 0.0


def test_cosine_overlap_scales():
    a = cosine("calron village elder", "calron village elder porridge")
    b = cosine("calron village elder", "totally different words here")
    assert a > b


def test_align_paired_delta():
    res = align_paired(GEN, ORIG, MTL)
    assert res["sim_generated_original"] > res["sim_mtl_original"]
    assert res["delta_vs_mtl"] > 0


def test_align_unpaired_adherence():
    profile = ["Calron frowned at the elder.", "The village welcomed strangers."]
    canonical = ["Calron", "Dominic", "Count Sinclair"]
    res = align_unpaired(GEN, profile, canonical)
    assert res["names_total"] == 3
    assert res["names_present"] == 1  # only Calron appears in GEN
    assert abs(res["name_adherence"] - round(1 / 3, 4)) < 1e-9


def test_align_unpaired_no_canonical():
    res = align_unpaired(GEN, ["some prose"], [])
    assert res["name_adherence"] is None


def test_cosine_excluding_removes_name_influence():
    # The real confound: a canonical name present in BOTH gen and orig inflates
    # their similarity. Excluding it should drop gen~orig back toward the mtl~orig
    # baseline (which never had the name).
    orig = "Calron ate the porridge."
    gen = "Calron ate the porridge and smiled."
    mtl = "The boy ate the porridge and smiled."
    raw_gen = cosine(gen, orig)
    raw_mtl = cosine(mtl, orig)
    assert raw_gen > raw_mtl  # shared name creates the confound

    excl_gen = cosine_excluding(gen, orig, ["Calron"])
    excl_mtl = cosine_excluding(mtl, orig, ["Calron"])
    assert excl_gen <= raw_gen  # excluding the shared name cannot raise similarity
    # After removing the shared name, gen and mtl are similarly related to orig.
    assert abs(excl_gen - excl_mtl) < 0.05
