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

# Site watermarks that MTL dumps inject (e.g. "* * * Ranovel dot com * * *").
# These are NOT meaning the rewriter must preserve, and relying on the LLM to
# drop them is unreliable (one leaked into ch002). Strip them deterministically
# up front so they can never reach the output.
_WATERMARK = re.compile(
    r"ranovel|novelplanet|wuxiaworld|boxnovel|readwn|lightnovel|wordexcerpt"
    r"|novelfull|translateop|mtlnovel",
    re.I,
)


def clean_mtl_artifacts(text: str) -> str:
    """Remove MTL square-bracket wrappers and site watermarks.

    Runs ONLY on the MTL input to the rewriter, never on the good-translation
    corpus used for extraction — the gold text must stay pristine.
    """
    # Drop whole lines that are just a watermark marker.
    lines = [
        ln for ln in text.split("\n")
        if not _WATERMARK.search(ln)
    ]
    cleaned = "\n".join(lines)
    # Also catch any inline watermark fragment that survived (e.g. mid-line).
    cleaned = _WATERMARK.sub("", cleaned)
    return _BRACKET.sub(r"\1", cleaned)
