"""MTL artifact cleaning for the rewrite path (PLAN.md §7 Layer 3).

Raw MTL carries conventions that hurt readability and are not "meaning" the
rewriter must preserve:
  - Internal-monologue / thought blocks wrapped in square brackets:
    "[go away! I fed him and put him to sleep...]"  ->  go away! I fed him...
  - (duplicated / truncated fragments are best fixed by the LLM rewriter; see
    the rewrite prompt.)

This runs ONLY on the MTL input to the rewriter, never on the good-translation
corpus used for extraction — the gold text must stay pristine.
"""

import re

# Strip the surrounding brackets of a [...]-wrapped thought block, keeping the
# text inside. Newline inside brackets is excluded so we don't swallow a whole
# multi-line aside unintendedly.
_BRACKET = re.compile(r"\[([^\]\n]*)\]")


def clean_mtl_artifacts(text: str) -> str:
    """Remove MTL square-bracket wrappers around thought/monologue blocks."""
    return _BRACKET.sub(r"\1", text)
