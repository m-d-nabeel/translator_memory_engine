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
from typing import Any, Dict, List, Optional

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


def format_known_errors_for_prompt(matches: List[Dict]) -> str:
    """Format matched known errors as prompt instructions."""
    if not matches:
        return ""

    lines = ["KNOWN MTL ERROR CORRECTIONS (apply these):"]
    for m in matches:
        phrase = m.get("mtl_phrase", "")
        correct = m.get("correct_translation", "")
        korean = m.get("korean_source", "")
        context = m.get("context", "")
        lines.append(f'  - "{phrase}" → "{correct}" (Source term: {korean}) — {context}')
    return "\n".join(lines)


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
    ensuring that chunks and the frontend treat every intended line break as a distinct paragraph."""
    # Convert \r\n to \n
    text = text.replace('\r\n', '\n')
    # Replace single \n with \n\n, but leave \n\n (or more) alone
    return re.sub(r'(?<!\n)\n(?!\n)', '\n\n', text)


def _split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _chunk_text(text: str, max_chars: int = 3500) -> List[str]:
    """Split text into chunks capped at ``max_chars``.

    Paragraphs are grouped; any single paragraph longer than the cap is further
    split at sentence boundaries. Setting max_chars=3500 (~600-700 words) ensures
    the actual story text outweighs the prompt scaffolding (~550 words) by ~1.2:1,
    preventing small models from hallucinating prompt bullets into the output while
    staying safely inside Groq's token budget. For supervised mode, the SAME chunker
    is run on the MTL and its reference so chunk k of each stays roughly aligned.
    """
    paras = _split_paragraphs(text)
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0

    def flush() -> None:
        nonlocal cur, cur_len
        if cur:
            chunks.append("\n\n".join(cur))
            cur = []
            cur_len = 0

    for p in paras:
        pieces = _SENT_RE.split(p) if len(p) > max_chars else [p]
        for piece in pieces:
            if not piece.strip():
                continue
            if cur_len + len(piece) > max_chars and cur:
                flush()
            cur.append(piece)
            cur_len += len(piece)
    flush()
    return chunks


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


def _faithfulness_prompt(output: str, novel: set) -> str:
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
        f"{output}"
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
_FALLBACK_RULES = """Repair rules:
- REWRITE MACHINE TRANSLATION (A) into fluent, natural English prose matching the translator's voice.
- RESOLVE DISCOURSE & NARRATIVE COHERENCE ANOMALIES (DECEPTIVE MTL ARTIFACTS):
  Machine translations frequently output grammatically valid English words that make zero logical sense inside the scene (due to homograph dictionary lookups, flipped pronouns, or literalized idioms).
  Before preserving any sentence or exclamation verbatim, verify its Discourse Coherence against the immediate scene:
  1. Conversational Logic: If a standalone noun, exclamation, or idiom violates the conversational or emotional logic of the scene (e.g. an unrelated economic/technical noun during a physical confrontation, or a bizarre non-sequitur), recognize it as a deceptive MTL homograph/idiom artifact and repair it so it makes natural sense inside the scene's context.
  2. Cause-and-Effect Pronouns: If pronoun cause-and-effect is inverted (e.g. a character hitting someone else "so that I could come to my senses" or bending "her own arm" while attacking an enemy), correct the pronoun logic ("so that you would come to your senses" / "bent his arm") to restore clear narrative causality.
  3. Speaker Attribution & Sentence Ownership (Dialogue Disentanglement): Korean pro-drop grammar and MTL paragraph merging frequently cause severe sentence ownership distortions in dialogue:
     - Merged Dialogue Turns: If two distinct characters' dialogue lines are merged into a single quotation block in the MTL (e.g., "Okay, there may be a white pigment that I don't know about. But as a dwarf, I've tried baking with all the white pigments I know..." where the first half is spoken by a human protagonist and the second half by a dwarf), you MUST disentangle and separate them into distinct dialogue turns with clear speaker attributions so sentence ownership is unmistakably clear.
     - Misattributed Pronouns & Subjects: If a dialogue line or inner thought attributes an identity, race, or profession to the wrong speaker due to MTL pronoun dropping (e.g., a human protagonist saying "as a dwarf I tried..." or "he replied" when the person speaking is "I"), correct the pronoun and speaker attribution ("I responded, 'Okay...' Stonehammer interjected, 'But as a dwarf, I've tried...'") to ensure every sentence belongs to its rightful speaker.
- Do NOT invent new plot events or characters. Output ONLY the repaired chapter text.
- PRESERVE ALL PARAGRAPH BREAKS EXACTLY across narrative paragraphs. Do not merge short paragraphs into blocks. You are permitted to split a merged dialogue paragraph when separating distinct speakers for sentence ownership clarity."""


def build_prompt(
    prepassed_text: str,
    prompted_policies: List[Policy],
    reference: Optional[str] = None,
    style_profile: Optional[List[str]] = None,
    previous_tail: Optional[str] = None,
    active_cast_entries: Optional[List[Dict]] = None,
) -> str:
    """Build the LLM rewrite prompt.

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
    # Scan for known MTL errors and inject corrections
    known_errors = scan_known_errors(prepassed_text)
    known_errors_block = format_known_errors_for_prompt(known_errors)

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
        known_errors_section = f"\n{known_errors_block}\n" if known_errors_block else ""
        return f"""You are POST-EDITING a machine-translated web-novel chapter toward a published human translation of the SAME passage.
{tail_block}{cast_block}
Apply the following translator policies consistently:
{instructions}
{known_errors_section}
Repair rules:
- REWRITE the MACHINE TRANSLATION (A) so it READS LIKE the PUBLISHED TRANSLATION (B): match its phrasing, voice, tone, rhythm, and emotional weight as closely as possible.
- RESOLVE DISCOURSE & NARRATIVE COHERENCE ANOMALIES (DECEPTIVE MTL ARTIFACTS):
  Machine translations frequently output grammatically valid English words that make zero logical sense inside the scene. Before preserving any sentence verbatim, verify its Discourse Coherence against the immediate scene:
  1. Conversational Logic: If a noun, exclamation, or idiom violates the conversational or emotional logic of the scene (e.g. an unrelated economic noun during a physical confrontation, or a bizarre non-sequitur), recognize it as a deceptive artifact and repair it to match (B)'s phrasing.
  2. Cause-and-Effect Pronouns: If pronoun cause-and-effect is inverted (e.g. a character hitting someone else "so that I could come to my senses"), correct the pronoun logic to restore clear narrative causality.
  3. Speaker Attribution & Sentence Ownership (Dialogue Disentanglement): Korean pro-drop grammar and MTL paragraph merging frequently cause severe sentence ownership distortions in dialogue:
     - Merged Dialogue Turns: If two distinct characters' dialogue lines are merged into a single quotation block in the MTL, disentangle and separate them into distinct dialogue turns with correct speaker attributions matching (B) so sentence ownership is unmistakably clear.
     - Misattributed Pronouns & Subjects: If a dialogue line or inner thought attributes an identity, race, or profession to the wrong speaker due to MTL pronoun dropping, correct the pronoun and speaker attribution so every sentence belongs to its rightful speaker.
- Do NOT invent events, characters, or details absent from both (A) and (B).
- Do NOT add unnecessary speaker attributions unless required to clarify ambiguous sentence ownership or disentangle merged dialogue turns.
- Do NOT summarize, condense, or skip content. Reproduce ALL scenes and beats from (A).
- Output ONLY the repaired chapter text. No headers, scaffolding, or code fences.
- PRESERVE ALL PARAGRAPH BREAKS EXACTLY across narrative paragraphs. Do not merge short paragraphs into blocks. You are permitted to split a merged dialogue paragraph when separating distinct speakers for sentence ownership clarity.

=== (A) MACHINE TRANSLATION TO REPAIR ===
{prepassed_text}

=== (B) PUBLISHED TRANSLATION (reference) ===
{reference}"""

    if style_profile:
        known_errors_section = f"\n{known_errors_block}\n" if known_errors_block else ""
        profile_txt = "\n".join(f"- {ex}" for ex in style_profile)
        return f"""You are repairing a machine-translated web-novel chapter into fluent, natural English. There is NO published translation for this chapter.
{tail_block}{cast_block}
### VOICE REFERENCE EXCERPTS (DO NOT COPY OR INSERT THESE LINES)
The following quotes are from DIFFERENT chapters by the SAME translator. Use them ONLY as stylistic inspiration for tone, rhythm, and vocabulary. DO NOT copy, insert, or weave any of these lines, characters, or dialogue into the current chapter:
{profile_txt}
### END REFERENCE EXCERPTS

Apply the following translator policies consistently:
{instructions}
{known_errors_section}
{_FALLBACK_RULES}

CHAPTER TO REWRITE:
{prepassed_text}"""

    profile_txt = "\n".join(f"- {ex}" for ex in _STYLE_REFERENCE)
    known_errors_section = f"\n{known_errors_block}\n" if known_errors_block else ""
    return f"""You are aggressively repairing a machine-translated web novel chapter into fluent, natural English.
{tail_block}{cast_block}
Apply the following translator policies consistently:
{instructions}
{known_errors_section}
### VOICE REFERENCE EXCERPTS (DO NOT COPY OR INSERT THESE LINES)
The following quotes show the translator's vocabulary, dialogue rhythm, and gritty tone. They are from DIFFERENT chapters. Use them ONLY as stylistic inspiration. DO NOT copy, insert, or weave any of these lines or characters into the current chapter:
{profile_txt}
### END REFERENCE EXCERPTS

{_FALLBACK_RULES}

CHAPTER TO REWRITE:
{prepassed_text}"""


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
    if glossary and (do_llm or reference_text is not None or style_profile is not None):
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

    # A reference or style profile only makes sense with the LLM on; force it.
    use_llm = do_llm or (reference_text is not None) or (style_profile is not None)
    # The LLM has something to do if do_llm is True, or if there's a reference / style bank.
    need_llm = do_llm or (reference_text is not None) or (style_profile is not None)
    logger.debug(f"LLM: use={use_llm}, need={need_llm}")

    # Entity shielding: replace glossary entries with placeholders before LLM,
    # restore after. This prevents the LLM from mangling entity names and makes
    # the faithfulness guard almost unnecessary for glossary entities.
    shielded_text = _normalize_newlines(prepassed_text)
    restore_map: Dict[str, str] = {}
    if glossary and use_llm and need_llm:
        shielded_text, restore_map = shield_entities(shielded_text, glossary)
        logger.debug(f"Shielded {len(restore_map)} entities")

    if reference_text:
        reference_text = _normalize_newlines(reference_text)

    # Long chapters exceed the small model's per-request token budget, so rewrite
    # in capped chunks (supervised: MTL chunk + matching reference chunk, aligned
    # by chunk index).
    mtl_chunks = _chunk_text(shielded_text)
    ref_chunks = _chunk_text(reference_text) if reference_text else []
    logger.debug(f"Split into {len(mtl_chunks)} chunks")

    rewritten_text = shielded_text
    client = None
    if use_llm and need_llm:
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
                    context_tail = previous_tail
                else:
                    context_tail = mtl_chunks[k - 1][-800:]

                # Find active cast from placeholders and known aliases/titles
                active_cast_entries = []
                if glossary:
                    active_canonicals = set()
                    if restore_map:
                        active_canonicals.update(canon for ph, canon in restore_map.items() if ph in mtl_chunk)
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

                prompt = build_prompt(
                    mtl_chunk,
                    prompted,
                    reference=ref_chunk,
                    style_profile=style_profile,
                    previous_tail=context_tail,
                    active_cast_entries=active_cast_entries,
                )
                logger.debug(f"Prompt length: {len(prompt)} chars")
                resp = _llm_complete(
                    client,
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    temperature=0.45,
                )
                out_parts.append(_strip_echo(resp.choices[0].message.content))
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
    if client is not None and reference_text is not None:
        novel = _novel_entities(rewritten_text, reference_text, whitelist=canon)
        if novel:
            logger.warning(f"Faithfulness guard: {len(novel)} novel entities detected: {novel}")
            guard_prompt = _faithfulness_prompt(rewritten_text, novel)
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
            )
            rewritten_text = _strip_echo(resp.choices[0].message.content)
            logger.info("Faithfulness guard applied")
        else:
            logger.debug("Faithfulness guard: no novel entities found")

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
    }
