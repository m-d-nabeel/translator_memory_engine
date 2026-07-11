"""Evaluation stack for the Translator Memory Engine.

Kept strictly separate from the extract/rewrite LLM stack (D11): the same model
must not both produce and judge a chapter.
"""

from translator_memory_engine.eval.align import (
    align_paired,
    align_unpaired,
    cosine,
    cosine_excluding,
)
from translator_memory_engine.eval.faith import (
    faithfulness_vs_reference,
    faithfulness_vs_source,
)
from translator_memory_engine.eval.judge import judge_chapter

__all__ = [
    "align_paired",
    "align_unpaired",
    "cosine",
    "cosine_excluding",
    "faithfulness_vs_source",
    "faithfulness_vs_reference",
    "judge_chapter",
]
