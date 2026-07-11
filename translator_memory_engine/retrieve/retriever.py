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
        # Pre-compile, longest match form first for stable scanning. Matching uses
        # word boundaries (not naive substring) so a form like "Ian" does NOT match
        # inside "brilliant" / "Julian" — that false positive once invented a whole
        # subplot (ch040). See faithfulness-guard work.
        self._forms: List[Tuple[re.Pattern, Policy, int]] = []
        for p in policies:
            for form in p.match:
                if not form:
                    continue
                fl = form.lower()
                rx = re.compile(r"(?<![a-z0-9])" + re.escape(fl) + r"(?![a-z0-9])")
                self._forms.append((rx, p, len(fl)))
        # Sort by form length desc so longer forms are preferred on overlaps
        self._forms.sort(key=lambda x: x[2], reverse=True)

    def retrieve(self, text: str, k: int | None = None) -> List[Policy]:
        """Return policies whose any match form appears in `text` as a whole word.

        Args:
            text: The MTL passage to match against.
            k: Optional cap on number of policies returned.

        Returns:
            List of matching Policy objects (order: by appearance confidence).
        """
        lowered = text.lower()
        matched: Dict[str, Policy] = {}
        for rx, policy, _ in self._forms:
            if rx.search(lowered):
                matched[policy.id] = policy
        result = list(matched.values())
        if k is not None:
            result = result[:k]
        return result
