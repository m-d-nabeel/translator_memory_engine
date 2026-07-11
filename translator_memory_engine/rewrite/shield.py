"""Entity shielding — protect named entities during LLM rewrite.

Replaces glossary entry surface forms with deterministic placeholders before
the LLM sees the text, then restores them afterwards. This guarantees the LLM
cannot mangle entity names, and the faithfulness guard becomes simpler (no
need to re-prompt for novel entities — they can't be novel if shielded).
"""

import re
from typing import Dict, List, Tuple

_PLACEHOLDER_RE = re.compile(r"__ENT_(\d+)__")


def shield_entities(
    text: str,
    glossary: List[Dict],
) -> Tuple[str, Dict[str, str]]:
    """Replace glossary entry surface forms with __ENT_N__ placeholders.

    Args:
        text: The MTL text to shield.
        glossary: List of glossary dicts, each with at minimum
            "canonical" and optionally "match" (list of surface forms).

    Returns:
        (shielded_text, restore_map) where restore_map maps placeholder
        to the canonical form to restore.
    """
    restore_map: Dict[str, str] = {}
    shielded = text
    idx = 0

    for entry in glossary:
        canonical = entry.get("canonical", "")
        if not canonical:
            continue

        # Collect all surface forms: match list + canonical itself
        forms = list(entry.get("match", []))
        if canonical not in forms:
            forms.append(canonical)

        # Sort by length descending so longer forms are replaced first
        # (avoids partial replacement of "Li Qing" before "Li")
        forms.sort(key=len, reverse=True)

        placeholder = f"__ENT_{idx}__"
        for form in forms:
            if not form:
                continue
            # Case-insensitive whole-word replacement
            pattern = re.compile(
                r"(?<![a-zA-Z0-9])" + re.escape(form) + r"(?![a-zA-Z0-9])",
                re.IGNORECASE,
            )
            # Only replace if not already shielded
            if pattern.search(shielded) and placeholder not in shielded:
                shielded = pattern.sub(placeholder, shielded)
                restore_map[placeholder] = canonical
                idx += 1
                break  # One placeholder per glossary entry
            elif pattern.search(shielded):
                # Already has a placeholder for this entry, just replace
                shielded = pattern.sub(placeholder, shielded)

    return shielded, restore_map


def restore_entities(text: str, restore_map: Dict[str, str]) -> str:
    """Restore original entity spans from placeholders.

    Replaces __ENT_N__ with the canonical form from the restore map.
    Unrecognized placeholders are removed.
    """
    result = text
    for placeholder, canonical in restore_map.items():
        result = result.replace(placeholder, canonical)
    # Clean up any leftover unrecognized placeholders
    result = _PLACEHOLDER_RE.sub("", result)
    return result
