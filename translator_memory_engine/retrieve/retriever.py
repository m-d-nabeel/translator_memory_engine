"""Policy Retriever — lexical match of policy match-forms against an MTL passage.

v0 retriever (PLAN.md §6 M1, §9): given a passage, find the policies whose
`match` surface forms appear in it. This is the policy-retrieval mechanism
(conditions C/D in the §12 ablation), distinct from the document-level RAG
retriever used by the baseline (condition A).

The retriever knows nothing about storage: it is given the policies and returns
the ones that match. Conflict resolution and application live elsewhere.
"""

import re
from typing import Dict, List, Tuple

from translator_memory_engine.policy import Policy


class PolicyRetriever:
    """Lexically match policy surface forms against text."""

    def __init__(self, policies: List[Policy]):
        self.policies = policies
        # Pre-compile, longest match form first for stable scanning
        self._forms: List[Tuple[str, Policy]] = []
        for p in policies:
            for form in p.match:
                self._forms.append((form.lower(), p))
        # Sort by length desc so longer forms are preferred when overlaps occur
        self._forms.sort(key=lambda x: len(x[0]), reverse=True)

    def retrieve(self, text: str, k: int | None = None) -> List[Policy]:
        """Return policies whose any match form appears in `text`.

        Args:
            text: The MTL passage to match against.
            k: Optional cap on number of policies returned.

        Returns:
            List of matching Policy objects (order: by appearance confidence).
        """
        lowered = text.lower()
        matched: Dict[str, Policy] = {}
        for form_lower, policy in self._forms:
            if not form_lower:
                continue
            if form_lower in lowered:
                matched[policy.id] = policy
        result = list(matched.values())
        if k is not None:
            result = result[:k]
        return result
