"""Tests for signal extractors."""

from translator_memory_engine.extract import extract_signals
from translator_memory_engine.extract.entity import extract_entities
from translator_memory_engine.extract.honorific import extract_honorifics
from translator_memory_engine.extract.terminology import extract_terminology
from translator_memory_engine.models import Chapter


def _make_chapters():
    """Synthetic test chapters with known entities."""
    return [
        Chapter(
            chapter=1, title="Chapter 1", paragraphs=[],
            text=(
                "Lord Theodore Sinclair walked through the halls of the Sinclair Estate. "
                "His knight Ian Hanover followed behind. "
                "'My Lord, the Rondo Trading Company has sent a letter,' said Ian. "
                "Meanwhile, Dominic was cooking in Evergreen village as always. "
                "Theodore nodded at the report about the Devil's Hand."
            ),
        ),
        Chapter(
            chapter=2, title="Chapter 2", paragraphs=[],
            text=(
                "The meal that Dominic prepared was for Lord Theodore. "
                "Ian stood guard at the door. Sir Knight, stand down, said Theodore. "
                "The Rondo Trading Company's merchant Anton arrived. "
                "Countess Noella greeted the guests warmly. "
                "The Devil's Hand seaweed was on the menu."
            ),
        ),
        Chapter(
            chapter=3, title="Chapter 3", paragraphs=[],
            text=(
                "After arriving, Calron visited Evergreen to see Dominic. "
                "Lord Theodore Sinclair was in a meeting with Count Sinclair. "
                "Ian reported that the Rondo Merchant Group had expanded. "
                "My Lord, the situation is under control, Ian assured."
            ),
        ),
    ]


class TestEntityExtraction:
    def test_extracts_character_names(self):
        chapters = _make_chapters()
        signals = extract_entities(chapters, min_support=2)
        texts = {s.text for s in signals}
        # Core character names should be found
        assert "Dominic" in texts
        assert "Ian" in texts
        assert "Theodore" in texts

    def test_extracts_titled_entities(self):
        chapters = _make_chapters()
        signals = extract_entities(chapters, min_support=1)
        texts = {s.text for s in signals}
        assert "Lord Theodore" in texts

    def test_extracts_organization_names(self):
        chapters = _make_chapters()
        signals = extract_entities(chapters, min_support=1)
        texts = {s.text for s in signals}
        # Domain-suffix compounds
        assert "Sinclair Estate" in texts or "Rondo Trading Company" in texts

    def test_respects_min_support(self):
        chapters = _make_chapters()
        # With min_support=3, only names in all 3 chapters survive
        signals_strict = extract_entities(chapters, min_support=3)
        texts = {s.text for s in signals_strict}
        # Dominic appears mid-sentence in all 3 chapters
        assert "Dominic" in texts
        # "Lord Theodore" (title+name) appears in all 3 via title_name extractor
        assert "Lord Theodore" in texts or "Lord Theodore Sinclair" in texts

    def test_filters_stop_words(self):
        chapters = _make_chapters()
        signals = extract_entities(chapters, min_support=1)
        texts = {s.text for s in signals}
        # Stop words should not appear as single-word entities
        for stop in ["The", "His", "Was", "And", "But"]:
            assert stop not in texts

    def test_filters_sentence_fragments(self):
        chapters = [
            Chapter(chapter=1, title="Ch1", paragraphs=[],
                    text="As Ian walked, he noticed something. But Dominic kept cooking."),
            Chapter(chapter=2, title="Ch2", paragraphs=[],
                    text="As Ian approached, Dominic smiled. Watching Dominic cook was soothing."),
        ]
        signals = extract_entities(chapters, min_support=1)
        texts = {s.text for s in signals}
        # "As Ian" and "But Dominic" should NOT be entities
        assert "As Ian" not in texts
        assert "But Dominic" not in texts


class TestTerminologyExtraction:
    def test_extracts_possessive_terms(self):
        chapters = [
            Chapter(chapter=1, title="Ch1", paragraphs=[],
                    text="The Devil's Hand was growing in the sea. It was a rare find."),
            Chapter(chapter=2, title="Ch2", paragraphs=[],
                    text="They harvested the Devil's Hand for the soup."),
        ]
        signals = extract_terminology(chapters, min_support=2)
        texts = {s.text for s in signals}
        assert "Devil's Hand" in texts

    def test_extracts_bracketed_terms(self):
        chapters = [
            Chapter(chapter=1, title="Ch1", paragraphs=[],
                    text="He used the [Inner Strength] technique."),
            Chapter(chapter=2, title="Ch2", paragraphs=[],
                    text="The [Inner Strength] allowed him to break through."),
        ]
        signals = extract_terminology(chapters, min_support=2)
        texts = {s.text for s in signals}
        assert "Inner Strength" in texts


class TestHonorificExtraction:
    def test_extracts_universal_titles(self):
        chapters = [
            Chapter(chapter=1, title="Ch1", paragraphs=[],
                    text="My Lord, the troops are ready. Sir Knight, stand at attention."),
        ]
        signals = extract_honorifics(chapters)
        texts = {s.text for s in signals}
        assert "My Lord" in texts
        assert "Sir Knight" in texts

    def test_extracts_korean_honorifics(self):
        chapters = [
            Chapter(chapter=1, title="Ch1", paragraphs=[],
                    text="Hyung, let's go eat. The sunbae recommended this restaurant."),
        ]
        signals = extract_honorifics(chapters, source_languages=["korean"])
        texts = {s.text for s in signals}
        assert "Hyung" in texts
        assert "sunbae" in texts

    def test_extracts_japanese_honorifics(self):
        chapters = [
            Chapter(chapter=1, title="Ch1", paragraphs=[],
                    text="Tanaka-san arrived at the dojo. Yamada-sensei greeted him."),
        ]
        signals = extract_honorifics(chapters, source_languages=["japanese"])
        texts = {s.text for s in signals}
        assert "Tanaka-san" in texts
        assert "Yamada-sensei" in texts

    def test_extracts_chinese_honorifics(self):
        chapters = [
            Chapter(chapter=1, title="Ch1", paragraphs=[],
                    text="Senior Brother led the way. The Dao Friend followed."),
        ]
        signals = extract_honorifics(chapters, source_languages=["chinese"])
        texts = {s.text for s in signals}
        assert "Senior Brother" in texts
        assert "Dao Friend" in texts


class TestExtractSignals:
    def test_merges_all_extractors(self):
        chapters = _make_chapters()
        signals = extract_signals(chapters, min_support=2, source_languages=["korean"])
        # Should have signals from multiple extractors
        extractors = {s.extractor for s in signals}
        types = {s.type for s in signals}
        assert "entity" in types
        assert len(signals) > 0

    def test_returns_signals_with_context(self):
        chapters = _make_chapters()
        signals = extract_signals(chapters, min_support=1)
        # Every signal should have a non-empty context
        for s in signals:
            assert s.context, f"Signal {s.text!r} has empty context"
