"""Embedding-based exemplar retrieval for style bank.

Replaces Jaccard-based retrieval with cosine similarity on embeddings.
Falls back to Jaccard when the embedding model is unavailable.
"""

import re
from typing import Callable, List, Optional, Tuple

import numpy as np

from translator_memory_engine.style.schema import SCENE_TYPES, Exemplar


def classify_scene_type(text: str) -> str:
    """Classify a paragraph's scene type using spaCy heuristics.

    Returns one of: dialogue, action, description, internal, transition.
    """
    text_lower = text.lower()
    has_dialogue = bool(re.search(r'["\u201c]', text))
    word_count = len(text.split())

    # Internal monologue signals
    internal_words = (
        "thought",
        "wondered",
        "realized",
        "remembered",
        "felt",
        "knew",
        "pondered",
        "considered",
        "reflected",
        "mused",
    )
    has_internal = any(w in text_lower for w in internal_words)

    if has_dialogue:
        return "dialogue"
    if has_internal:
        return "internal"
    if word_count < 25:
        return "transition"

    # Count action verbs vs descriptive markers
    action_verbs = re.findall(
        r"\b(?:ran|drew|struck|leapt|ducked|charged|grabbed|kicked|punched|"
        r"slammed|drew|pulled|pushed|threw|swung|lunged|stabbed|slashed|"
        r"broke|crashed|shattered|exploded|bolted|sprang|dived|rolled|"
        r"dashed|rushed|sprinted|bolted|lunged|fell|dropped|collapsed)\b",
        text_lower,
    )
    adj_count = len(re.findall(r"\b\w+ly\b", text))  # adverb count as proxy
    adj_count += len(re.findall(r"\b(?:very|quite|rather|somewhat|extremely)\b", text_lower))

    if len(action_verbs) >= 3:
        return "action"
    if adj_count >= 3 or word_count > 60:
        return "description"
    return "description"


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class ExemplarIndex:
    """Fast cosine-retrieval index over exemplar embeddings."""

    def __init__(self, exemplars: List[Exemplar]):
        self.exemplars = exemplars
        self._embeddings: Optional[np.ndarray] = None
        if exemplars and any(ex.embedding is not None for ex in exemplars):
            vecs = [ex.embedding if ex.embedding is not None else [0.0] * 768 for ex in exemplars]
            self._embeddings = np.array(vecs, dtype=np.float32)

    def retrieve(
        self,
        query_text: str,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        scene_type: Optional[str] = None,
        top_k: int = 3,
    ) -> List[Exemplar]:
        """Retrieve top-k exemplars by cosine similarity to query.

        If scene_type is specified, pre-filter to matching exemplars.
        If embeddings are unavailable, falls back to keyword overlap.
        """
        candidates = self.exemplars
        if scene_type:
            candidates = [e for e in candidates if e.scene_type == scene_type]

        if not candidates:
            return []

        # Try embedding-based retrieval
        if self._embeddings is not None and embed_fn is not None:
            query_emb = np.array(embed_fn(query_text), dtype=np.float32)
            candidate_indices = [
                i
                for i, e in enumerate(self.exemplars)
                if e in candidates and e.embedding is not None
            ]
            if not candidate_indices:
                return candidates[:top_k]

            cands_emb = self._embeddings[candidate_indices]
            scores = [
                _cosine_similarity(query_emb, cands_emb[j]) for j in range(len(candidate_indices))
            ]
            ranked = sorted(zip(scores, candidate_indices), key=lambda x: x[0], reverse=True)
            return [self.exemplars[idx] for _, idx in ranked[:top_k]]

        # Fallback: keyword overlap
        query_tokens = set(re.findall(r"[a-z']{3,}", query_text.lower()))
        scored = []
        for ex in candidates:
            ex_tokens = set(re.findall(r"[a-z']{3,}", ex.text.lower()))
            if not ex_tokens or not query_tokens:
                scored.append((0.0, ex))
                continue
            score = len(query_tokens & ex_tokens) / len(query_tokens | ex_tokens)
            scored.append((score, ex))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:top_k]]

    def retrieve_all(
        self,
        query_text: str,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        top_k: int = 15,
    ) -> List[Exemplar]:
        """Retrieve top-k exemplars across all scene types (for prompt assembly)."""
        return self.retrieve(query_text, embed_fn=embed_fn, scene_type=None, top_k=top_k)

    def retrieve_balanced(
        self,
        query_text: str,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        per_type: int = 3,
    ) -> List[Exemplar]:
        """Retrieve top-k per scene type for balanced prompt diversity."""
        results: List[Exemplar] = []
        for st in SCENE_TYPES:
            results.extend(
                self.retrieve(query_text, embed_fn=embed_fn, scene_type=st, top_k=per_type)
            )
        return results


def build_exemplar_index(
    chapters: List[str],
    chapter_nums: List[int],
    embed_fn: Optional[Callable[[str], List[float]]] = None,
    per_chapter: int = 3,
) -> ExemplarIndex:
    """Build an ExemplarIndex from good-translation chapters.

    For each chapter, classifies paragraphs by scene type, ranks by voice
    richness, and keeps the top `per_chapter` per scene type.
    """
    exemplars: List[Exemplar] = []

    for text, num in zip(chapters, chapter_nums):
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        by_type: dict[str, list[Tuple[float, str]]] = {st: [] for st in SCENE_TYPES}

        for para in paragraphs:
            scene = classify_scene_type(para)
            # Voice richness: dialogue density + word count (proxy for detail)
            word_count = len(para.split())
            dlg_density = len(re.findall(r'["\u201c]', para)) / max(word_count, 1)
            richness = dlg_density * 10 + min(word_count / 50, 1.0)
            by_type[scene].append((richness, para))

        for st, items in by_type.items():
            items.sort(key=lambda x: x[0], reverse=True)
            for _, para in items[:per_chapter]:
                emb = embed_fn(para) if embed_fn else None
                exemplars.append(
                    Exemplar(
                        text=para[:500],  # cap length
                        scene_type=st,
                        chapter_num=num,
                        embedding=emb,
                    )
                )

    return ExemplarIndex(exemplars)
