"""Tests for exemplar retrieval and scene classification."""

from translator_memory_engine.style.exemplars import (
    ExemplarIndex,
    build_exemplar_index,
    classify_scene_type,
)
from translator_memory_engine.style.schema import Exemplar


class TestClassifySceneType:
    def test_dialogue(self):
        text = '"Are you all right?" she asked.'
        assert classify_scene_type(text) == "dialogue"

    def test_action(self):
        text = ("He ran forward and drew his sword. She leapt over the barrier "
                "and charged at the enemy. The warrior swung his blade and struck "
                "the shield with a resounding clang.")
        assert classify_scene_type(text) == "action"

    def test_internal(self):
        text = "He wondered if this was the right path. She realized the truth."
        assert classify_scene_type(text) == "internal"

    def test_transition(self):
        text = "Meanwhile, across the valley."
        assert classify_scene_type(text) == "transition"


class TestExemplarIndex:
    def test_empty_index(self):
        index = ExemplarIndex([])
        result = index.retrieve("hello world")
        assert result == []

    def test_retrieve_by_scene_type(self):
        exemplars = [
            Exemplar(text="hello", scene_type="dialogue", chapter_num=1),
            Exemplar(text="goodbye", scene_type="action", chapter_num=1),
            Exemplar(text="hi there", scene_type="dialogue", chapter_num=2),
        ]
        index = ExemplarIndex(exemplars)
        result = index.retrieve("hello", scene_type="dialogue")
        assert all(e.scene_type == "dialogue" for e in result)

    def test_keyword_fallback(self):
        exemplars = [
            Exemplar(text="the cat sat on the mat", scene_type="description", chapter_num=1),
            Exemplar(text="the dog ran in the park", scene_type="action", chapter_num=1),
        ]
        index = ExemplarIndex(exemplars)
        result = index.retrieve("cat mat", top_k=1)
        assert len(result) == 1
        assert "cat" in result[0].text

    def test_balanced_retrieval(self):
        exemplars = [
            Exemplar(text=f"text {i}", scene_type=st, chapter_num=1)
            for i, st in enumerate(["dialogue", "action", "description",
                                     "internal", "transition"])
        ]
        index = ExemplarIndex(exemplars)
        result = index.retrieve_balanced("some query", per_type=1)
        types_found = {e.scene_type for e in result}
        assert len(types_found) == 5


class TestBuildExemplarIndex:
    def test_builds_from_chapters(self):
        chapters = [
            '"Hello!" she said.\n\nHe ran across the field.',
            '"Goodbye!" he replied.\n\nShe wondered about the future.',
        ]
        index = build_exemplar_index(chapters, [1, 2])
        assert len(index.exemplars) > 0
        assert any(e.chapter_num == 1 for e in index.exemplars)
        assert any(e.chapter_num == 2 for e in index.exemplars)
