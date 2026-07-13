"""Entity shielding — protect named entities during LLM rewrite.

Replaces glossary entry surface forms with deterministic placeholders before
the LLM sees the text, then restores them afterwards. This guarantees the LLM
cannot mangle entity names, and the faithfulness guard becomes simpler (no
need to re-prompt for novel entities — they can't be novel if shielded).
"""

import re
from typing import Dict, List, Optional, Tuple

_PLACEHOLDER_RE = re.compile(r"__ENT_(\d+)__")


def shield_entities(
    text: str,
    glossary: List[Dict],
    placeholder_by_canonical: Optional[Dict[str, str]] = None,
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
    supplied_mapping = placeholder_by_canonical is not None
    canonical_to_placeholder = dict(placeholder_by_canonical or {})
    restore_map = {placeholder: canonical for canonical, placeholder in canonical_to_placeholder.items()}
    candidates: List[Tuple[int, int, str]] = []

    for entry in glossary:
        canonical = entry.get("canonical", "")
        if not canonical:
            continue
        if supplied_mapping and canonical not in canonical_to_placeholder:
            continue
        forms = entry.get("match", [])
        if isinstance(forms, str):
            forms = [forms]
        forms = list(forms)
        if canonical not in forms:
            forms.append(canonical)

        for form in set(forms):
            if not form:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(form) + r"(?!\w)", re.IGNORECASE)
            candidates.extend((m.start(), m.end(), canonical) for m in pattern.finditer(text))

    # Resolve collisions globally, not one glossary row at a time. This ensures
    # "Li Qing" wins over "Li" regardless of database insertion order.
    candidates.sort(key=lambda item: (-(item[1] - item[0]), item[0], item[2].lower()))
    selected: List[Tuple[int, int, str]] = []
    for start, end, canonical in candidates:
        if any(not (end <= chosen_start or start >= chosen_end) for chosen_start, chosen_end, _ in selected):
            continue
        selected.append((start, end, canonical))

    next_idx = len(canonical_to_placeholder)
    for _, _, canonical in sorted(selected, key=lambda item: (item[0], item[1], item[2].lower())):
        if canonical not in canonical_to_placeholder:
            placeholder = f"__ENT_{next_idx}__"
            canonical_to_placeholder[canonical] = placeholder
            restore_map[placeholder] = canonical
            next_idx += 1

    shielded = text
    for start, end, canonical in sorted(selected, key=lambda item: item[0], reverse=True):
        shielded = shielded[:start] + canonical_to_placeholder[canonical] + shielded[end:]
    return shielded, restore_map


def restore_entities(text: str, restore_map: Dict[str, str]) -> str:
    """Restore original entity spans from placeholders.

    Replaces __ENT_N__ with the canonical form from the restore map.
    Unrecognized placeholders are removed.
    """
    result = text
    for placeholder, canonical in restore_map.items():
        result = result.replace(placeholder, canonical)
    # Preserve unknown markers. Dropping them silently deletes a name and makes
    # corruption impossible for the caller to detect and recover from.
    return result
