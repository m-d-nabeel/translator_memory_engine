import re
from typing import Dict, List, Set


def validate_entity_consistency(rewritten_text: str, trace: List[Dict]) -> List[str]:
    """
    Validate that entities deterministically applied in the pre-pass survived the LLM rewrite.
    If the LLM deleted or heavily altered the sentence containing the entity, this warns the user.

    Args:
        rewritten_text: The final output text from the rewriter.
        trace: A list of dictionaries representing the deterministic edits made during the pre-pass.
               Each dictionary records its replacement in the ``output`` key.

    Returns:
        A list of warning messages for any expected entities that are missing.
    """
    warnings = []

    # Collect expected canonical terms from the deterministic trace
    expected_terms: Set[str] = set()
    for edit in trace:
        if edit.get("kind") == "known_error":
            continue
        replacement = edit.get("output", "").strip()
        if replacement:
            expected_terms.add(replacement)

    for term in expected_terms:
        # Basic substring check (case insensitive to avoid false positives on casing)
        # Using a word boundary or just raw string match?
        # A raw string match is safer because some entities might be multi-word or hyphenated.
        if not re.search(re.escape(term), rewritten_text, flags=re.IGNORECASE):
            warnings.append(
                f"Missing Expected Entity: '{term}' was expected based on the original MTL, "
                "but does not appear in the final rewritten text. The LLM may have skipped it."
            )

    return sorted(warnings)
