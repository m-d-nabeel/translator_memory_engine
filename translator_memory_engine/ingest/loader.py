import os
import re
import zipfile
import html
from html.parser import HTMLParser
from typing import List, Optional

from translator_memory_engine.models import Chapter

CHAPTER_MARKER = re.compile(r'(?i)^\s*(chapter|ch)\.?\s*\d+')
STRIP_PATTERNS = [
    re.compile(r'(?i)translator\'?s?\s*notes?.*', re.DOTALL),
    re.compile(r'(?i)editor\'?s?\s*notes?.*', re.DOTALL),
]


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
        chapters.append(Chapter(chapter=i, title=title, text=chunk,
                                paragraphs=[p for p in chunk.split("\n") if p.strip()]))
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
        chapters.append(Chapter(chapter=i, title=title, text=chunk,
                                paragraphs=[p for p in chunk.split("\n") if p.strip()]))
    return chapters


def load_corpus(input_dir: str, chapter_marker: str,
                strip_patterns: Optional[List[str]] = None) -> List[Chapter]:
    marker = re.compile(chapter_marker)
    strips = [re.compile(p) for p in (strip_patterns or [])]
    chapters: List[Chapter] = []
    for root, _, files in os.walk(input_dir):
        for fname in sorted(files):
            ext = fname.lower().rsplit(".", 1)[-1]
            full = os.path.join(root, fname)
            if ext == "txt":
                chapters.extend(_load_txt(full, marker, strips))
            elif ext == "epub":
                chapters.extend(_load_epub(full, marker, strips))
    chapters.sort(key=lambda c: c.chapter)
    return chapters
