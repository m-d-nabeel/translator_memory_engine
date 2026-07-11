"""Rewriter (PLAN.md §6 M1, §8, §11).

Orchestrates the v0 rewrite pipeline for a single MTL passage:

    Retriever  ->  Conflict Resolver  ->  Deterministic Pre-pass  ->  (LLM Rewrite)

The deterministic pre-pass guarantees the high-confidence terminology. The
lower-confidence / context-dependent policies are assembled into an LLM prompt
as explicit instructions (Mechanism 2). A change trace records every
deterministic edit for explainability.

The LLM call reuses the OpenAI-compatible client (same backend as verification).
"""

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

# ---------------------------------------------------------------------------
# Known MTL error corrections (outputs/known_errors.json)
# ---------------------------------------------------------------------------

_KNOWN_ERRORS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "known_errors.json"
)


def _load_known_errors() -> List[Dict]:
    """Load known MTL error corrections from JSON."""
    try:
        import json

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

    matches = []
    for error in known_errors:
        phrase = error.get("mtl_phrase", "")
        if phrase and re.search(re.escape(phrase), text, re.IGNORECASE):
            matches.append(error)
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
        lines.append(f'  - "{phrase}" → "{correct}" (Korean: {korean}) — {context}')
    return "\n".join(lines)


def _load_policies(path: str) -> List[Policy]:
    store = PolicyStore()
    store.load(path)
    return store.all()


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
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"```\s*$", "", raw)
        import json

        mapping = json.loads(raw)
        # Only return valid mappings (non-null, non-identical)
        return {k: v for k, v in mapping.items() if v and k != v}
    except Exception:
        return {}


def _llm_complete(client, retries: int = 5, backoff: float = 15.0, **kwargs):
    """Call the chat completion with retry/backoff for TPM rate limits.

    The free Groq tier caps ~6000 tokens/min, and the chunked rewrite plus the
    faithfulness re-prompt can burst past it. Backing off keeps the run green
    instead of aborting mid-chapter.
    """
    last = None
    for attempt in range(retries):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            last = e
            if attempt == retries - 1:
                break
            time.sleep(backoff * (attempt + 1))
    raise last


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
- Do NOT invent new plot events or characters. Output ONLY the repaired chapter text."""


def build_prompt(
    prepassed_text: str,
    prompted_policies: List[Policy],
    reference: Optional[str] = None,
    style_profile: Optional[List[str]] = None,
    previous_tail: Optional[str] = None,
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
        render_as = p.action.get("render_as", p.trigger)
        if p.type == "honorific":
            lines.append(f'- Always render "{p.trigger}" as the honorific "{render_as}".')
        elif p.type == "terminology":
            lines.append(f'- Use the terminology "{render_as}" (not variants of "{p.trigger}").')
        else:
            lines.append(f'- Render "{p.trigger}" as "{render_as}".')
    instructions = "\n".join(lines) if lines else "  (no prompted policies)"

    tail_block = ""
    if previous_tail:
        tail_block = (
            "\n=== PREVIOUS CHAPTER TAIL (for continuity — do NOT reproduce) ===\n"
            f"{previous_tail}\n\n"
        )

    if reference:
        known_errors_section = f"\n{known_errors_block}\n" if known_errors_block else ""
        return f"""You are POST-EDITING a machine-translated web-novel chapter toward a published human translation of the SAME passage.
{tail_block}
Apply the following translator policies consistently:
{instructions}
{known_errors_section}
Repair rules:
- REWRITE the MACHINE TRANSLATION (A) so it READS LIKE the PUBLISHED TRANSLATION (B): match its phrasing, voice, tone, rhythm, and emotional weight as closely as possible.
- RESOLVE DISCOURSE & NARRATIVE COHERENCE ANOMALIES (DECEPTIVE MTL ARTIFACTS):
  Machine translations frequently output grammatically valid English words that make zero logical sense inside the scene. Before preserving any sentence verbatim, verify its Discourse Coherence against the immediate scene:
  1. Conversational Logic: If a noun, exclamation, or idiom violates the conversational or emotional logic of the scene (e.g. an unrelated economic noun during a physical confrontation, or a bizarre non-sequitur), recognize it as a deceptive artifact and repair it to match (B)'s phrasing.
  2. Cause-and-Effect Pronouns: If pronoun cause-and-effect is inverted (e.g. a character hitting someone else "so that I could come to my senses"), correct the pronoun logic to restore clear narrative causality.
- Do NOT invent events, characters, or details absent from both (A) and (B).
- Do NOT add speaker attributions ("he said") if neither (A) nor (B) has them.
- Do NOT summarize, condense, or skip content. Reproduce ALL scenes and beats from (A).
- Output ONLY the repaired chapter text. No headers, scaffolding, or code fences.

=== (A) MACHINE TRANSLATION TO REPAIR ===
{prepassed_text}

=== (B) PUBLISHED TRANSLATION (reference) ===
{reference}"""

    if style_profile:
        known_errors_section = f"\n{known_errors_block}\n" if known_errors_block else ""
        profile_txt = "\n".join(f"- {ex}" for ex in style_profile)
        return f"""You are repairing a machine-translated web-novel chapter into fluent, natural English. There is NO published translation for this chapter.
{tail_block}
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
{tail_block}
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
    policies_path: str,
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
        policies_path: Path to policies.jsonl (the mined store).
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

    policies = _load_policies(policies_path)

    # Alias bridging: use a lightweight LLM call to map MTL transliterations
    # (e.g. "Noh Young-ju") to canonical policy names (e.g. "Lord Noh").
    # This runs before the retriever so the updated match lists capture MTL forms.
    if glossary and (do_llm or reference_text is not None or style_profile is not None):
        load_dotenv()
        api_key = os.environ.get(api_key_env, "")
        if api_key:
            from openai import OpenAI

            _client = OpenAI(api_key=api_key, base_url=base_url)
            alias_map = _align_mtl_entities(text, glossary, _client, model)
            if alias_map:
                # Inject discovered aliases into policy match lists in memory
                for p in policies:
                    for mtl_form, canonical in alias_map.items():
                        if p.trigger.lower() == canonical.lower() or canonical.lower() in [
                            a.lower() for a in p.match
                        ]:
                            if mtl_form not in p.match:
                                p.match.append(mtl_form)

    retriever = PolicyRetriever(policies)
    matched = retriever.retrieve(text)

    resolution = resolve(text, matched)
    prepassed_text, trace = apply_prepass(text, resolution)

    # Prompted (non-deterministic, non-rejected) policies for the LLM
    prompted = [p for p in matched if p.applies == "prompted" and not p.llm_rejected]

    # Mode: supervised (reference) > unsupervised (style bank) > fallback.
    if reference_text is not None:
        mode = "supervised_reference"
    elif style_profile is not None:
        mode = "unsupervised_stylebank"
    else:
        mode = "fallback_faithful_repair"

    # A reference or style profile only makes sense with the LLM on; force it.
    use_llm = do_llm or (reference_text is not None) or (style_profile is not None)
    # The LLM has something to do only if there are policies to apply, or a
    # reference / style bank to steer voice against.
    need_llm = bool(prompted) or (reference_text is not None) or (style_profile is not None)

    # Entity shielding: replace glossary entries with placeholders before LLM,
    # restore after. This prevents the LLM from mangling entity names and makes
    # the faithfulness guard almost unnecessary for glossary entities.
    shielded_text = prepassed_text
    restore_map: Dict[str, str] = {}
    if glossary and use_llm and need_llm:
        shielded_text, restore_map = shield_entities(prepassed_text, glossary)

    # Long chapters exceed the small model's per-request token budget, so rewrite
    # in capped chunks (supervised: MTL chunk + matching reference chunk, aligned
    # by chunk index).
    mtl_chunks = _chunk_text(shielded_text)
    ref_chunks = _chunk_text(reference_text) if reference_text else []

    rewritten_text = shielded_text
    client = None
    if use_llm and need_llm:
        load_dotenv()
        api_key = os.environ.get(api_key_env, "")
        if api_key:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
            out_parts = []
            for k, mtl_chunk in enumerate(mtl_chunks):
                ref_chunk = ref_chunks[k] if k < len(ref_chunks) else None
                prompt = build_prompt(
                    mtl_chunk,
                    prompted,
                    reference=ref_chunk,
                    style_profile=style_profile,
                    previous_tail=previous_tail if k == 0 else None,
                )
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

    # Restore shielded entities after LLM rewrite
    if restore_map:
        rewritten_text = restore_entities(rewritten_text, restore_map)

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

    # Re-apply the deterministic pre-pass so canonical names/honorifics survive
    # even if the LLM renamed or dropped a named entity (PLAN §8: the high-confidence
    # path must not depend on LLM compliance). Runs on the LLM output and on the
    # pre-pass-only output alike.
    rewritten_text = _apply_deterministic(rewritten_text, policies)

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
