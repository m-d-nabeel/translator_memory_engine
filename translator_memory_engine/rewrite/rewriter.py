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


# Short voice reference pulled from the good-translation corpus. v0 has no
# Language Memory (PLAN §15), so this few-shot excerpt is a lightweight anchor
# that tells the LLM which translator's tone to preserve. Replace with a real
# style-bank retrieval once Language Memory lands.
_STYLE_REFERENCE = (
    "His chirping words were dripping with pride in his culinary skills and "
    "love for the people of the village.\n"
    "A village that would welcome a stranger with neither home nor temple was "
    "something that only existed in fairy tales."
)


def _load_policies(path: str) -> List[Policy]:
    store = PolicyStore()
    store.load(path)
    return store.all()


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


def build_prompt(
    prepassed_text: str,
    prompted_policies: List[Policy],
) -> str:
    """Build the LLM rewrite prompt with policy-augmented instructions."""
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

    return f"""You are REPAIRING a machine-translated web novel — not reinventing it. The existing text is already in the translator's voice; your ONLY job is to fix broken machine-translation while keeping the translator's wording, tone, rhythm, and emotional weight intact.

Apply the following translator policies consistently:
{instructions}

Repair rules (read carefully):
- KEEP the original sentences and phrasing wherever they are already grammatical. Do NOT rephrase for style or "improve" the prose.
- FIX only what is actually broken: duplicated or truncated fragments (e.g. "With my daughter, with my daughter-."), bracketed thought markers, wrong word choices, and awkward grammar. Repair into natural prose — never just delete the sentence.
- PRESERVE voice, metaphors, onomatopoeia, and emotional phrasing. Do NOT flatten the writing or make it generic.
- Do NOT invent events, details, or narration the source lacks. Do not change settings, actions, or a character's behavior.
- Match the tone of this reference passage from the SAME translator:
  "{_STYLE_REFERENCE}"

OUTPUT FORMAT: Return ONLY the repaired chapter text. Do NOT repeat these instructions, do NOT include the "CHAPTER TO REWRITE:" label, and do NOT add any meta-commentary such as "Here is the repaired text:".

CHAPTER TO REWRITE:
{prepassed_text}"""


def rewrite(
    text: str,
    policies_path: str,
    model: str = "llama-3.1-8b-instant",
    base_url: Optional[str] = None,
    api_key_env: str = "LLM_API_KEY",
    do_llm: bool = False,
) -> Dict[str, Any]:
    """Run the full v0 rewrite pipeline on one passage.

    Args:
        text: Raw MTL passage.
        policies_path: Path to policies.jsonl (the mined store).
        model / base_url / api_key_env: LLM backend for the optional rewrite.
        do_llm: If True, call the LLM to rewrite the pre-passed text.

    Returns:
        Dict with: prepassed_text, rewritten_text, trace, conflicts,
        prompted_policies (triggers), deterministic_count, prompted_count.
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

    rewritten_text = prepassed_text
    if do_llm:
        load_dotenv()
        api_key = os.environ.get(api_key_env, "")
        if api_key:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            prompt = build_prompt(prepassed_text, prompted)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content":
                     "You repair machine-translated web novels into fluent English, "
                     "faithfully preserving the translator's voice and applying the "
                     "given translator policies."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            rewritten_text = resp.choices[0].message.content
            rewritten_text = _strip_echo(rewritten_text)

    # Re-apply the deterministic pre-pass so canonical names/honorifics survive
    # even if the LLM renamed or dropped a named entity (PLAN §8: the high-confidence
    # path must not depend on LLM compliance).
    rewritten_text = _apply_deterministic(rewritten_text, policies)

    return {
        "prepassed_text": prepassed_text,
        "rewritten_text": rewritten_text,
        "trace": trace,
        "conflicts": resolution.conflicts,
        "prompted_triggers": [p.trigger for p in prompted],
        "deterministic_count": len(trace),
        "prompted_count": len(prompted),
    }
