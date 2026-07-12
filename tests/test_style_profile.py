"""Tests for StyleProfile schema (style/schema.py)."""

from translator_memory_engine.style.schema import Exemplar, StyleProfile


class TestExemplar:
    def test_roundtrip_dict(self):
        ex = Exemplar(text="hello", scene_type="dialogue", chapter_num=1)
        d = ex.to_dict()
        restored = Exemplar.from_dict(d)
        assert restored.text == ex.text
        assert restored.scene_type == ex.scene_type
        assert restored.chapter_num == ex.chapter_num

    def test_with_embedding(self):
        ex = Exemplar(text="hello", scene_type="dialogue", chapter_num=1, embedding=[0.1, 0.2, 0.3])
        d = ex.to_dict()
        assert d["embedding"] == [0.1, 0.2, 0.3]
        restored = Exemplar.from_dict(d)
        assert restored.embedding == [0.1, 0.2, 0.3]


class TestStyleProfile:
    def test_roundtrip_dict(self):
        sp = StyleProfile(
            register="close-third-person, colloquial",
            narration_notes="Short, punchy sentences.",
            dialogue_notes="Snappy, informal dialogue.",
            rewrite_tendencies={"passive→active": "Rewrites passives to active voice"},
            exemplars=[
                Exemplar(text="hello", scene_type="dialogue", chapter_num=1),
            ],
            diagnostics={"avg_sentence_length": 12.5, "dialog_share": 0.4},
        )
        d = sp.to_dict()
        restored = StyleProfile.from_dict(d)
        assert restored.register == sp.register
        assert restored.narration_notes == sp.narration_notes
        assert restored.dialogue_notes == sp.dialogue_notes
        assert restored.rewrite_tendencies == sp.rewrite_tendencies
        assert len(restored.exemplars) == 1
        assert restored.diagnostics["avg_sentence_length"] == 12.5

    def test_empty_profile(self):
        sp = StyleProfile()
        d = sp.to_dict()
        restored = StyleProfile.from_dict(d)
        assert restored.register == ""
        assert restored.exemplars == []

    def test_to_prompt_excerpts(self):
        sp = StyleProfile(
            register="colloquial",
            narration_notes="Short sentences.",
            dialogue_notes="Informal.",
            rewrite_tendencies={"passive→active": "Rewrite passives"},
            exemplars=[
                Exemplar(text="hello world", scene_type="dialogue", chapter_num=1),
            ],
            diagnostics={"avg_sentence_length": 10.0, "dialog_share": 0.5},
        )
        excerpts = sp.to_prompt_excerpts()
        assert any("Register: colloquial" in e for e in excerpts)
        assert any("Narration: Short sentences." in e for e in excerpts)
        assert any("[dialogue] hello world" in e for e in excerpts)
        assert any("avg_sentence_length=10.00" in e for e in excerpts)

    def test_to_prompt_excerpts_with_cap(self):
        sp = StyleProfile(
            exemplars=[Exemplar(text=f"ex{i}", scene_type="dialogue", chapter_num=1) for i in range(20)],
        )
        excerpts = sp.to_prompt_excerpts(max_exemplars=5)
        exemplar_count = sum(1 for e in excerpts if e.startswith("[dialogue]"))
        assert exemplar_count == 5
