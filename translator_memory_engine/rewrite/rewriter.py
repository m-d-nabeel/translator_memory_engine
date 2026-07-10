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

    return f"""You are rewriting a machine-translated web novel chapter into clean, natural English in the SAME translator's voice and tone.

Apply the following translator policies consistently:
{instructions}

Rewrite rules:
- FIX machine-translation artifacts: duplicated or truncated sentence fragments (e.g. "With my daughter, with my daughter-."), bracketed thought markers, filler, and awkward repetition. Repair them into natural prose — do not just delete the sentence.
- PRESERVE the translator's voice, tone, and register. Do not flatten the prose or make it generic. Keep the original paragraph structure and meaning.
- Only improve fluency and apply the policies above. Do NOT invent new events or change the story.

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
    if do_llm and prompted:
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
                     "You rewrite machine-translated web novels into fluent English, applying the given translator policies."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            rewritten_text = resp.choices[0].message.content

    return {
        "prepassed_text": prepassed_text,
        "rewritten_text": rewritten_text,
        "trace": trace,
        "conflicts": resolution.conflicts,
        "prompted_triggers": [p.trigger for p in prompted],
        "deterministic_count": len(trace),
        "prompted_count": len(prompted),
    }
