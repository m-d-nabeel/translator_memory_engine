"""Independent LLM judge (D11 eval independence).

This is a DIFFERENT model family (Gemini) from the Groq model that produces and
rewrites chapters, so it can judge without the same-model produce+judge bias
(Dietz 2025, Panickssey 2024). It is OFF by default in the align command; enable
with `--judge`. Scores faithfulness and fluency 0-5 on a sample.
"""

import json
import os
from typing import Dict

from dotenv import load_dotenv

_SYSTEM = (
    "You are an independent evaluator from a different model family than the one "
    "that produced the text. You score machine-translation repair on two axes, 0-5."
)

_PROMPT = """Score the REPAIRED text on two axes, 0-5:

- FAITHFULNESS: does it preserve every person, place, event, and beat present in the SOURCE? Penalize invented/added content and dropped content heavily.
- FLUENCY: is it natural, fluent English in a consistent translator voice?

Return ONLY a JSON object: {{"faithfulness": <int 0-5>, "fluency": <int 0-5>, "notes": "<one short sentence>"}}

=== SOURCE ===
{src}

=== REPAIRED ===
{gen}"""


def judge_chapter(
    gen: str,
    src: str,
    model: str = "gemini-2.0-flash",
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai",
    api_key_env: str = "GEMINI_API_KEY",
    temperature: float = 0.0,
) -> Dict:
    """Score one chapter with the Gemini judge. Returns a dict (or {"error": ...})."""
    load_dotenv()
    key = os.environ.get(api_key_env, "")
    if not key:
        return {"error": f"no {api_key_env}"}
    from openai import OpenAI

    client = OpenAI(api_key=key, base_url=base_url)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _PROMPT.format(src=src, gen=gen)},
            ],
            temperature=temperature,
        )
        content = resp.choices[0].message.content
        return json.loads(content)
    except Exception as e:  # pragma: no cover - network/parse dependent
        return {"error": str(e)}
