import json
import logging
from typing import Any, Dict, Optional

from translator_memory_engine.rewrite.rewriter import GroqRotatingClient, _get_groq_keys, _llm_complete

logger = logging.getLogger(__name__)


def extract_chapter_lore(
    chapter_text: str,
    model: str = "llama-3.3-70b-versatile",
    base_url: Optional[str] = None,
    api_key_env: str = "LLM_API_KEY",
) -> Dict[str, Any]:
    """
    Extracts a chapter summary and character lore from a chapter text using an LLM.

    Returns a dict with:
        "chapter_summary": str (2-3 sentences)
        "characters": List of dicts, each with:
            - "name": str (Canonical name)
            - "gender": str
            - "race_or_identity": str (1-2 sentences)
            - "speech_style": str (1-2 sentences)
            - "introduction_context": str (verbatim 1-2 sentence quote)
    """
    keys = _get_groq_keys(api_key_env) or _get_groq_keys("GROQ_API_KEY")
    if not keys:
        logger.error("No API keys found for lore extraction.")
        return {"chapter_summary": "", "characters": []}

    client = GroqRotatingClient(keys, base_url)

    # Cap text length to avoid context limits.
    # Usually the first and last few paragraphs have the most lore, but we'll take the first 4000 words.
    words = chapter_text.split()
    if len(words) > 4000:
        chapter_text = " ".join(words[:4000])

    prompt = (
        "You are an expert literary analyst and character archivist. Your task is to analyze the provided chapter text and extract structural lore.\n\n"
        "Return ONLY a valid JSON object matching the following structure:\n"
        "{\n"
        '  "chapter_summary": "A 2-3 sentence summary of the main events in this chapter.",\n'
        '  "characters": [\n'
        "    {\n"
        '      "name": "The character\'s primary name (e.g., Dominic, Stonehammer)",\n'
        '      "gender": "male, female, or unknown",\n'
        '      "race_or_identity": "1-2 short, descriptive sentences about their race, profession, or role in the story.",\n'
        '      "speech_style": "1-2 short, descriptive sentences detailing how they speak (e.g., Speaks with archaic formality, uses slang, arrogant tone).",\n'
        '      "introduction_context": "An exact verbatim 1-2 sentence quote from the chapter introducing or showing this character in action. MUST BE EXACT WORDS FROM THE TEXT, NO PARAPHRASING."\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "1. Extract EVERY named character present in the text, even if they only speak briefly.\n"
        "2. Do NOT extract abstract concepts, inanimate objects, or places as characters.\n"
        "3. Keep identity and speech_style descriptive but concise (1-2 sentences max).\n"
        "4. DO NOT wrap the JSON in Markdown code blocks (e.g., no ```json). Output raw JSON only.\n\n"
        f"=== CHAPTER TEXT ===\n{chapter_text}"
    )

    try:
        resp = _llm_complete(
            client,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a terminology mapper and lore archivist. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)
        return data

    except Exception as e:
        logger.error(f"Failed to extract chapter lore: {e}", exc_info=True)
        return {"chapter_summary": "", "characters": []}
