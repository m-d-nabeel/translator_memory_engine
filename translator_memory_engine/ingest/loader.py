import os
import re
import zipfile
from html.parser import HTMLParser
from typing import List, Optional

from translator_memory_engine.models import Chapter

CHAPTER_MARKER = re.compile(r"(?i)^\\s*(chapter|ch)\\.?\\s*\\d+")
STRIP_PATTERNS = [
    re.compile(r"(?i)translator\'?s?\s*notes?.*", re.DOTALL),
    re.compile(r"(?i)editor\'?s?\s*notes?.*", re.DOTALL),
]

# Pattern to extract the chapter number from a chapter header
_CHAPTER_NUM = re.compile(r"(?i)(?:chapter|ch)\.?\s*(\d+)")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: List[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "div", "br", "h1", "h2", "h3"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("p", "div", "h1", "h2", "h3"):
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _split_chapters(text: str, marker: re.Pattern) -> List[str]:
    matches = list(marker.finditer(text))
    if not matches:
        return [text]
    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _clean(text: str, strip_patterns: List[re.Pattern]) -> str:
    for pat in strip_patterns:
        text = pat.sub("", text)
    return text


def _extract_chapter_number(text: str, fallback: int) -> int:
    """Extract the chapter number from a chapter header.

    Looks for patterns like 'Chapter 10', 'Ch. 3', '# Chapter 25'.
    Falls back to the provided fallback number if no match is found.
    """
    m = _CHAPTER_NUM.search(text[:200])  # Only search the first 200 chars
    if m:
        return int(m.group(1))
    return fallback


def _load_txt(path: str, marker: re.Pattern, strip_patterns: List[re.Pattern]) -> List[Chapter]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    raw = _clean(raw, strip_patterns)
    chunks = _split_chapters(raw, marker)
    chapters = []
    for i, chunk in enumerate(chunks, start=1):
        title = ""
        m = marker.match(chunk)
        if m:
            title = m.group(0).strip()
        chapter_num = _extract_chapter_number(chunk, fallback=i)
        chapters.append(
            Chapter(
                chapter=chapter_num,
                title=title,
                text=chunk,
                paragraphs=[p for p in chunk.split("\n") if p.strip()],
            )
        )
    return chapters


def _load_epub(path: str, marker: re.Pattern, strip_patterns: List[re.Pattern]) -> List[Chapter]:
    text_blocks: List[str] = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.lower().endswith((".xhtml", ".html", ".htm")):
                data = z.read(name).decode("utf-8", errors="ignore")
                parser = _TextExtractor()
                parser.feed(data)
                text_blocks.append(parser.get_text())
    raw = _clean("\n".join(text_blocks), strip_patterns)
    chunks = _split_chapters(raw, marker)
    chapters = []
    for i, chunk in enumerate(chunks, start=1):
        title = ""
        m = marker.match(chunk)
        if m:
            title = m.group(0).strip()
        chapter_num = _extract_chapter_number(chunk, fallback=i)
        chapters.append(
            Chapter(
                chapter=chapter_num,
                title=title,
                text=chunk,
                paragraphs=[p for p in chunk.split("\n") if p.strip()],
            )
        )
    return chapters


def load_corpus(
    input_dir: str, chapter_marker: str, strip_patterns: Optional[List[str]] = None
) -> List[Chapter]:
    marker = re.compile(chapter_marker)
    strips = [re.compile(p) for p in (strip_patterns or [])]
    chapters: List[Chapter] = []
    global_counter = 0
    for root, _, files in os.walk(input_dir):
        for fname in sorted(files):
            ext = fname.lower().rsplit(".", 1)[-1]
            full = os.path.join(root, fname)
            if ext == "txt":
                loaded = _load_txt(full, marker, strips)
                if not loaded:
                    continue
                # If all chapters got the same fallback number, use global counter
                for ch in loaded:
                    global_counter += 1
                    if ch.chapter == 0:
                        ch.chapter = global_counter
                chapters.extend(loaded)
            elif ext == "epub":
                loaded = _load_epub(full, marker, strips)
                for ch in loaded:
                    global_counter += 1
                    if ch.chapter == 0:
                        ch.chapter = global_counter
                chapters.extend(loaded)
    chapters.sort(key=lambda c: c.chapter)
    return chapters
