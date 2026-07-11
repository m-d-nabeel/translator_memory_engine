"""Style profile schema — the learned voice fingerprint for a translator.

StyleProfile holds both LLM-analyzed qualitative notes and deterministic
stylometry diagnostics. It is extracted from paired good+MTL data (Case 1)
and used to steer the rewrite LLM when no published reference exists for a
chapter (unsupervised mode).

Exemplars are scene-tagged excerpts from the good translation, selected by
embedding similarity to the chapter being rewritten.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

SCENE_TYPES = ("dialogue", "action", "description", "internal", "transition")


@dataclass
class Exemplar:
    """A scene-tagged excerpt from the good translation."""

    text: str
    scene_type: str  # one of SCENE_TYPES
    chapter_num: int
    embedding: Optional[List[float]] = None

    def to_dict(self) -> dict:
        d = {
            "text": self.text,
            "scene_type": self.scene_type,
            "chapter_num": self.chapter_num,
        }
        if self.embedding is not None:
            d["embedding"] = self.embedding
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Exemplar":
        return cls(
            text=d["text"],
            scene_type=d["scene_type"],
            chapter_num=d["chapter_num"],
            embedding=d.get("embedding"),
        )


@dataclass
class StyleProfile:
    """Learned voice profile for a translator.

    Attributes:
        register: High-level description of the narrative voice
            (e.g. "close-third-person, colloquial, snappy dialogue").
        narration_notes: LLM-analyzed patterns in narration prose.
        dialogue_notes: LLM-analyzed patterns in dialogue.
        rewrite_tendencies: Editorial tendencies extracted from paired
            MTL→original diffs (Case 1 only). Keys are short labels like
            "passive→active", values are descriptive instructions.
        exemplars: Scene-tagged excerpts from the good translation,
            selected for voice richness and diversity.
        diagnostics: Deterministic stylometry metrics (no LLM). Keys include
            avg_sentence_length, sentence_length_variance, lexical_richness,
            hapax_ratio, contraction_rate, dialog_share, top_sentence_starts.
    """

    register: str = ""
    narration_notes: str = ""
    dialogue_notes: str = ""
    rewrite_tendencies: Dict[str, str] = field(default_factory=dict)
    exemplars: List[Exemplar] = field(default_factory=list)
    diagnostics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "register": self.register,
            "narration_notes": self.narration_notes,
            "dialogue_notes": self.dialogue_notes,
            "rewrite_tendencies": self.rewrite_tendencies,
            "exemplars": [e.to_dict() for e in self.exemplars],
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StyleProfile":
        return cls(
            register=d.get("register", ""),
            narration_notes=d.get("narration_notes", ""),
            dialogue_notes=d.get("dialogue_notes", ""),
            rewrite_tendencies=d.get("rewrite_tendencies", {}),
            exemplars=[Exemplar.from_dict(e) for e in d.get("exemplars", [])],
            diagnostics=d.get("diagnostics", {}),
        )

    def to_prompt_excerpts(self, max_exemplars: int = 15) -> List[str]:
        """Format the profile as a list of prompt-ready strings."""
        lines: List[str] = []
        if self.register:
            lines.append(f"Register: {self.register}")
        if self.narration_notes:
            lines.append(f"Narration: {self.narration_notes}")
        if self.dialogue_notes:
            lines.append(f"Dialogue: {self.dialogue_notes}")
        for label, instruction in self.rewrite_tendencies.items():
            lines.append(f"Tendency ({label}): {instruction}")
        for ex in self.exemplars[:max_exemplars]:
            lines.append(f"[{ex.scene_type}] {ex.text}")
        if self.diagnostics:
            parts = []
            for k, v in self.diagnostics.items():
                if k == "top_sentence_starts":
                    continue
                parts.append(f"{k}={v:.2f}")
            if parts:
                lines.append(f"Measured: {'; '.join(parts)}")
        return lines
