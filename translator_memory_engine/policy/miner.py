"""Policy Miner — Signals → verified Policies.

Three stages:
1. Aggregation: group signals by normalized text
2. Variant clustering: merge near-duplicates, pick canonical form
3. Confidence scoring: compute frequency, consistency, overall confidence

This is the heart of the system (PLAN.md §7).
"""

import re
import unicodedata
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from translator_memory_engine.extract.entity import (
    _STOP_PREFIXES,
    _STOP_WORDS,
    _TITLE_PREFIXES,
)
from translator_memory_engine.extract.signals import Signal
from translator_memory_engine.policy import Policy
from translator_memory_engine.policy.scorer import (
    compute_confidence,
    score_consistency,
    score_frequency,
)

# --- Generic noun categories for false-positive filtering ---
#
# DESIGN DECISION: We split "generic" into two categories:
#
# 1. _GENERIC_STANDALONE: words that are NEVER entity names when alone.
#    Single-word candidates matching these are dropped unconditionally.
#    Multi-word candidates are dropped only if ALL words are in this set.
#    Example: "Count" alone → DROP. "Count Sinclair" → KEEP.
#
# 2. NOT in this set: place suffixes like "Castle", "Village", "Dynasty",
#    "Kingdom". These ARE generic when standalone (handled by entity.py stop words)
#    but form legitimate place names when combined: "Count's Castle", "Ming Dynasty".
#    The old code killed "Count's Castle" because both words were in _GENERIC_NOUNS.
#
_GENERIC_STANDALONE: Set[str] = {
    # titles / roles used standalone (not as "Title Name")
    "Count",
    "Countess",
    "Lord",
    "Lady",
    "Sir",
    "Duke",
    "Duchess",
    "Prince",
    "Princess",
    "King",
    "Queen",
    "Emperor",
    "Empress",
    "Viscount",
    "Baron",
    "Marquis",
    "Master",
    "Chief",
    "Elder",
    "Knight",
    "Knights",
    "Soldier",
    "Soldiers",
    "Warrior",
    "Warriors",
    "Mrs",
    # common nouns that NER over-labels
    "Monster",
    "Monsters",
    "God",
    "Goddess",
    "Gods",
    "Hand",
    "Hands",
    "Disease",
    "Mercenary",
    "Wizard",
    "Wizards",
    "Earth",
    "Rice",
    "Magic",
    "Cook",
    "Postpartum",
    "Sea",
    "Care",
    # verbs / adjectives that NER mislabels
    "Perfect",
    "Speak",
    "Money",
}

# Leading articles to strip when cleaning surface forms
_ARTICLES = {"the", "a", "an"}

# Sentence-initial verbs / gerunds that produce fragment candidates.
# A multi-word phrase led by one of these is a clause fragment, not a name.
_FRAGMENT_LEADS = {
    # Common gerunds in fiction narration
    "Hearing",
    "Seeing",
    "Watching",
    "Following",
    "Regarding",
    "Thinking",
    "Knowing",
    "Feeling",
    "Wondering",
    "Asking",
    "Saying",
    "Looking",
    "Turning",
    "Walking",
    "Standing",
    "Making",
    "Taking",
    "Using",
    "Going",
    "Coming",
    "Being",
    "Having",
    "Doing",
    "Getting",
    "Keeping",
    "Leaving",
    "Bringing",
    "Calling",
    "Finding",
    "Giving",
    "Putting",
    "Showing",
    "Telling",
    "Trying",
    "Wanting",
    "Wishing",
    "Hoping",
    "Noticing",
    "Realizing",
    "Remembering",
    "Deciding",
    "Observing",
    # Additional gerunds that produce fragments
    "Ignoring",
    "Approaching",
    "Arriving",
    "Avoiding",
    "Becoming",
    "Believing",
    "Catching",
    "Checking",
    "Closing",
    "Considering",
    "Continuing",
    "Covering",
    "Creating",
    "Crossing",
    "Entering",
    "Examining",
    "Expecting",
    "Facing",
    "Finishing",
    "Grabbing",
    "Holding",
    "Imagining",
    "Including",
    "Judging",
    "Letting",
    "Lifting",
    "Living",
    "Missing",
    "Moving",
    "Opening",
    "Passing",
    "Picking",
    "Pointing",
    "Pulling",
    "Pushing",
    "Raising",
    "Reaching",
    "Reading",
    "Receiving",
    "Recognizing",
    "Removing",
    "Returning",
    "Running",
    "Sensing",
    "Setting",
    "Sitting",
    "Speaking",
    "Starting",
    "Stopping",
    "Studying",
    "Suggesting",
    "Supporting",
    "Swinging",
    "Thanking",
    "Throwing",
    "Touching",
    "Understanding",
    "Waiting",
    "Wearing",
    "Working",
}

# Confidence below which a policy is flagged for human review (PLAN.md §3 / D10)
_REVIEW_CONFIDENCE_THRESHOLD = 0.6


def _normalize(text: str) -> str:
    """Normalize text for grouping: lowercase, strip accents, collapse whitespace/hyphens."""
    text = unicodedata.normalize("NFKD", text)
    # Remove accent marks
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    # Collapse hyphens and whitespace
    text = re.sub(r"[-\s]+", " ", text)
    # Remove possessive
    text = re.sub(r"'s\b", "", text)
    return text


def _edit_distance(a: str, b: str) -> int:
    """Simple Levenshtein edit distance."""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[len(b)]


def _normalized_edit_distance(a: str, b: str) -> float:
    """Edit distance normalized by max length. 0.0 = identical, 1.0 = completely different."""
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0
    return _edit_distance(a, b) / max_len


# ----------------------------------------------------------------------- #
# Stage 1: Aggregation
# ----------------------------------------------------------------------- #


def _aggregate_signals(signals: List[Signal]) -> Dict[str, List[Signal]]:
    """Group signals by normalized text.

    Returns a dict mapping normalized form → list of signals.
    Each group represents a candidate policy.
    """
    groups: Dict[str, List[Signal]] = defaultdict(list)
    for s in signals:
        key = _normalize(s.text)
        groups[key].append(s)
    return groups


# ----------------------------------------------------------------------- #
# Stage 2: Variant clustering
# ----------------------------------------------------------------------- #


def _cluster_variants(
    groups: Dict[str, List[Signal]],
    similarity_threshold: float = 0.3,
) -> Dict[str, List[Signal]]:
    """Merge groups whose normalized keys are near-duplicates.

    Two merges happen here:
    1. Word-order duplicates: groups with the same token multiset
       (e.g. "Sinclair Count" and "Count Sinclair") are merged — these are
       the same entity written in different word order.
    2. Edit-distance near-duplicates within `similarity_threshold`
       (e.g. "Carlon" ~ "Calron" when the threshold is tuned).

    The group with more signals absorbs the other.

    Args:
        groups: Output of _aggregate_signals.
        similarity_threshold: Max normalized edit distance to merge.

    Returns:
        Merged groups.
    """

    TITLE_STOPWORDS = {
        "count", "countess", "lord", "lady", "sir", "madam", "chief", "elder", "master",
        "saint", "king", "queen", "prince", "princess", "captain", "general", "brother",
        "sister", "patriarch", "matriarch", "young", "old", "senior", "junior", "wizard",
        "apprentice", "guard", "soldier", "village", "city", "town", "castle", "palace",
        "sect", "clan", "family", "house", "mountain", "river", "forest", "valley", "lake",
        "sword", "blade", "demon", "divine", "holy", "dark", "light", "grand", "great",
        "high", "supreme", "emperor", "empress", "duke", "duchess", "baron", "baroness",
        "marquis", "the", "and", "of", "in", "at", "to", "for", "with"
    }

    def _tokens(key: str) -> Tuple[str, ...]:
        return tuple(sorted(_normalize(key).split()))

    keys = sorted(groups.keys())
    merged: Dict[str, List[Signal]] = {}
    absorbed: Set[str] = set()

    for i, k1 in enumerate(keys):
        if k1 in absorbed:
            continue
        cluster = list(groups[k1])
        t1 = _tokens(k1)
        for j in range(i + 1, len(keys)):
            k2 = keys[j]
            if k2 in absorbed:
                continue
            # (1) word-order duplicate: identical token multiset
            if _tokens(k2) == t1:
                cluster.extend(groups[k2])
                absorbed.add(k2)
                continue
            # Check if one is a single-token proper subset of the other (e.g. "sinclair" vs "count sinclair")
            # We do NOT absorb single-token subsets here because mine_policies (§3 / D10) explicitly emits
            # them as distinct policies with needs_review=True ("prompted" mode).
            t2 = _tokens(k2)
            is_bare_subset = (len(t2) == 1 and set(t2) < set(t1)) or (len(t1) == 1 and set(t1) < set(t2))
            if not is_bare_subset:
                # (2) substring containment for multi-word variants (e.g. "wizard perot" vs "arch-wizard perot")
                if (k1 in k2 or k2 in k1) and min(len(k1), len(k2)) >= 4:
                    shorter_tokens = t1 if len(k1) <= len(k2) else t2
                    if any(tok not in TITLE_STOPWORDS for tok in shorter_tokens):
                        cluster.extend(groups[k2])
                        absorbed.add(k2)
                        continue
                # (3) token intersection: shared core word of length >= 4 between multi-word variants
                shared_tokens = {tok for tok in (set(t1) & set(t2)) if tok not in TITLE_STOPWORDS}
                if any(len(tok) >= 4 for tok in shared_tokens) and len(t1) > 1 and len(t2) > 1:
                    cluster.extend(groups[k2])
                    absorbed.add(k2)
                    continue
            # (4) edit-distance near-duplicate
            if _normalized_edit_distance(k1, k2) <= similarity_threshold:
                cluster.extend(groups[k2])
                absorbed.add(k2)
        merged[k1] = cluster

    return merged


def _pick_canonical(signals: List[Signal]) -> Tuple[str, List[str]]:
    """Pick the canonical form (most frequent variant) and collect aliases.

    Prefers a surface form that does not begin with a stop word / stop prefix
    (e.g. "Behind Dominic" is rejected in favour of "Chief Dominic").

    Returns:
        (canonical_form, list_of_aliases)
    """
    # Count each exact surface form (light cleanup of stray quotes)
    form_counts: Dict[str, int] = defaultdict(int)
    for s in signals:
        form_counts[s.text.strip().strip("'`\"")] += 1

    # Prefer a form whose first token is NOT a generic/common-noun stop word or a
    # fragment lead. Title prefixes ("Count", "Lord", ...) are legitimate name
    # leaders and must NOT be penalized — otherwise "Count Sinclair" loses to the
    # word-order variant "Sinclair Count".
    _PENALTY_WORDS = (_STOP_WORDS - set(_TITLE_PREFIXES)) | _FRAGMENT_LEADS

    def _canonical_key(form: str) -> Tuple[int, int]:
        first = form.split()[0] if form.split() else ""
        penalty = 1 if first in _PENALTY_WORDS else 0
        return (penalty, -form_counts[form])

    canonical = min(form_counts, key=_canonical_key)  # type: ignore
    aliases = [form for form in form_counts if form != canonical]

    return canonical, aliases


def _clean_match_forms(canonical: str, aliases: List[str]) -> Tuple[str, List[str]]:
    """Clean canonical + alias surface forms.

    - Strips surrounding quotes / punctuation / stray whitespace.
    - Drops leading articles ("the", "a", "an").
    - Drops alias forms that begin with a stop word / stop prefix
      (e.g. "Behind Dominic" is a sentence fragment, not a name).

    Returns:
        (cleaned_canonical, cleaned_alias_list)
    """

    def _clean(form: str) -> str:
        f = form.strip().strip("'`\".,;:!?()[]{}")
        # Strip a single leading article
        parts = f.split()
        if parts and parts[0].lower() in _ARTICLES:
            parts = parts[1:]
        return " ".join(parts).strip()

    canonical = _clean(canonical)
    seen: Set[str] = set()
    cleaned: List[str] = []
    for a in aliases:
        ca = _clean(a)
        if not ca or ca == canonical:
            continue
        first = ca.split()[0] if ca.split() else ""
        if first in _STOP_WORDS or first in _STOP_PREFIXES:
            continue  # sentence fragment, not a name variant
        if ca not in seen:
            seen.add(ca)
            cleaned.append(ca)
    return canonical, cleaned


def _is_generic(canonical: str) -> bool:
    """True if the canonical form is a clear false positive.

    Rules:
    - Single-word canonical in _GENERIC_STANDALONE → generic (DROP)
    - Multi-word canonical where ALL words are in _GENERIC_STANDALONE → generic (DROP)
    - Multi-word canonical where at least one word is NOT generic → NOT generic (KEEP)
      This preserves "Count's Castle", "Ming Dynasty", "Devil's Hand" etc.
    """
    tokens = [t for t in canonical.split() if t]
    if not tokens:
        return True
    # Single word: check against standalone generics
    if len(tokens) == 1:
        return tokens[0] in _GENERIC_STANDALONE
    # Multi-word: only generic if ALL words are standalone generics
    return all(t in _GENERIC_STANDALONE for t in tokens)


# ----------------------------------------------------------------------- #
# Stage 3: Scoring + Policy construction
# ----------------------------------------------------------------------- #


def _infer_type(signals: List[Signal]) -> str:
    """Infer the policy type from the signal extractors that produced it."""
    extractors = {s.extractor for s in signals}
    types = {s.type for s in signals}

    if "honorific" in types:
        return "honorific"
    if any(e.startswith("terminology.") for e in extractors):
        return "terminology"
    return "entity-naming"


def mine_policies(
    signals: List[Signal],
    total_chapters: int,
    min_support: int = 2,
    min_confidence: float = 0.4,
    similarity_threshold: float = 0.3,
    confidence_base: float = 0.5,
    confidence_per_occurrence: float = 0.03,
    confidence_cap: float = 0.99,
    deterministic_threshold: float = 0.8,
) -> List[Policy]:
    """Convert raw signals into verified policies.

    Args:
        signals: Raw signals from extractors.
        total_chapters: Total number of chapters in the corpus.
        min_support: Minimum chapters a candidate must appear in.
        min_confidence: Minimum confidence to emit a policy.
        similarity_threshold: Max edit distance for variant clustering.
        confidence_base: Base confidence score.
        confidence_per_occurrence: Confidence increment per occurrence.
        confidence_cap: Maximum confidence score.
        deterministic_threshold: Confidence above which policy is deterministic.

    Returns:
        List of Policy objects, sorted by confidence (descending).
    """
    # Stage 1: Aggregate
    groups = _aggregate_signals(signals)

    # Stage 2: Cluster variants
    clustered = _cluster_variants(groups, similarity_threshold=similarity_threshold)

    # Stage 3: Score and build policies
    policies: List[Policy] = []
    policy_id = 0

    for _norm_key, group_signals in clustered.items():
        # Check min_support: how many distinct chapters?
        chapters_present: Set[int] = {s.chapter for s in group_signals}
        if len(chapters_present) < min_support:
            continue

        # Pick canonical form and aliases
        canonical, aliases = _pick_canonical(group_signals)

        # Clean surface forms (strip quotes/articles, drop fragment aliases)
        canonical, aliases = _clean_match_forms(canonical, aliases)
        if not canonical:
            continue

        # Rules backend: drop clear false positives (generic nouns / standalone titles)
        if _is_generic(canonical):
            continue

        # Drop clause-fragment candidates led by a sentence-initial verb
        # (e.g. "Hearing Calron," is the start of a sentence, not a name).
        if canonical.split()[0] in _FRAGMENT_LEADS:
            continue

        # Count occurrences
        form_counts: Dict[str, int] = defaultdict(int)
        for s in group_signals:
            form_counts[s.text] += 1
        total_occurrences = sum(form_counts.values())
        canonical_count = form_counts[canonical]

        # Collect a few example sentences (Evidence layer) for LLM review context
        example_contexts: List[str] = []
        for s in group_signals:
            ctx = (s.context or "").strip()
            if ctx and ctx not in example_contexts:
                example_contexts.append(ctx)
            if len(example_contexts) >= 3:
                break

        # Compute scores
        freq = score_frequency(len(chapters_present), total_chapters)
        consistency = score_consistency(canonical_count, total_occurrences)

        scores = {
            "frequency": round(freq, 3),
            "consistency": round(consistency, 3),
            "context": 1.0,  # placeholder for v0
        }

        confidence = compute_confidence(
            scores,
            base=confidence_base,
            per_occurrence=confidence_per_occurrence,
            occurrence_count=total_occurrences,
            cap=confidence_cap,
        )

        if confidence < min_confidence:
            continue

        # Build match list: canonical + all aliases
        match_forms = [canonical] + sorted(set(aliases))

        # Determine applies mode
        applies = "deterministic" if confidence >= deterministic_threshold else "prompted"

        # Infer type
        policy_type = _infer_type(group_signals)

        policy_id += 1
        policies.append(
            Policy(
                id=f"p_{policy_id:03d}",
                type=policy_type,
                trigger=canonical,
                match=match_forms,
                action={"render_as": canonical},
                applies=applies,
                confidence=round(confidence, 3),
                scores=scores,
                evidence=sorted(chapters_present),
                contexts=example_contexts,
            )
        )

    # Sort by confidence descending
    policies.sort(key=lambda p: p.confidence, reverse=True)

    # Flag ambiguous policies for human review (PLAN.md §3 / D10):
    # a single-token canonical that is a proper subset of another same-type
    # policy is redundant/ambiguous (e.g. "Sinclair" inside "Count Sinclair").
    for p in policies:
        if p.needs_review:
            continue
        toks_p = set(p.trigger.split())
        if len(toks_p) != 1:
            continue
        for q in policies:
            if q is p or q.type != p.type or q.needs_review:
                continue
            if toks_p < set(q.trigger.split()):
                p.needs_review = True
                p.note = (p.note + f"; ambiguous subset of {q.id}").strip("; ")
                break

    # Low-confidence policies are flagged and forced into prompted mode
    # (never applied by the deterministic pre-pass).
    for p in policies:
        if p.confidence < _REVIEW_CONFIDENCE_THRESHOLD:
            p.needs_review = True
            p.applies = "prompted"
            if "low confidence" not in p.note.lower():
                p.note = (p.note + "; low confidence, needs review").strip("; ")
        # Any flagged policy must not be deterministic
        if p.needs_review and p.applies == "deterministic":
            p.applies = "prompted"

    # Re-number IDs after sorting / flagging
    for i, p in enumerate(policies, start=1):
        p.id = f"p_{i:03d}"

    return policies
