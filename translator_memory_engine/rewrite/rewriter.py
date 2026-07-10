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
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv

from translator_memory_engine.policy import Policy
from translator_memory_engine.memory.store import PolicyStore
from translator_memory_engine.retrieve.retriever import PolicyRetriever
from translator_memory_engine.rewrite.conflict import resolve
from translator_memory_engine.rewrite.prepass import apply_prepass
from translator_memory_engine.rewrite.clean import clean_mtl_artifacts


def _load_policies(path: str) -> List[Policy]:
    store = PolicyStore()
    store.load(path)
    return store.all()


def _split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _para_ranges(paras: List[str], max_chars: int = 1800) -> List[tuple]:
    """Group paragraph indices into windows capped at ``max_chars``.

    Used so long chapters fit the small model's per-request token budget; the
    same ranges are applied to the MTL and its published reference so chunks stay
    aligned (supervised mode).
    """
    ranges: List[tuple] = []
    start = 0
    cur = 0
    for i, p in enumerate(paras):
        if cur + len(p) > max_chars and i > start:
            ranges.append((start, i))
            start = i
            cur = 0
        cur += len(p)
    ranges.append((start, len(paras)))
    return ranges


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
        out = out[idx + len(marker):].strip()
    return out.strip()


# Few-shot style anchor from the good corpus (used only as the ultimate fallback
# when neither a published reference nor a learned style bank is available).
_STYLE_REFERENCE = [
    '"Elder, are you all right?"',
    '"You\'re overthinking it, Calron. Eat."',
    "\"He's the one who appointed me, after all.\"",
    "The boy's stomach growled loud enough to shame him.",
    "She didn't smile, exactly — more a baring of teeth that passed for warmth.",
]

# The LLM task is FAITHFUL REPAIR, not free rewriting: keep the existing wording,
# only fix broken MTL, and preserve the translator's voice/metaphors/onomatopoeia.
# Never invent. (8B models love to echo the scaffolding — see _strip_echo.)
_FALLBACK_RULES = """Repair rules:
- FIX machine-translation artifacts: duplicated or truncated sentence fragments (e.g. "With my daughter, with my daughter-."), bracketed thought markers, site watermarks, filler, and awkward repetition. Repair them into natural prose — do not just delete the sentence.
- PRESERVE the translator's voice, tone, and register. Do not flatten the prose or make it generic. Keep the original paragraph structure and meaning.
- Only improve fluency and apply the policies above. Do NOT invent new events or change the story.
- Output ONLY the repaired chapter text. Do not add "Here is the repaired text", headers, or markdown code fences."""


def build_prompt(
    prepassed_text: str,
    prompted_policies: List[Policy],
    reference: Optional[str] = None,
    style_profile: Optional[List[str]] = None,
) -> str:
    """Build the LLM rewrite prompt.

    Three modes (PLAN §15, D11):
      * reference      — supervised: a published translation of the SAME chapter
                         exists; rewrite the MTL to read like it (max fidelity).
      * style_profile  — unsupervised: no original for this chapter; preserve the
                         translator's voice using learned excerpts from the bank.
      * (neither)      — fallback faithful-repair using a fixed style anchor.
    """
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

    if reference:
        return f"""You are POST-EDITING a machine-translated web-novel chapter toward a published human translation of the SAME passage.

Apply the following translator policies consistently:
{instructions}

Repair rules:
- Rewrite the MACHINE TRANSLATION (A) so it READS LIKE the PUBLISHED TRANSLATION (B): match its phrasing, voice, tone, rhythm, and emotional weight as closely as possible, while preserving (A)'s meaning.
- FIX machine-translation errors only: broken syntax, mistranslations, duplicated/truncated fragments, bracketed thought markers, and site watermarks (e.g. "Ranovel dot com"). Repair into natural prose — never just delete.
- PRESERVE (B)'s published style; do not flatten or generalize it.
- Do NOT invent events, details, or narration the source lacks.
- Output ONLY the repaired chapter text. No "Here is the repaired text", headers, or code fences.

=== (A) MACHINE TRANSLATION TO REPAIR ===
{prepassed_text}

=== (B) PUBLISHED TRANSLATION (reference) ===
{reference}"""

    if style_profile:
        profile_txt = "\n".join(f"- {ex}" for ex in style_profile)
        return f"""You are repairing a machine-translated web-novel chapter. There is NO published translation for this chapter, so preserve the translator's established voice using these excerpts from earlier chapters by the SAME translator:

{profile_txt}

Apply the following translator policies consistently:
{instructions}

{_FALLBACK_RULES}

CHAPTER TO REWRITE:
{prepassed_text}"""

    profile_txt = "\n".join(f"- {ex}" for ex in _STYLE_REFERENCE)
    return f"""You are rewriting a machine-translated web novel chapter into clean, natural English in the SAME translator's voice and tone.

Apply the following translator policies consistently:
{instructions}

Use this translator's established voice as a guide:
{profile_txt}

{_FALLBACK_RULES}

CHAPTER TO REWRITE:
{prepassed_text}"""


def rewrite(
    text: str,
    policies_path: str,
    model: str = "llama-3.1-8b-instant",
    base_url: Optional[str] = None,
    api_key_env: str = "LLM_API_KEY",
    do_llm: bool = False,
    reference_text: Optional[str] = None,
    style_profile: Optional[List[str]] = None,
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

    Returns:
        Dict with: prepassed_text, rewritten_text, trace, conflicts,
        prompted_policies (triggers), deterministic_count, prompted_count, mode.
    """
    # Clean MTL artifacts on the input only (gold corpus is untouched).
    text = clean_mtl_artifacts(text)

    policies = _load_policies(policies_path)
    retriever = PolicyRetriever(policies)
    matched = retriever.retrieve(text)

    resolution = resolve(text, matched)
    prepassed_text, trace = apply_prepass(text, resolution)

    # Prompted (non-deterministic, non-rejected) policies for the LLM
    prompted = [
        p for p in matched
        if p.applies == "prompted" and not p.llm_rejected
    ]

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

    # Long chapters exceed the small model's per-request token budget, so rewrite
    # in paragraph-aligned chunks (supervised: MTL chunk + matching original chunk).
    mtl_paras = _split_paragraphs(prepassed_text)
    ref_paras = _split_paragraphs(reference_text) if reference_text else []
    ranges = _para_ranges(mtl_paras)

    rewritten_text = prepassed_text
    if use_llm and need_llm:
        load_dotenv()
        api_key = os.environ.get(api_key_env, "")
        if api_key:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            out_parts = []
            for (s, e) in ranges:
                mtl_chunk = "\n\n".join(mtl_paras[s:e])
                ref_chunk = "\n\n".join(ref_paras[s:e]) if ref_paras else None
                prompt = build_prompt(
                    mtl_chunk, prompted,
                    reference=ref_chunk, style_profile=style_profile,
                )
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content":
                         "You are a faithful post-editor of machine-translated web novels. "
                         "You repair broken translation into natural, fluent English while "
                         "preserving the translator's established voice and never inventing "
                         "content."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                out_parts.append(_strip_echo(resp.choices[0].message.content))
            rewritten_text = "\n\n".join(out_parts)

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
