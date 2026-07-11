"""Tests for the style bank (Language Memory, lite)."""

from translator_memory_engine.memory.style_bank import (
    _pick_excerpts,
    _stats,
    build_style_bank,
)

CH1 = (
    'He said, "Calron, eat your porridge."\n\n'
    "The boy scowled at the bowl.\n\n"
    '"You\'re overthinking it," she added.\n\n'
    "A village that welcomed strangers was rare."
)

CH2 = (
    '"Elder, are you all right?" the child asked.\n\n'
    "Dominic laughed, a baring of teeth that passed for warmth.\n\n"
    "Outside, the wind took the roofs."
)


def test_pick_excerpts_prefers_dialogue():
    ex = _pick_excerpts(CH1, per_chapter=2, max_chars=400)
    assert len(ex) == 2
    # Both chosen paragraphs should contain dialogue
    assert all(('"' in e) for e in ex)


def test_stats_nonempty_for_corpus():
    s = _stats([CH1, CH2])
    assert "chapters" in s
    assert "dialogue" in s.lower()


def test_build_style_bank_returns_excerpts_and_stats():
    prof = build_style_bank([CH1, CH2], per_chapter=2)
    assert len(prof) >= 3  # 2 per chapter + 1 stats line
    assert any("chapters" in p for p in prof)  # stats line present


def test_build_style_bank_empty():
    assert build_style_bank([]) == []
    assert build_style_bank([], include_stats=False) == []


def test_build_style_bank_stats_off():
    prof = build_style_bank([CH1], per_chapter=1, include_stats=False)
    assert len(prof) == 1
    assert "chapters" not in prof[0]
