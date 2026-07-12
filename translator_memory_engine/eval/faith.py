"""Faithfulness evaluation (the missing 1st pillar of the eval stack, D11).

The alignment cosine (align.py) only measures vocabulary/style overlap — it is
BLIND to meaning drift: the rewriter can invent a character (ch040 `Ian`) while
still scoring high. This module measures *grounding against the true source*:

  * unsupervised rewrite  -> source is the MTL
  * supervised rewrite    -> source is the published reference (B)

Metrics:
  person_retention : src PERSON entities that also appear in gen (None if no src persons)
  novel_persons    : PERSON entities in gen whose string is absent from the source
                     (these are the invented-speaker / invented-character signals)
  novel_org_gpe    : same for ORG/GPE/LOC
  intrusion_score  : fraction of gen sentences with NO content-token support in src
                     (catches wholly-invented passages, e.g. an Ian subplot)
  drop_score       : fraction of src sentences with no echo in gen (deletions)
  coverage         : content-token overlap gen∩src / src

Novelty is checked by STRING presence in the source (not spaCy tags alone), because
spaCy under-tags the MTL and would otherwise raise false "novel" alarms for names
that are genuinely present (e.g. `Dominic`).
"""

import re
from typing import Dict, List, Set

import spacy

_NLP = None


def _nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


_CONTENT_RE = re.compile(r"[a-z']{4,}")


def _sentences(doc) -> List[str]:
    return [s.text for s in doc.sents]


def _content_tokens(text: str) -> Set[str]:
    return set(_CONTENT_RE.findall(text.lower()))


def _entities(text: str, labels: Set[str]) -> Set[str]:
    doc = _nlp()(text)
    return {e.text for e in doc.ents if e.label_ in labels}


def _novel(entities: Set[str], source: str) -> Set[str]:
    low = source.lower()
    return {e for e in entities if e.lower() not in low}


def faithfulness_vs_source(gen: str, src: str) -> Dict[str, object]:
    """Ground `gen` against the true `src` (MTL for unsupervised, reference for supervised)."""
    gdoc = _nlp()(gen)
    sdoc = _nlp()(src)

    gen_persons = {e.text for e in gdoc.ents if e.label_ == "PERSON"}
    src_persons = {e.text for e in sdoc.ents if e.label_ == "PERSON"}
    novel_persons = _novel(gen_persons, src)
    retained = src_persons & gen_persons
    person_retention = round(len(retained) / len(src_persons), 4) if src_persons else None

    gen_org = {e.text for e in gdoc.ents if e.label_ in ("ORG", "GPE", "LOC")}
    novel_org = _novel(gen_org, src)

    src_tokens = _content_tokens(src)
    gen_tokens = _content_tokens(gen)

    gen_sents = _sentences(gdoc)
    intrusions = sum(1 for s in gen_sents if _content_tokens(s) and not (_content_tokens(s) & src_tokens))
    intrusion_score = round(intrusions / len(gen_sents), 4) if gen_sents else 0.0

    src_sents = _sentences(sdoc)
    drops = sum(1 for s in src_sents if _content_tokens(s) and not (_content_tokens(s) & gen_tokens))
    drop_score = round(drops / len(src_sents), 4) if src_sents else 0.0

    coverage = round(len(gen_tokens & src_tokens) / len(src_tokens), 4) if src_tokens else None

    return {
        "person_retention": person_retention,
        "gen_persons": len(gen_persons),
        "novel_persons": sorted(novel_persons),
        "novel_person_count": len(novel_persons),
        "novel_org_gpe": sorted(novel_org),
        "intrusion_score": intrusion_score,
        "drop_score": drop_score,
        "coverage": coverage,
    }


# Supervised mode compares against the published reference rather than the MTL.
faithfulness_vs_reference = faithfulness_vs_source
