"""Rewriter (PLAN.md §6 M1, §8, §11).

Orchestrates the v0 rewrite pipeline for a single MTL passage:

    Retriever  ->  Conflict Resolver  ->  Deterministic Pre-pass  ->  (LLM Rewrite)

The deterministic pre-pass guarantees the high-confidence terminology. The
lower-confidence / context-dependent policies are assembled into an LLM prompt
as explicit instructions (Mechanism 2). A change trace records every
deterministic edit for explainability.

The LLM call reuses the OpenAI-compatible client (same backend as verification).
"""

import json
import logging
import os
import re
import time
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv
from openai import RateLimitError

from translator_memory_engine.eval.faith import _entities, _novel
from translator_memory_engine.memory.store import PolicyStore
from translator_memory_engine.policy import Policy
from translator_memory_engine.retrieve.retriever import PolicyRetriever
from translator_memory_engine.rewrite.clean import clean_mtl_artifacts
from translator_memory_engine.rewrite.conflict import resolve
from translator_memory_engine.rewrite.prepass import apply_prepass
from translator_memory_engine.rewrite.shield import restore_entities, shield_entities

logger = logging.getLogger("tme.rewrite")


# ---------------------------------------------------------------------------
# Rotating LLM client (multiple API keys for rate-limit resilience)
# ---------------------------------------------------------------------------


class GroqRotatingClient:
    """OpenAI-compatible client that rotates across multiple API keys.

    When a rate-limit error occurs, automatically falls back to the next key.
    Cycles through all keys up to ``max_rounds`` times before giving up.
    """

    def __init__(self, keys: List[str], base_url: Optional[str] = None, max_rounds: int = 2):
        from openai import OpenAI

        client_kwargs: Dict[str, Any] = {"base_url": base_url} if base_url else {}
        self._clients = [OpenAI(api_key=k, **client_kwargs) for k in keys]
        self._idx = 0
        self._max_rounds = max_rounds
        self._num_keys = len(keys)

    def chat_completions_create(self, **kwargs):
        """Call chat.completions.create, rotating keys on rate-limit errors."""
        last_err: Optional[Exception] = None
        for _ in range(self._num_keys * self._max_rounds):
            try:
                return self._clients[self._idx].chat.completions.create(**kwargs)
            except RateLimitError as e:
                last_err = e
                logger.warning(f"Rate limit on key #{self._idx + 1}, rotating to next key...")
                self._idx = (self._idx + 1) % self._num_keys
                time.sleep(5)
        if last_err is not None:
            raise last_err
        raise RuntimeError("Groq rate limit retries exhausted or zero retries configured.")


def _get_groq_keys(api_key_env: str = "LLM_API_KEY") -> List[str]:
    """Load all GROQ_API_KEY* values from environment.

    If the caller's ``api_key_env`` is not set, also tries loading from
    ``.env`` via ``load_dotenv()``.  Returns an empty list when no keys
    are available (keeps the LLM path as a no-op for tests that clear env vars).
    """
    load_dotenv(override=True)
    primary = os.environ.get(api_key_env, "")
    if not primary and api_key_env != "LLM_API_KEY":
        primary = os.environ.get("GROQ_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
    if primary:
        extra_keys = sorted(
            [k for k in os.environ if k.startswith("GROQ_API_KEY") and os.environ[k] and os.environ[k] != primary]
        )
        extras = [os.environ[k] for k in extra_keys]
        return [primary] + extras
    return []


# ---------------------------------------------------------------------------
# Known MTL error corrections (data/known_errors.json)
# ---------------------------------------------------------------------------

_KNOWN_ERRORS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "known_errors.json")


def _load_known_errors() -> List[Dict]:
    """Load known MTL error corrections from JSON."""
    try:
        with open(_KNOWN_ERRORS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def scan_known_errors(text: str, known_errors: Optional[List[Dict]] = None) -> List[Dict]:
    """Scan MTL text for known error phrases and return matches.

    Returns a list of dicts with keys: id, mtl_phrase, correct_translation,
    korean_source, context. Only returns errors that are actually present in text.
    """
    if known_errors is None:
        known_errors = _load_known_errors()
        logger.debug(f"Loaded {len(known_errors)} known errors from {_KNOWN_ERRORS_PATH}")

    matches = []
    for error in known_errors:
        phrase = error.get("mtl_phrase", "")
        if phrase and re.search(re.escape(phrase), text, re.IGNORECASE):
            matches.append(error)
            logger.debug(f"Known error detected: '{phrase}' → '{error.get('correct_translation', '?')}'")
    if matches:
        logger.info(f"Detected {len(matches)} known MTL errors for correction")
    return matches


def apply_known_errors(
    text: str,
    known_errors: Optional[List[Dict]] = None,
    protected_terms: Optional[Iterable[str]] = None,
    with_trace: bool = False,
) -> str | Tuple[str, List[Dict[str, Any]]]:
    """Apply safe known-error corrections without touching protected entities.

    Rules are whole-token matches by default. Short or ambiguous entries can set
    ``auto_apply: false`` in ``known_errors.json`` and remain available for
    diagnostics without silently rewriting legitimate prose or character names.
    """
    if known_errors is None:
        known_errors = _load_known_errors()

    out_text = text
    trace: List[Dict[str, Any]] = []
    protected = [term for term in (protected_terms or []) if term]
    for error in sorted(known_errors, key=lambda item: len(item.get("mtl_phrase", "")), reverse=True):
        if error.get("auto_apply", True) is False:
            continue
        phrase = error.get("mtl_phrase", "")
        correct = error.get("correct_translation", "")
        if phrase and correct:
            protected_spans = []
            for term in protected:
                protected_spans.extend(
                    (m.start(), m.end())
                    for m in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", out_text, re.IGNORECASE)
                )
            pattern = re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE)

            def replace(match: re.Match) -> str:
                if any(not (match.end() <= start or match.start() >= end) for start, end in protected_spans):
                    return match.group(0)
                trace.append(
                    {
                        "original": match.group(0),
                        "output": correct,
                        "rule_id": error.get("id", "known-error"),
                        "kind": "known_error",
                        "span": [match.start(), match.end()],
                    }
                )
                return correct

            out_text = pattern.sub(replace, out_text)
    return (out_text, trace) if with_trace else out_text


def _load_policies(source: Any) -> List[Policy]:
    """Load policies from various sources.

    Args:
        source: One of:
            - str: File path to policies.jsonl (legacy/CLI mode)
            - List[Policy]: Already-loaded policy objects (SQLite mode)
            - List[dict]: Policy dicts from ORM conversion (SQLite mode)
            - Any other: raises ValueError

    Returns:
        List of Policy dataclass instances.
    """
    if isinstance(source, list):
        policies = []
        for item in source:
            if isinstance(item, Policy):
                policies.append(item)
            elif isinstance(item, dict):
                policies.append(Policy(**item))
            else:
                raise ValueError(f"Unsupported policy item type: {type(item)}")
        return policies
    if isinstance(source, str):
        store = PolicyStore()
        store.load(source)
        return store.all()
    raise ValueError(f"Unsupported policies source type: {type(source)}")


def _align_mtl_entities(
    mtl_text: str,
    glossary: List[Dict],
    client,
    model: str,
) -> Dict[str, str]:
    """One-shot LLM call to map MTL transliterations to canonical entity names.

    Extracts capitalized multi-word phrases from the MTL and asks the LLM to
    map them against the known glossary. Returns a dict like
    {"Noh Young-ju": "Lord Noh", "Raki": "Laki"}.
    """
    if not glossary or not client:
        return {}

    # Build a compact glossary table for the prompt
    glossary_lines = []
    for entry in glossary:
        canon = entry.get("canonical", "")
        aliases = entry.get("match", [])
        if canon:
            alias_str = ", ".join(aliases) if aliases else "(none)"
            glossary_lines.append(f"- {canon} (aliases: {alias_str})")
    glossary_table = "\n".join(glossary_lines)

    # Extract capitalized multi-word phrases from MTL (simple heuristic)
    import spacy

    try:
        _spacy_nlp = spacy.load("en_core_web_sm")
    except Exception:
        return {}
    doc = _spacy_nlp(mtl_text)  # parse full chapter so late-introduced entities are caught
    mtl_entities = set()
    for ent in doc.ents:
        if ent.label_ in ("PERSON", "ORG", "GPE", "LOC"):
            text = ent.text.strip()
            if len(text) > 1 and text.lower() not in (
                "i",
                "he",
                "she",
                "it",
                "we",
                "they",
                "you",
            ):
                mtl_entities.add(text)
    if not mtl_entities:
        return {}

    # Cap to top 45 unique entities to avoid token bloat in the LLM prompt
    entity_list = "\n".join(f"- {e}" for e in sorted(mtl_entities)[:45])

    prompt = (
        "Map these MTL (machine-translated) entity names to known canonical names.\n"
        "If an MTL name corresponds to a canonical entity, return the mapping.\n"
        "If an MTL name is NEW (not in the glossary), map it to null.\n\n"
        'Return ONLY a JSON object like: {"MTL Name": "Canonical Name"} or '
        '{"MTL Name": null}. No other text.\n\n'
        f"=== KNOWN CANONICAL ENTITIES ===\n{glossary_table}\n\n"
        f"=== MTL ENTITIES TO MAP ===\n{entity_list}"
    )

    try:
        resp = _llm_complete(
            client,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a terminology mapper. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"```\s*$", "", raw)
        mapping = json.loads(raw)
        if not isinstance(mapping, dict):
            return {}
        # Only return valid mappings (non-null, non-identical)
        return {str(k): str(v) for k, v in mapping.items() if v and k != v}
    except Exception:
        return {}


def _llm_complete(client, retries: int = 5, backoff: float = 15.0, **kwargs):
    """Call the chat completion with retry/backoff for TPM rate limits.

    Supports both plain OpenAI clients and ``GroqRotatingClient`` instances.
    For rotating clients, key rotation is handled internally; this wrapper
    adds per-key backoff on top.
    """
    if isinstance(client, GroqRotatingClient):
        return client.chat_completions_create(**kwargs)

    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            last = e
            if attempt == retries - 1:
                break
            time.sleep(backoff * (attempt + 1))
    if last is not None:
        raise last
    raise RuntimeError("LLM completion retries exhausted or zero retries configured.")


def _normalize_newlines(text: str) -> str:
    """Normalize newlines so that solitary single newlines are converted to double newlines,
    ensuring that chunks and the frontend treat every intended line break as a distinct paragraph.
    """
    # Convert \r\n to \n
    text = text.replace("\r\n", "\n")
    # Replace single \n with \n\n, but leave \n\n (or more) alone
    return re.sub(r"(?<!\n)\n(?!\n)", "\n\n", text)


def _split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _chunk_text(
    text: str,
    target_chars: int = 3600,
    min_chars: int = 2800,
    hard_cap: int = 4800,
) -> List[str]:
    """Split text into chunks with dialogue and scene boundary awareness.

    Instead of a blind character cutoff that splits mid-dialogue, this chunker uses
    a soft target (`target_chars`) and accumulates paragraphs until it finds a clean
    narrative boundary (scene break `***` / `---` or descriptive transition) or until
    it hits `hard_cap`. If two adjacent paragraphs are both dialogue turns (starting/ending
    with quotation marks), the chunker avoids splitting between them.
    """
    paras = _split_paragraphs(text)
    if not paras:
        return []

    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0

    def flush() -> None:
        nonlocal cur, cur_len
        if cur:
            chunks.append("\n\n".join(cur))
            cur = []
            cur_len = 0

    def is_dialogue_turn(paragraph: str) -> bool:
        stripped = paragraph.strip()
        return bool(
            stripped
            and (
                stripped.startswith(('"', "“", "'"))
                or stripped.endswith(('"', "”", "'"))
                or '"' in stripped
                or "“" in stripped
                or "”" in stripped
            )
        )

    def is_active_dialogue(previous: str, current: str) -> bool:
        return is_dialogue_turn(previous) and is_dialogue_turn(current)

    for p in paras:
        # If a single paragraph is longer than hard_cap, split at sentence boundaries
        if len(p) > hard_cap:
            if cur:
                flush()
            pieces = _SENT_RE.split(p)
            for piece in pieces:
                if not piece.strip():
                    continue
                if cur_len + len(piece) > target_chars and cur:
                    flush()
                cur.append(piece)
                cur_len += len(piece)
            continue

        added_len = len(p) + (2 if cur else 0)
        if cur_len + added_len > hard_cap and cur:
            prev_p = cur[-1].strip()
            # Preserve a live exchange through a bounded overflow. If the
            # exchange is unusually long, the next forced split still receives
            # the final turns as context in rewrite().
            if not is_active_dialogue(prev_p, p) or cur_len + added_len > hard_cap + 1200:
                flush()
        elif cur_len + added_len >= target_chars and cur_len >= min_chars and cur:
            # Check if we should flush before adding `p`:
            # 1. Check if `p` or `cur[-1]` is a scene break
            prev_p = cur[-1].strip()
            is_scene_break = prev_p in ("***", "---", "* * *", "- - -") or p.strip() in ("***", "---", "* * *", "- - -")

            # 2. Check if we are right in the middle of back-to-back dialogue turns
            in_active_dialogue = is_active_dialogue(prev_p, p)

            if is_scene_break or not in_active_dialogue:
                flush()

        cur.append(p)
        cur_len += len(p) + (2 if len(cur) > 1 else 0)

    flush()
    return chunks


def _align_reference_chunks(mtl_chunks: List[str], reference_text: str) -> List[str]:
    """Slice reference_text proportionally to match the paragraph counts of each MTL chunk.

    In supervised mode, character-based chunking on translation vs reference causes
    rapid alignment drift because translations expand/contract differently from MTL.
    By matching the proportional paragraph/line distribution of `mtl_chunks`, each
    reference chunk stays locked to the exact same scene as its MTL counterpart.
    """
    ref_paras = _split_paragraphs(reference_text)
    if not ref_paras or not mtl_chunks:
        return []

    mtl_para_counts = [len(_split_paragraphs(ch)) for ch in mtl_chunks]
    total_mtl_paras = sum(mtl_para_counts)
    if total_mtl_paras == 0:
        return [reference_text] * len(mtl_chunks)

    # Compute cumulative boundaries once. Independent per-chunk rounding can
    # consume every reference paragraph before the final MTL chunk.
    boundaries = [0]
    cumulative = 0
    for count in mtl_para_counts:
        cumulative += count
        boundaries.append(round(cumulative / total_mtl_paras * len(ref_paras)))

    ref_chunks: List[str] = []
    for k in range(len(mtl_chunks)):
        start_idx, end_idx = boundaries[k], boundaries[k + 1]
        if end_idx <= start_idx:
            # There are fewer reference paragraphs than MTL chunks. Reuse the
            # nearest paragraph as context rather than silently sending an
            # empty reference and pretending alignment exists.
            nearest = min(len(ref_paras) - 1, max(0, start_idx))
            chunk_paras = [ref_paras[nearest]]
        else:
            chunk_paras = ref_paras[start_idx:end_idx]
        ref_chunks.append("\n\n".join(chunk_paras))
    return ref_chunks


_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _chunk_integrity_violations(source: str, candidate: str) -> List[str]:
    """Return deterministic reasons to reject an unsafe chunk rewrite."""
    if not candidate.strip():
        return ["empty output"]

    violations: List[str] = []
    if len(_split_paragraphs(candidate)) < len(_split_paragraphs(source)):
        violations.append("paragraph count decreased")

    source_numbers = Counter(_NUMBER_RE.findall(source))
    candidate_numbers = Counter(_NUMBER_RE.findall(candidate))
    missing_numbers = [number for number, count in source_numbers.items() if candidate_numbers[number] < count]
    if missing_numbers:
        violations.append(f"missing numeric values: {', '.join(missing_numbers[:5])}")
    return violations


def _apply_deterministic(text: str, policies: List[Policy]) -> str:
    """Re-run the deterministic name/honorific pre-pass over `text`.

    Used both before the LLM (primary) and after it, so that canonical forms
    survive even if the model renamed or dropped a named entity.
    """
    retriever = PolicyRetriever(policies)
    matched = retriever.retrieve(text)
    resolution = resolve(text, matched)
    out, _ = apply_prepass(text, resolution)
    return out


def _strip_echo(text: str) -> str:
    """Remove prompt scaffolding some models echo into the output.

    Small models occasionally parrot the "CHAPTER TO REWRITE:" label or preface
    the result with "Here is the repaired text:". Strip those and any leading
    code fence so the stored text is clean prose.
    """
    if not text:
        return text
    out = text.strip()
    # Drop a leading ``` fence (with optional language tag)
    out = re.sub(r"^```[a-zA-Z]*\s*", "", out)
    out = re.sub(r"```\s*$", "", out)
    # Drop a "Here is the repaired text:" style preface
    out = re.sub(
        r"^\s*(here is|below is|sure[,\s]*here is)?\s*(the)?\s*repaired text[^\n]*:?\s*\n",
        "",
        out,
        flags=re.IGNORECASE,
    )
    # If the model echoed the literal "CHAPTER TO REWRITE:" label, cut everything
    # up to and including it.
    marker = "CHAPTER TO REWRITE:"
    idx = out.find(marker)
    if idx != -1:
        out = out[idx + len(marker) :].strip()
    return out.strip()


# Entity labels we treat as "named-entity inventions" worth guarding against.
_GUARD_LABELS = {"PERSON", "ORG", "GPE", "LOC"}


def _canonical_set(glossary: Optional[List[Dict]] = None) -> set:
    """Build a set of all canonical names and alias forms from the glossary.

    Any entity whose lowercased form matches a canonical or alias is considered
    "known" and must never be flagged as novel by the faithfulness guard.
    """
    if not glossary:
        return set()
    names: set = set()
    for entry in glossary:
        canon = entry.get("canonical", "")
        if canon:
            names.add(canon.lower())
        for alias in entry.get("match", []):
            if alias:
                names.add(alias.lower())
    return names


def _novel_entities(gen: str, src: str, whitelist: Optional[set] = None) -> set:
    """PERSON/ORG/GPE/LOC spans in `gen` whose text is absent from `src`.

    If ``whitelist`` is provided, entities matching a whitelisted name are
    excluded from the novel set (they are canonical, not invented).
    """
    novel = _novel(_entities(gen, _GUARD_LABELS), src)
    if whitelist:
        novel = {e for e in novel if e.lower() not in whitelist}
    return novel


def _faithfulness_prompt(output: str, novel: set, source: str) -> str:
    """Prompt that asks the model to ONLY strip invented names, nothing else."""
    names = ", ".join(sorted(novel))
    return (
        "Your previous output introduced the following names that do NOT appear "
        f"anywhere in the source material: {names}.\n"
        "That is a faithfulness violation. Edit ONLY to remove or neutralize those "
        "names (replace with a generic noun such as 'the man' / 'the merchant', or "
        "omit the sentence if it adds nothing). Do NOT add or change any other "
        "content, and preserve the rest verbatim.\n\n"
        "Return the full corrected chapter text, no scaffolding.\n\n"
        "<SourceReference>\n"
        f"{source}\n"
        "</SourceReference>\n\n"
        "<CandidateOutput>\n"
        f"{output}\n"
        "</CandidateOutput>"
    )


# Few-shot style anchor from the good corpus (used only as the ultimate fallback
# when neither a published reference nor a learned style bank is available).
_STYLE_REFERENCE = [
    '"Elder, are you all right?"',
    '"You\'re overthinking it, Calron. Eat."',
    '"He\'s the one who appointed me, after all."',
    "The boy's stomach growled loud enough to shame him.",
    "She didn't smile, exactly — more a baring of teeth that passed for warmth.",
]

# The LLM task is FAITHFUL REPAIR, not free rewriting: keep the existing wording,
# only fix broken MTL, and preserve the translator's voice/metaphors/onomatopoeia.
# Never invent. (8B models love to echo the scaffolding — see _strip_echo.)
_FALLBACK_RULES = """<Rules>
1. REPAIR, DO NOT REAUTHOR: Correct broken machine translation into fluent, natural English while preserving every source-supported event, relationship, and emotional beat. Improve rhythm and word choice only when the meaning remains grounded in the input. Never add color, motivations, dialogue, or detail that the input does not support.
2. RESOLVE MACHINE TRANSLATION ERRORS (DECEPTIVE ARTIFACTS):
   Machine translations frequently output grammatically valid English words that make zero logical sense inside the scene (due to homograph dictionary lookups, flipped pronouns, or literalized idioms).
   Before preserving any sentence or exclamation verbatim, verify its Discourse Coherence against the immediate scene:
   - Conversational Logic: If a standalone noun, exclamation, or idiom violates the conversational or emotional logic of the scene (e.g. an unrelated economic/technical noun during a physical confrontation, or a bizarre non-sequitur), recognize it as a deceptive MTL homograph/idiom artifact and repair it so it makes natural sense inside the scene's context.
   - Cause-and-Effect Pronoun Inversion: When pronoun cause-and-effect is inverted (e.g. an attacker hitting someone else "so that I could come to my senses" or bending "her own arm" while attacking an enemy), correct the pronouns to restore clear narrative causality.
   - Speaker Attribution & Sentence Ownership: Disentangle dialogue turns merged into single blocks, ensuring every line belongs to its rightful speaker. Correct misattributed pronouns caused by MTL pronoun dropping.
   - Inverted Negation & State Flipping (Common MTL Error): Korean double-negatives often cause machine translation to output flipped positive/negative states ("shouldn't" instead of "should", or "couldn't" instead of "could"). If a sentence logically contradicts the speaker's obvious intent due to this MTL error, flip the negation to restore the true meaning.
3. Preserve paragraph boundaries and dialogue-turn semantics. You may split a genuinely merged dialogue turn to clarify ownership, but never merge distinct paragraphs or omit a source beat.
</Rules>

<Examples>
<example>
  <error_type>Cause-and-Effect Pronoun Inversion</error_type>
  <raw_mt>I was going to finish it with just one hit so that I could come to my senses.</raw_mt>
  <repaired>I was going to finish it with just one hit so that you would come to your senses.</repaired>
</example>
<example>
  <error_type>Inverted Negation (State Flipping)</error_type>
  <raw_mt>If you missed the young man's touch, you shouldn't have said that you missed it.</raw_mt>
  <repaired>If you missed the young man's touch, you should have just said so!</repaired>
</example>
</Examples>

<Format>
- Output ONLY the repaired chapter text without conversational filler. No scaffolding or headers.
- Replicate the exact paragraph spacing of the Machine Translation. Keep every distinct dialogue turn and action tag on its own separate line.
- You may separate merged dialogue turns into new paragraphs for clarity, but you should NEVER merge existing paragraphs together into blocks.
</Format>"""


def build_prompt(
    prepassed_text: str,
    prompted_policies: List[Policy],
    reference: Optional[str] = None,
    style_profile: Optional[List[str]] = None,
    previous_tail: Optional[str] = None,
    active_cast_entries: Optional[List[Dict]] = None,
) -> tuple[str, str]:
    """Build the LLM rewrite prompt as a (system_prompt, user_prompt) tuple.

    Three modes (PLAN §15, D11):
      * reference      — supervised: a published translation of the SAME chapter
                         exists; rewrite the MTL to read like it (max fidelity).
      * style_profile  — unsupervised: no original for this chapter; preserve the
                         translator's voice using learned excerpts from the bank.
      * (neither)      — fallback faithful-repair using a fixed style anchor.

    Args:
        previous_tail: Last 1-2 paragraphs of the previous chapter, for
            cross-chapter continuity (pronoun consistency, scene flow).
    """

    lines = []
    for p in prompted_policies:
        import json

        action = p.action
        if isinstance(action, str):
            try:
                action = json.loads(action)
            except Exception:
                action = {}
        if not isinstance(action, dict):
            action = {}
        render_as = action.get("render_as", p.trigger)
        if p.type == "honorific":
            lines.append(f'- Always render "{p.trigger}" as the honorific "{render_as}".')
        elif p.type == "terminology":
            lines.append(f'- Use the terminology "{render_as}" (not variants of "{p.trigger}").')
        else:
            lines.append(f'- Render "{p.trigger}" as "{render_as}".')
    instructions = "\n".join(lines) if lines else "  (no prompted policies)"

    tail_block = ""
    if previous_tail:
        tail_block = f"\n=== PREVIOUS SCENE CONTEXT (For continuity only, DO NOT translate this) ===\n{previous_tail}\n===========================================================================\n\n"

    cast_block = ""
    if active_cast_entries:
        cast_lines = []
        for entry in active_cast_entries:
            canon = entry.get("canonical", "")
            meta = entry.get("metadata", {})
            aliases = entry.get("aliases", [])
            if isinstance(aliases, str):
                try:
                    aliases = json.loads(aliases)
                except Exception:
                    aliases = []
            if canon:
                gender = meta.get("gender", "") if isinstance(meta, dict) else ""
                identity = meta.get("race_or_identity", "") if isinstance(meta, dict) else ""
                speech = meta.get("speech_style", "") if isinstance(meta, dict) else ""

                alias_prefix = f"[Aliases/Titles: {', '.join(aliases)}]" if aliases else ""
                meta_parts = []
                if gender:
                    meta_parts.append(f"({gender})")
                if identity:
                    meta_parts.append(f"{identity}")
                if speech:
                    meta_parts.append(f"{speech}")

                meta_str = ", ".join(meta_parts)
                if alias_prefix and meta_str:
                    desc = f"{alias_prefix} {meta_str}"
                elif alias_prefix:
                    desc = alias_prefix
                elif meta_str:
                    desc = meta_str
                else:
                    desc = ""

                if desc:
                    cast_lines.append(f"- {canon} {desc}")
                else:
                    cast_lines.append(f"- {canon}")

        if cast_lines:
            cast_str = "\n".join(cast_lines)
            cast_block = (
                "\n=== ACTIVE SCENE CAST (For pronoun & dialogue accuracy) ===\n"
                "Use this cast information ONLY for pronoun resolution, dialogue attribution, and recognizing character continuity across their Aliases/Titles. "
                "Do NOT inject their background or identity into the narrative. "
                "Do NOT force-replace natural social titles or honorifics with proper names in dialogue if the title is natural to the scene.\n"
                f"{cast_str}\n"
            )

    if reference:
        system_prompt = (
            "You are an expert translator and editor for a high-quality, professionally published fantasy web-novel.\n"
            "Your task is to rewrite a rough Machine Translation (A) so it reads like the target Published Translation (B).\n"
            "ELEVATE THE PROSE: Match the phrasing, voice, tone, rhythm, and emotional weight of (B) as closely as possible. "
            "Do not output dry, literal, or clinical 'study-book' translations. Inject life, feeling, and depth into the narrative."
        )
        user_prompt = f"""{tail_block}{cast_block}
<TranslatorPolicies>
{instructions}
</TranslatorPolicies>
<Rules>
1. REPAIR AGAINST THE REFERENCE: Rewrite Machine Translation (A) into fluent prose using Published Translation (B) as same-scene evidence for voice and meaning. Do not copy unrelated wording, add unsupported detail, or replace a source event merely to sound more literary.
2. RESOLVE MACHINE TRANSLATION ERRORS (DECEPTIVE ARTIFACTS):
   Machine translations frequently output grammatically valid English words that make zero logical sense inside the scene. Before preserving any sentence verbatim, verify its Discourse Coherence against the immediate scene:
   - Conversational Logic: If a noun, exclamation, or idiom violates the conversational or emotional logic of the scene (e.g. an unrelated economic noun during a physical confrontation, or a bizarre non-sequitur), recognize it as a deceptive artifact and repair it to match (B)'s phrasing.
   - Cause-and-Effect Pronoun Inversion: When pronoun cause-and-effect is inverted (e.g. an attacker hitting someone else "so that I could come to my senses"), correct the pronoun logic to restore clear narrative causality matching (B).
   - Speaker Attribution & Sentence Ownership: Disentangle dialogue turns merged into single blocks, ensuring every line belongs to its rightful speaker matching (B). Correct misattributed pronouns caused by MTL pronoun dropping.
   - Inverted Negation & State Flipping (Common MTL Error): Korean double-negatives often cause machine translation to output flipped positive/negative states ("shouldn't" instead of "should", or "couldn't" instead of "could"). If a sentence logically contradicts the speaker's obvious intent due to this MTL error, flip the negation to restore the true meaning.
3. Preserve every beat from (A) and use (B) only to resolve meaning and style. Preserve paragraph boundaries; split only genuinely merged dialogue turns and never merge distinct paragraphs.
</Rules>

<Examples>
<example>
  <error_type>Cause-and-Effect Pronoun Inversion</error_type>
  <raw_mt>I was going to finish it with just one hit so that I could come to my senses.</raw_mt>
  <repaired>I was going to finish it with just one hit so that you would come to your senses.</repaired>
</example>
<example>
  <error_type>Inverted Negation (State Flipping)</error_type>
  <raw_mt>If you missed the young man's touch, you shouldn't have said that you missed it.</raw_mt>
  <repaired>If you missed the young man's touch, you should have just said so!</repaired>
</example>
</Examples>

<Format>
- Output ONLY the repaired chapter text without headers, scaffolding, or code fences.
- Replicate the exact paragraph spacing of the Machine Translation. Keep every distinct dialogue turn and action tag on its own separate line.
- You may separate merged dialogue turns into new paragraphs for clarity, but you should NEVER merge existing paragraphs together into blocks.
</Format>

=== (A) MACHINE TRANSLATION TO REPAIR ===
{prepassed_text}

=== (B) PUBLISHED TRANSLATION (reference) ===
{reference}"""
        return system_prompt, user_prompt

    if style_profile:
        profile_txt = "\n".join(f"- {ex}" for ex in style_profile)
        system_prompt = (
            "You are a faithful post-editor for a professionally published fantasy web-novel.\n"
            "Repair rough Machine Translation into natural English without changing source-supported facts.\n"
            "Use the voice reference only for surface style; never import its names, events, or dialogue."
        )
        user_prompt = f"""{tail_block}{cast_block}
<VoiceReference>
The following quotes are from DIFFERENT chapters by the SAME translator. Use them ONLY as stylistic inspiration for tone, rhythm, and vocabulary. DO NOT copy, insert, or weave any of these lines, characters, or dialogue into the current chapter:
{profile_txt}
</VoiceReference>

<TranslatorPolicies>
{instructions}
</TranslatorPolicies>

{_FALLBACK_RULES}

=== MACHINE TRANSLATION TO REPAIR ===
{prepassed_text}"""
        return system_prompt, user_prompt

    # Fallback (unsupervised, no style bank)
    system_prompt = (
        "You are a faithful post-editor for a professionally published fantasy web-novel.\n"
        "Repair rough Machine Translation into natural English without changing source-supported facts.\n"
        "When the input is ambiguous, preserve its uncertainty instead of inventing an explanation."
    )
    user_prompt = f"""{tail_block}{cast_block}
<TranslatorPolicies>
{instructions}
</TranslatorPolicies>

{_FALLBACK_RULES}

=== MACHINE TRANSLATION TO REPAIR ===
{prepassed_text}"""
    return system_prompt, user_prompt


def rewrite(
    text: str,
    policies_path: str = "",
    policies: Any = None,
    model: str = "llama-3.3-70b-versatile",
    base_url: Optional[str] = None,
    api_key_env: str = "LLM_API_KEY",
    do_llm: bool = False,
    reference_text: Optional[str] = None,
    style_profile: Optional[List[str]] = None,
    glossary: Optional[List[Dict]] = None,
    previous_tail: Optional[str] = None,
    temperature: float = 0.25,
    max_output_tokens: int = 3072,
    enable_alias_bridging: bool = False,
) -> Dict[str, Any]:
    """Run the full v0 rewrite pipeline on one passage.

    Args:
        text: Raw MTL passage.
        policies_path: Path to policies.jsonl (legacy/CLI mode). Ignored if
            ``policies`` is provided.
        policies: Pre-loaded policies — can be a List[Policy], List[dict], or
            a PolicyStore instance. When provided, takes precedence over
            ``policies_path`` (SQLite / web-backend mode).
        model / base_url / api_key_env: LLM backend for the optional rewrite.
        do_llm: If True, call the LLM to rewrite the pre-passed text.
        reference_text: Supervised mode — published translation of the SAME
            chapter; the LLM rewrites the MTL to read like it (max fidelity).
        style_profile: Unsupervised mode — voice excerpts from the style bank,
            used when no original exists for this chapter.
        glossary: Glossary entries for entity shielding (protects names during
            LLM rewrite by replacing with placeholders).
        previous_tail: Last 1-2 paragraphs of the previous chapter for
            cross-chapter continuity.

    Returns:
        Dict with: prepassed_text, rewritten_text, trace, conflicts,
        prompted_policies (triggers), deterministic_count, prompted_count, mode.
    """
    # Clean MTL artifacts on the input only (gold corpus is untouched).
    text = clean_mtl_artifacts(text)

    # Load policies from the provided source (in-memory list takes precedence)
    if policies is not None:
        if isinstance(policies, PolicyStore):
            policy_list = policies.all()
        else:
            policy_list = _load_policies(policies)
    else:
        policy_list = _load_policies(policies_path)
    logger.debug(f"Loaded {len(policy_list)} policies")

    # Alias bridging: use a lightweight LLM call to map MTL transliterations
    # (e.g. "Noh Young-ju") to canonical policy names (e.g. "Lord Noh").
    # This runs before the retriever so the updated match lists capture MTL forms.
    if glossary and do_llm and enable_alias_bridging:
        keys = _get_groq_keys(api_key_env)
        if keys:
            logger.debug("Running alias bridging (MTL -> canonical)...")
            _client = GroqRotatingClient(keys, base_url)
            alias_map = _align_mtl_entities(text, glossary, _client, model)
            if alias_map:
                logger.debug(f"Discovered {len(alias_map)} aliases: {list(alias_map.keys())[:5]}")
                # Inject discovered aliases into policy match lists in memory
                for p in policy_list:
                    for mtl_form, canonical in alias_map.items():
                        if p.trigger.lower() == canonical.lower() or canonical.lower() in [a.lower() for a in p.match]:
                            if mtl_form not in p.match:
                                p.match.append(mtl_form)

    retriever = PolicyRetriever(policy_list)
    matched = retriever.retrieve(text)
    logger.debug(f"Retriever matched {len(matched)} policies")

    resolution = resolve(text, matched)
    prepassed_text, trace = apply_prepass(text, resolution)
    logger.debug(f"Pre-pass applied {len(trace)} deterministic edits")

    # Known-error rules must not overwrite a canonical entity or policy form.
    protected_terms = [form for policy in policy_list for form in policy.match]
    if glossary:
        for entry in glossary:
            forms = entry.get("match", [])
            protected_terms.extend(forms if isinstance(forms, list) else [forms])
    prepassed_text, known_error_trace = apply_known_errors(
        prepassed_text,
        protected_terms=protected_terms,
        with_trace=True,
    )
    trace.extend(known_error_trace)
    logger.debug(f"Applied {len(known_error_trace)} known-error corrections")

    # Prompted (non-deterministic, non-rejected) policies for the LLM
    prompted = [p for p in matched if p.applies == "prompted" and not p.llm_rejected]
    logger.debug(f"Prompted policies for LLM: {len(prompted)}")

    # Mode: supervised (reference) > unsupervised (style bank) > fallback.
    if reference_text is not None:
        mode = "supervised_reference"
    elif style_profile is not None:
        mode = "unsupervised_stylebank"
    else:
        mode = "fallback_faithful_repair"
    logger.debug(f"Rewrite mode: {mode}")

    use_llm = do_llm
    logger.debug(f"LLM: use={use_llm}")

    # Entity shielding: replace glossary entries with placeholders before LLM,
    # restore after. This prevents the LLM from mangling entity names and makes
    # the faithfulness guard almost unnecessary for glossary entities.
    shielded_text = _normalize_newlines(prepassed_text)
    restore_map: Dict[str, str] = {}
    if glossary and use_llm:
        shielded_text, restore_map = shield_entities(shielded_text, glossary)
        logger.debug(f"Shielded {len(restore_map)} entities")

    faithfulness_source = None
    if reference_text:
        reference_text = _normalize_newlines(reference_text)
        faithfulness_source = reference_text
        if restore_map:
            placeholder_by_canonical = {canonical: placeholder for placeholder, canonical in restore_map.items()}
            reference_text, _ = shield_entities(
                reference_text,
                glossary or [],
                placeholder_by_canonical=placeholder_by_canonical,
            )

    # Long chapters exceed the small model's per-request token budget, so rewrite
    # in capped chunks (supervised: MTL chunk + matching reference chunk, aligned
    # by chunk index).
    mtl_chunks = _chunk_text(shielded_text)
    ref_chunks = _align_reference_chunks(mtl_chunks, reference_text) if reference_text else []
    logger.debug(f"Split into {len(mtl_chunks)} chunks")

    rewritten_text = shielded_text
    integrity_warnings: List[str] = []
    client = None
    if use_llm:
        keys = _get_groq_keys(api_key_env)
        if keys:
            client = GroqRotatingClient(keys, base_url)
            logger.info(f"LLM client initialized (model={model}, keys={len(keys)})")
            out_parts = []
            for k, mtl_chunk in enumerate(mtl_chunks):
                logger.debug(f"Processing chunk {k + 1}/{len(mtl_chunks)}...")
                ref_chunk = ref_chunks[k] if k < len(ref_chunks) else None

                # Context continuity between chunks
                if k == 0:
                    previous_paras = _split_paragraphs(previous_tail or "")
                    context_tail = "\n\n".join(previous_paras[-2:]) if previous_paras else ""
                else:
                    # Continuity comes from the repaired prior chunk, not the
                    # broken MTL that prompted this rewrite.
                    prev_paras = _split_paragraphs(out_parts[-1])
                    context_tail = "\n\n".join(prev_paras[-2:]) if prev_paras else ""

                # Find active cast from placeholders and known aliases/titles
                active_cast_entries = []
                if glossary:
                    active_canonicals = set()
                    if restore_map:
                        active_canonicals.update(
                            canon for ph, canon in restore_map.items() if ph in mtl_chunk or ph in context_tail
                        )
                    for entry in glossary:
                        canon = entry.get("canonical", "")
                        aliases = entry.get("aliases", [])
                        if isinstance(aliases, str):
                            try:
                                aliases = json.loads(aliases)
                            except Exception:
                                aliases = []
                        if canon in active_canonicals or any(a and a.lower() in mtl_chunk.lower() for a in aliases):
                            active_cast_entries.append(entry)

                system_prompt, user_prompt = build_prompt(
                    mtl_chunk,
                    prompted,
                    reference=ref_chunk,
                    style_profile=style_profile,
                    previous_tail=context_tail,
                    active_cast_entries=active_cast_entries,
                )
                logger.debug(
                    f"System Prompt length: {len(system_prompt)} chars | User Prompt length: {len(user_prompt)} chars"
                )
                resp = _llm_complete(
                    client,
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        {
                            "role": "user",
                            "content": user_prompt,
                        },
                    ],
                    temperature=temperature,
                    max_tokens=max_output_tokens,
                )
                candidate = _strip_echo(resp.choices[0].message.content)
                expected_placeholders = {
                    placeholder: mtl_chunk.count(placeholder) for placeholder in restore_map if placeholder in mtl_chunk
                }
                found_placeholders = set(re.findall(r"__ENT_(\d+)__", candidate))
                expected_ids = {placeholder[6:-2] for placeholder in expected_placeholders}
                valid_placeholders = all(
                    candidate.count(placeholder) == count for placeholder, count in expected_placeholders.items()
                ) and found_placeholders.issubset(expected_ids)
                violations = _chunk_integrity_violations(mtl_chunk, candidate)
                if not valid_placeholders:
                    violations.append("entity placeholders changed")
                if violations:
                    logger.warning(
                        "LLM output failed integrity checks in chunk %d (%s); using deterministic chunk",
                        k + 1,
                        "; ".join(violations),
                    )
                    integrity_warnings.append(f"Chunk {k + 1}: {'; '.join(violations)}")
                    candidate = mtl_chunk
                out_parts.append(candidate)
            rewritten_text = "\n\n".join(out_parts)
            logger.info(f"LLM rewrite complete: {len(out_parts)} chunks")

    # Restore shielded entities after LLM rewrite
    if restore_map:
        rewritten_text = restore_entities(rewritten_text, restore_map)
        logger.debug(f"Restored {len(restore_map)} entities")

    # Faithfulness guard: the small model can still invent speakers/characters
    # (e.g. ch040 'Ian'). Detect PERSON/ORG/GPE absent from the TRUE source and
    # remove them with ONE LLM re-prompt.
    #
    # In supervised mode, source = published reference. Canonical entities
    # (from the glossary) are whitelisted — they are correct by definition
    # even if absent from the reference (e.g. "Calron" fixed from "Carlon").
    #
    # In unsupervised mode, skip the guard entirely — the raw MTL is too
    # noisy to serve as a reliable source (it would false-positive on every
    # correct MTL→canonical correction like "Noh Young-ju" → "Lord Noh").
    canon = _canonical_set(glossary)
    if client is not None and faithfulness_source is not None:
        novel = _novel_entities(rewritten_text, faithfulness_source, whitelist=canon)
        if novel:
            logger.warning(f"Faithfulness guard: {len(novel)} novel entities detected: {novel}")
            before_guard = rewritten_text
            guard_prompt = _faithfulness_prompt(rewritten_text, novel, faithfulness_source)
            resp = _llm_complete(
                client,
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a faithful post-editor. You ONLY remove invented names; "
                        "you never add or alter any other content.",
                    },
                    {"role": "user", "content": guard_prompt},
                ],
                temperature=0.1,
                max_tokens=max_output_tokens,
            )
            rewritten_text = _strip_echo(resp.choices[0].message.content)
            remaining = _novel_entities(rewritten_text, faithfulness_source, whitelist=canon)
            if remaining:
                logger.warning("Faithfulness guard failed validation; restoring pre-guard output")
                rewritten_text = before_guard
            else:
                logger.info("Faithfulness guard applied")
        else:
            logger.debug("Faithfulness guard: no novel entities found")
    elif client is not None and faithfulness_source is None:
        # MTL-only mode cannot safely auto-repair every apparent name mismatch,
        # but it must surface possible inventions for editorial review.
        novel = _novel_entities(rewritten_text, prepassed_text, whitelist=canon)
        if novel:
            integrity_warnings.append(f"MTL-only review: possible novel entities: {', '.join(sorted(novel))}")

    # Re-apply the deterministic pre-pass so canonical names/honorifics survive
    # even if the LLM renamed or dropped a named entity (PLAN §8: the high-confidence
    # path must not depend on LLM compliance). Runs on the LLM output and on the
    # pre-pass-only output alike.
    rewritten_text = _apply_deterministic(rewritten_text, policy_list)

    logger.debug(f"Final output: {len(rewritten_text)} chars")
    return {
        "prepassed_text": prepassed_text,
        "rewritten_text": rewritten_text,
        "trace": trace,
        "conflicts": resolution.conflicts,
        "prompted_triggers": [p.trigger for p in prompted],
        "deterministic_count": len(trace),
        "prompted_count": len(prompted),
        "mode": mode,
        "integrity_warnings": integrity_warnings,
    }
