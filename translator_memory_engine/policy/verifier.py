"""LLM-based policy verification.

Optional verification pass that filters heuristic/NER candidates using an LLM.
Validates whether a candidate is a true named entity, classifies its type,
and identifies false positives that pattern matching cannot catch.

The verifier is provider-agnostic: it talks to any OpenAI-compatible Chat
Completions endpoint (Groq, Gemini's OpenAI-compatible route, Together,
OpenRouter, a local Ollama server, etc.). Configure the provider via
`provider` / `base_url` / `api_key_env` in config.yaml.

Usage:
    verifier = LLMVerifier(api_key="...", model="llama-3.1-8b-instant",
                           base_url="https://api.groq.com/openai/v1")
    verified = verifier.verify_policies(policies, context_map)

Off by default (passthrough). Enabled with --verify llm or config setting.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from translator_memory_engine.policy import Policy
from translator_memory_engine.policy.miner import _normalized_edit_distance


class PassthroughVerifier:
    """Default verifier that accepts all policies unchanged."""

    def verify_policies(
        self,
        policies: List[Policy],
        context_map: Optional[Dict[str, str]] = None,
        audit_path: Optional[str] = None,
    ) -> List[Policy]:
        return policies

    def review_ambiguous(
        self,
        policies: List[Policy],
        context_map: Optional[Dict[str, str]] = None,
        audit_path: Optional[str] = None,
    ) -> List[Policy]:
        return policies


class LLMVerifier:
    """Verify policy candidates using an OpenAI-compatible LLM endpoint.

    Sends batch verification requests to classify candidates as:
    - KEEP: genuine named entity / term, policy is correct
    - DROP: false positive (common noun, sentence fragment, generic word)
    - RETYPE: entity is real but type should change

    Also enriches policies with notes from the LLM.

    Any provider exposing an OpenAI-style Chat Completions API works: pass the
    matching `base_url` and `api_key`. Examples:
      - Groq:      base_url="https://api.groq.com/openai/v1"
      - Gemini:    base_url="https://generativelanguage.googleapis.com/v1beta/openai"
      - Local Ollama: base_url="http://localhost:11434/v1"
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.1-8b-instant",
        base_url: Optional[str] = None,
        api_key_env: str = "LLM_API_KEY",
        batch_size: int = 20,
    ):
        load_dotenv()
        self.api_key = api_key or os.environ.get(api_key_env, "")
        self.model = model
        self.base_url = base_url
        self.batch_size = batch_size
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def _build_prompt(self, batch: List[Policy], context_map: Optional[Dict[str, str]] = None) -> str:
        """Build a verification prompt for a batch of policy candidates.

        When ``context_map`` provides example sentences for a trigger, they are
        included so the LLM judges the candidate from real usage, not the bare
        string (PLAN.md §7 verification / §3 monolingual ambiguity).
        """
        context_map = context_map or {}
        candidates = []
        for p in batch:
            evidence_str = f"chapters {p.evidence[:5]}" if p.evidence else "unknown"
            aliases = [f for f in p.match if f != p.trigger]
            alias_str = f", aliases: {aliases}" if aliases else ""
            ctx = context_map.get(p.trigger, "")
            # Only attach example sentences for candidates flagged for review
            # (ambiguous / low-confidence). Obvious, high-confidence entities are
            # judged from the trigger/aliases alone — sending their contexts too
            # would bloat the prompt with sentences we already mined (PLAN.md §3).
            ctx_str = (
                f'\n    example_usage: "{ctx}"'
                if (ctx and p.needs_review)
                else ""
            )
            candidates.append(
                f'  - id={p.id}, trigger="{p.trigger}", type={p.type}, '
                f'confidence={p.confidence}, found_in={evidence_str}{alias_str}{ctx_str}'
            )

        candidates_text = "\n".join(candidates)

        return f"""You are verifying named entity extraction results from a translated Korean web novel.

For each candidate below, classify it as:
- KEEP: This is a genuine character name, place name, organization, item, or consistent term that a translator would standardize.
- DROP: This is a false positive — a common English word, sentence fragment, generic noun, or role/title that is not a specific named entity.
- RETYPE: The entity is real but the type is wrong. Specify the correct type.

Valid types: entity-naming, honorific, terminology

IMPORTANT classification rules:
- DROP clear common nouns and generic terms that are NOT specific named entities. Examples to DROP: "Earth", "Rice", "Magic", "Cook", "Village", "Wizard", "Spiders", "Mrs", "Postpartum", "God", "Monster". A capitalized common noun is NOT an entity just because it is capitalized.
- DROP a BARE title used alone as if it were a name (e.g. "Count" by itself, "Lord" by itself). BUT KEEP established honorific address forms — these ARE the policy: "My Lord", "My Lady", "Sir Knight", "Senior Brother", "Young Master", etc.
- DROP sentence fragments or role/title phrases that are not a specific named entity (e.g. "Ignoring Calron", "Hearing Dominic" — these are clause starts, not names). NOTE: a fragment that contains a real name (like "Ignoring Calron") must be DROPPED as a fragment, but the inner name (Calron) is extracted as its OWN separate entity, so dropping the fragment does NOT lose the person. Never DROP a standalone proper name just because it also appears inside a fragment elsewhere.
- KEEP only genuine character names, place names, organizations, items, honorific address forms, or consistent specific terms.
- If genuinely uncertain between KEEP and DROP, KEEP (prefer false positives over missed entities), but only when the candidate could plausibly be a real named entity.

Candidates:
{candidates_text}

Respond with ONLY a JSON array. Each element must have:
- "id": the policy id
- "verdict": "KEEP" or "DROP" or "RETYPE"
- "correct_type": (only if RETYPE) the correct type
- "reason": brief explanation (1 sentence)

Example:
[
  {{"id": "p_001", "verdict": "KEEP", "reason": "Dominic is the protagonist's name"}},
  {{"id": "p_002", "verdict": "DROP", "reason": "'Chief' is a generic title, not a named entity"}},
  {{"id": "p_003", "verdict": "RETYPE", "correct_type": "honorific", "reason": "'Sir Knight' is an honorific form of address"}}
]"""

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM endpoint and return the response text."""
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict classifier of named entities in translated web novels. Respond with valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content

    def _parse_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse the JSON response from the LLM."""
        # Strip markdown code fences if present
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (code fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON array in the response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            print("  WARNING: Could not parse LLM response, keeping all policies")
            return []

    def verify_policies(
        self,
        policies: List[Policy],
        context_map: Optional[Dict[str, str]] = None,
        audit_path: Optional[str] = None,
    ) -> List[Policy]:
        """Verify a list of policies using the LLM.

        Args:
            policies: Candidate policies to verify.
            context_map: Optional mapping of policy trigger → example context
                (e.g. joined example sentences). Fed to the LLM so it judges
                candidates from real usage.
            audit_path: If given, every LLM verdict (KEEP/DROP/RETYPE, including
                dropped candidates) is appended as JSON lines to this file — a
                permanent record for the M0 review gate (PLAN.md §12).

        Returns:
            Filtered and potentially retyped policies.
        """
        if not policies:
            return policies

        if not self.api_key:
            print("  WARNING: No API key set for verifier, skipping LLM verification")
            return policies

        # Build a per-trigger context lookup from the policies' own example sentences
        # (plus any explicitly provided context_map).
        built_context: Dict[str, str] = {}
        for p in policies:
            if p.contexts:
                built_context.setdefault(p.trigger, " | ".join(p.contexts[:3]))
        if context_map:
            for k, v in context_map.items():
                built_context.setdefault(k, v)

        verified: List[Policy] = []
        verdicts: Dict[str, Dict[str, Any]] = {}
        audit_records: List[Dict[str, Any]] = []

        # Process in batches
        for i in range(0, len(policies), self.batch_size):
            batch = policies[i:i + self.batch_size]
            prompt = self._build_prompt(batch, context_map=built_context)

            try:
                response_text = self._call_llm(prompt)
                results = self._parse_response(response_text)

                id_to_trigger = {p.id: p.trigger for p in batch}
                for r in results:
                    r_id = r.get("id")
                    verdicts[r_id] = r
                    audit_records.append({
                        "id": r_id,
                        "trigger": id_to_trigger.get(r_id, ""),
                        "verdict": r.get("verdict"),
                        "correct_type": r.get("correct_type"),
                        "reason": r.get("reason", ""),
                    })

            except Exception as e:
                print(f"  WARNING: LLM verification failed for batch {i}: {e}")
                # Keep all on failure
                for p in batch:
                    verdicts[p.id] = {"id": p.id, "verdict": "KEEP",
                                      "reason": "verification failed, keeping"}

            # Rate limit: be polite to the free tier
            if i + self.batch_size < len(policies):
                time.sleep(1)

        # Write the audit log (one JSON object per line) if requested
        if audit_path and audit_records:
            with open(audit_path, "w", encoding="utf-8") as f:
                for rec in audit_records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  Verification audit written to: {audit_path}")

        # Apply verdicts
        kept = 0
        dropped = 0
        retyped = 0

        for p in policies:
            verdict = verdicts.get(p.id, {"verdict": "KEEP", "reason": "no verdict"})

            if verdict["verdict"] == "DROP":
                # Retain the policy but mark it rejected (with reason) for human
                # review, instead of silently deleting it. Excluded from the glossary.
                dropped += 1
                p.llm_rejected = True
                p.note = verdict.get("reason", "rejected by LLM verification")
                p.applies = "prompted"  # never applied by the deterministic pre-pass
            elif verdict["verdict"] == "RETYPE":
                p.type = verdict.get("correct_type", p.type)
                p.note = verdict.get("reason", "")
                retyped += 1
            else:
                if verdict.get("reason"):
                    p.note = verdict["reason"]
                kept += 1

            verified.append(p)

        print(f"  Verification: kept={kept}, dropped={dropped}, retyped={retyped}")
        return verified

    def review_ambiguous(
        self,
        policies: List[Policy],
        context_map: Optional[Dict[str, str]] = None,
        audit_path: Optional[str] = None,
    ) -> List[Policy]:
        """Refined LLM review of ambiguous (needs_review) policies.

        Unlike the first pass (which judges each candidate in isolation), this
        pass gives the LLM (a) the candidate's example sentences and (b) its
        RELATED policies, so it can resolve overlaps by deciding MERGE_INTO /
        KEEP / DROP / RETYPE on its own — no human in the loop (per the user's
        request; PLAN.md §7 / D7 LLM-assisted extraction).

        Args:
            policies: Policies after the first verification pass.
            context_map: trigger -> example sentences.
            audit_path: if given, refined decisions are appended as JSON lines.

        Returns:
            Policies list with ambiguous candidates merged / dropped / retyped.
        """
        candidates = [p for p in policies if p.needs_review and not p.llm_rejected]
        if not candidates:
            return policies
        if not self.api_key:
            print("  WARNING: No API key, skipping refined review")
            return policies

        context_map = context_map or {}
        by_id = {p.id: p for p in policies}

        related_cache: Dict[str, List[Dict[str, Any]]] = {}
        for c in candidates:
            rel = []
            for p in policies:
                if p is c:
                    continue
                if _policies_related(c, p):
                    rel.append({
                        "id": p.id, "trigger": p.trigger,
                        "type": p.type, "confidence": round(p.confidence, 3),
                    })
            related_cache[c.id] = rel

        decisions: Dict[str, Dict[str, Any]] = {}
        audit: List[Dict[str, Any]] = []
        for i in range(0, len(candidates), self.batch_size):
            batch = candidates[i:i + self.batch_size]
            prompt = self._build_review_prompt(batch, related_cache, context_map)
            try:
                resp = self._call_llm(prompt)
                results = self._parse_response(resp)
                for r in results:
                    decisions[r.get("id")] = r
                    audit.append({
                        "stage": "review", "id": r.get("id"),
                        "decision": r.get("decision"),
                        "target_id": r.get("target_id"),
                        "type": r.get("type"),
                        "reason": r.get("reason", ""),
                    })
            except Exception as e:
                print(f"  WARNING: refined review failed for batch {i}: {e}")
                for p in batch:
                    decisions[p.id] = {"id": p.id, "decision": "KEEP",
                                        "reason": "review failed, keeping"}
            if i + self.batch_size < len(candidates):
                time.sleep(1)

        # Build raw merge edges, then resolve cycles / transitive chains so a
        # mutual or chained MERGE_INTO keeps the best root policy (not deleting
        # both ends of a cycle).
        merge_of: Dict[str, str] = {}
        for c in candidates:
            d = decisions.get(c.id)
            if not d:
                continue
            if (d.get("decision") or "").upper() == "MERGE_INTO":
                tgt = d.get("target_id")
                if tgt and tgt != c.id and tgt in by_id:
                    merge_of[c.id] = tgt

        def _resolve_root(cid: str) -> str:
            seen: set = set()
            cur = cid
            while cur in merge_of and cur not in seen:
                seen.add(cur)
                nxt = merge_of[cur]
                if nxt == cur:
                    break
                if nxt in seen:
                    # Cycle: pick the root by highest confidence, then longest trigger
                    cycle = [k for k in seen
                             if merge_of.get(k) == nxt or k == nxt]
                    best = max(cycle, key=lambda k: (by_id[k].confidence,
                                                      len(by_id[k].trigger)))
                    return best
                cur = nxt
            return cur

        roots = {cid: _resolve_root(cid) for cid in merge_of}

        # Apply merges into the resolved root
        for cid, root_id in roots.items():
            c = by_id[cid]
            root = by_id[root_id]
            if root is c:
                continue  # self-root, nothing to merge away
            root.match = sorted(set(root.match) | set(c.match) | {c.trigger})
            root.evidence = sorted(set(root.evidence) | set(c.evidence))
            root.contexts = list(dict.fromkeys(root.contexts + c.contexts))
            root.note = (root.note + f"; merged '{c.trigger}' "
                         f"({decisions[cid].get('reason', '')})").strip("; ")
            c.llm_rejected = True
            c.note = f"merged into {root.id}: {decisions[cid].get('reason', '')}"
        # Roots are resolved (no longer ambiguous)
        for root_id in set(roots.values()):
            by_id[root_id].needs_review = False

        # Apply non-merge decisions for candidates not involved in a merge
        for c in candidates:
            if c.id in merge_of:
                continue
            d = decisions.get(c.id)
            if not d:
                c.needs_review = False
                continue
            dec = (d.get("decision") or "KEEP").upper()
            reason = d.get("reason", "")
            if dec == "DROP":
                c.llm_rejected = True
                c.note = reason or "rejected in refined review"
                c.applies = "prompted"
            elif dec == "RETYPE":
                c.type = d.get("type", c.type)
                c.note = reason
                c.needs_review = False
            else:  # KEEP
                c.needs_review = False
                if reason:
                    c.note = reason

        if audit_path and audit:
            with open(audit_path, "w", encoding="utf-8") as f:
                for rec in audit:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  Refined review audit written to: {audit_path}")

        # Drop only the non-root merge sources (the surviving root stays)
        merged_ids = {cid for cid, root in roots.items() if root != cid}
        return [p for p in policies if p.id not in merged_ids]

    def _build_review_prompt(
        self,
        batch: List[Policy],
        related_cache: Dict[str, List[Dict[str, Any]]],
        context_map: Optional[Dict[str, str]] = None,
    ) -> str:
        items = []
        for p in batch:
            ctx = context_map.get(p.trigger, "") if context_map else ""
            ctx_str = f'\n    example_usage: "{ctx}"' if ctx else ""
            rel = related_cache.get(p.id, [])
            rel_str = ""
            if rel:
                rel_lines = "\n".join(
                    f'      - {r["id"]} {r["trigger"]} ({r["type"]}, conf={r["confidence"]})'
                    for r in rel
                )
                rel_str = f"\n    related_policies:\n{rel_lines}"
            items.append(
                f'  - id={p.id}, trigger="{p.trigger}", type={p.type}, '
                f'confidence={p.confidence}{ctx_str}{rel_str}'
            )
        items_text = "\n".join(items)
        return f"""You are resolving AMBIGUOUS candidate policies from a translated novel. Each was flagged because it is low-confidence or overlaps another policy.

For each candidate you are given its example sentences (real usage) and its RELATED policies (others that may be the SAME entity or a different one).

Decide for each candidate:
- MERGE_INTO: <target_id>  -> the candidate is the SAME entity/person as the related policy (a spelling variant, word-order variant, or a bare surname that belongs to that name). Merge it.
- KEEP: it is a genuinely distinct entity/term; keep it separate.
- DROP: it is a false positive (common noun, sentence fragment, not a real named entity).
- RETYPE: <type> -> it is real but the type is wrong (one of: entity-naming, honorific, terminology).

Use the example sentences to judge real usage. If a candidate is just a fragment or variant of a related policy, prefer MERGE_INTO.

Candidates:
{items_text}

Respond ONLY with a JSON array, each element:
{{"id": "...", "decision": "MERGE_INTO|KEEP|DROP|RETYPE", "target_id": "<id if MERGE_INTO>", "type": "<type if RETYPE>", "reason": "..."}}"""


def _policies_related(a: Policy, b: Policy) -> bool:
    """Heuristic: are two policies plausibly the same entity (worth the LLM
    considering a merge)? True when one trigger is a token-subset of the other,
    edit distance is small, or they share a substantive token."""
    ta = {t.lower() for t in a.trigger.split()}
    tb = {t.lower() for t in b.trigger.split()}
    if ta and tb and (ta <= tb or tb <= ta):
        return True
    if _normalized_edit_distance(a.trigger, b.trigger) < 0.35:
        return True
    shared = ta & tb
    if shared and any(len(t) >= 4 for t in shared):
        return True
    return False


def create_verifier(
    backend: str = "none",
    api_key: Optional[str] = None,
    model: str = "llama-3.1-8b-instant",
    base_url: Optional[str] = None,
    api_key_env: str = "LLM_API_KEY",
    batch_size: int = 20,
) -> PassthroughVerifier | LLMVerifier:
    """Factory function for creating a verifier.

    Args:
        backend: "none" for passthrough, "llm" for LLM-based verification.
        api_key: API key. Falls back to the env var named by `api_key_env`.
        model: Model name on the provider.
        base_url: OpenAI-compatible endpoint URL for the provider.
        api_key_env: Environment variable holding the API key.
        batch_size: Policies per verification request.

    Returns:
        A verifier instance.
    """
    if backend == "llm":
        return LLMVerifier(
            api_key=api_key,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            batch_size=batch_size,
        )
    return PassthroughVerifier()
