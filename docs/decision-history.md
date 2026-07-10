# Decision History — Translator Memory Engine (package: translator_memory_engine)

This document records how the project's design evolved across review rounds, so the
*why* behind each decision survives. The current, frozen design lives in `PLAN.md`.

---

## D0 — Origin: "RAG + LLM to fix MTL"

The first idea was naive: chunk a novel → embed → retrieve similar passages → ask an LLM
to rewrite MTL. Identified weakness: novels are not FAQ-style repeats; pure vector
retrieval misses *structured* consistency information (names, terms, honorifics, ranks).

**Decision:** the problem is not generation, it is *consistency / retrieval / verification*.

---

## D1 — Translation Consistency Engine

Reframed around a knowledge base built from good chapters: Glossary, Character DB, Style
Profile, World Knowledge, Translation Memory → indexes → Retriever → LLM Rewrite →
Consistency Checker.

Key sub-decisions:

- Style should be captured by **exemplars + contrastive few-shot**, not numeric statistics
  (avg sentence length etc. don't steer LLMs and can produce unnatural prose). Stats kept
  only as diagnostics.
- Retrieval should be **hybrid**: exact glossary lookup + fuzzy TM + vector for scene/context.
- Add a **world-state** layer (who's alive, relationships, ranks) — memory failures, not
  style failures, break long-form consistency.
- Build an **evaluation harness** before the engine.
- Scope discipline: MVP = glossary + TM + style exemplars + consistency checker; defer
  world graph and fancy statistics.

---

## D2 — "Translator Memory Engine" + Decisions abstraction

Renamed (see D9 for why we later resisted "Editorial Memory Engine"): the system isn't
translating, it's **reconstructing a translator's decisions**. The central object became the
**Decision**, retrieved instead of whole documents. Glossary/character DB/TM became *derived
views* over the decision store (one source of truth). Style moved to example banks. TM
reinterpreted as **stylistic patterns** (dialogue/voice/combat), retrieved by scene type.
Checkers made **modular/pluggable**. Added a **regression suite** (every bug = permanent
test). Flagged **variant clustering** as the top technical risk.

---

## D3 — Hierarchical memory, Rules, Explainability, Conflict Resolver

- Central object renamed **Rule** (trigger → action, an inference rule).
- Memory split into three types that evolve differently: **Translator Memory (Policy,
  static), Story Memory (Fact, changes), Language Memory (Pattern, slow)**.
- Added **Explainability** (every change cites rule + evidence + confidence).
- Added **Conflict Resolver** (when >1 rule matches).
- Top risk updated to **Rule applicability** (context-dependent rendering, e.g. Master vs
  Teacher vs Instructor).
- Added a real **architecture diagram**.
- Defined the **north-star success criterion**: given 30 good chapters + ch.31 MTL, can
  readers judge ch.31 as the same translator?

---

## D4 — Freeze the design

Stopped iterating architecture. Added:

- **Research hypothesis** (falsifiable): explicit rule retrieval beats document retrieval
  for consistency at lower context.
- **Evidence → Inference → Rule** layering (debuggability).
- Vocabulary note: "Rule" may evolve to "Policy".
- Validation prototype defined: extract 50–100 rules from 30 chapters, rewrite one unseen
  MTL chapter, compare vs RAG baseline.

---

## D5 — Locked setup decisions

From the setup wizard: Mixed **txt+epub**, target **English**, source **CJK** (tunes
heuristics), storage **JSON prototype → SQLite production**, extraction **Hybrid**,
goal **Balanced**, rewrite **Cloud**, corpus **30–40 to 100s**. RAG baseline defined.

---

## D6 — Deep-review corrections (before any code)

Found and fixed:

- **No application model** → added deterministic pre-pass for high-confidence
  naming/term/honorific rules; LLM only for style. (This also defuses much of the
  applicability risk.)
- **Runtime Rule lacked `match` forms** (variants/forbidden) → added `match`.
- **Missing schemas**: Character/Entity DB, Rule `type` enumeration.
- **Inconsistencies**: validation prototype needed a Retriever (added minimal retriever
  before the run); M0 "three stores" clarified (populate Translator only); hypothesis
  "less context" claim softened to a secondary context-budget metric; Conflict Resolver
  signals phased (speaker/context deferred).
- **Missing loops**: added self-correcting **feedback loop** + `refine/` (Rule Refinement)
  module (versioning, confidence updates).
- Flagged **translator style-drift** as unmodeled assumption.

---

## D7 — Latest review (this round)

- Renamed **Rule Generator → Policy Miner** (extraction is uncertain/verification-gated,
  not deterministic generation). Object renamed **Rule → Policy** throughout for coherence.
- **Hypothesis made precise**: *Explicit translator-policy retrieval produces better
  cross-chapter consistency than document-level retrieval for long-form translation
  rewriting.*
- **Policy evolution**: added `valid_from` / `valid_until` / `superseded_by` to the schema.
- **Decomposed confidence**: `frequency` / `consistency` / `context` / `verification`
  scores → `confidence`.
- **Policy Verification Backend** instead of "LLM confirms" — backend-agnostic
  (LLM / rules / human / another classifier).
- **Four-class evaluation**: Extraction / Retrieval / Generation / Reader benchmarks,
  each independent.
- **Observability**: every module emits metrics.
- Kept the storage abstraction (JSON → SQLite → Graph behind one interface) — praised.
- Build order confirmed correct: prove extraction works first.

---

## D8 — Repository restructure

Created `translator-memory-engine/` (correct system name) with package
`translator_memory_engine/{ingest, extract, memory}` and `docs/`. v0 contains **only** these three packages

- config — no retriever, rewriter, validators, or UI yet. The immediate goal: prove the
**Policy Miner** can produce a high-quality `memory/policies.jsonl` from ~30 chapters.

**Package-naming rationale (D8→D10):** the engine package is named `translator_memory_engine`,
*not* `app` (that implies a web application — this is a library/engine) and *not* a cryptic
initialism like `tme`/`novelmtl` (unsearchable, meaningless to future readers). A wrapper
package is required for **namespacing**: domain subpackages (`policy`, `memory`, `extract`,
`validate`, `eval`, …) are too generic to be safe top-level imports, so they live under
`translator_memory_engine.`. The repo previously carried the old `novelmtl` name; that was
removed because it contradicted the finalized "Translator Memory Engine" framing.

---

## Current state (frozen design, building v0)

- Architecture: frozen. Changes only from implementation discoveries / experiments.
- First deliverable: Policy Miner + JSON store → `translator_memory` (policies.jsonl).
- Gate: human review of 100+ extracted policies from a sample corpus.
- If extraction quality is good → build Retriever → Rewriter → Validators and run the
  four-class evaluation against the RAG baseline.

---

## D9 — Domain-driven repository layout

Adopted a **domain / bounded-context** layout instead of a technology layout (no `llm/`,
`rag/`, `embeddings/` top-level). Key decisions:

- **`policy/` is its own package — the heart.** It is the one bounded context every other
  package produces / stores / retrieves / consumes. `policy/schema.py` is the **single
  source of truth** for the `Policy` type; `memory/`, `retrieve/`, `validate/`, `rewrite/`
  import it and never redefine it.
- **Split `extract` from `policy`:** `extract/` produces *signals* (entity / terminology /
  honorific / formatting / style); `policy/` consumes signals and emits *policies*
  (Evidence → Signals → Policies). The Miner does not do extraction itself.
- **Validators are report-only.** Findings are returned, never text edits. Auto-fix lives in
  `rewrite/postprocessor.py` (or a dedicated fixer).
- **Retriever knows no storage:** `retrieve()` asks and gets results; storage is internal.
- **`Policy Refinement` folded into `policy/`** (`lifecycle.py`, `versioning.py`) rather than
  a separate top-level package.
- **Python-idiomatic:** avoided Go `cmd/`/`internal/`; use `pipeline.py` + `configs/`.

Critical discipline: the full tree is the **target shape** recorded in `PLAN.md` §19, but
only v0-needed packages are instantiated as code (`ingest` done, `extract`, `policy`,
`memory/storage`). Remaining packages are created when their stage is built — not scaffolded
empty up front (avoids rot and "architecture-exercise" drift).

---

## D10 — Plan refinement (dual critical review)

Two independent critical reviews (external domain reviewer + internal engineering review)
identified overlapping concerns. The plan was restructured to address all of them. Previous
version archived to `docs/PLAN-v1.md`.

Key changes:

- **Separated hypothesis-testing core from full system vision.** v0 has 5 components
  (Extractor → Policies → Retriever → Pre-pass → LLM). Everything else (Story Memory,
  Language Memory, 7 validators, pattern mining, vector retrieval, versioning) is now
  explicitly labeled future work in §15.
- **Added four-condition ablation study** (§12). Without it, the deterministic pre-pass
  could capture all gains and the hypothesis ("policy *retrieval* helps") would be
  unattributable. Conditions: (A) baseline RAG, (B) pre-pass only, (C) retrieval only,
  (D) full pipeline.
- **Simplified v0 Policy schema.** Removed `valid_from`, `valid_until`, `superseded_by` —
  YAGNI until policy evolution is actually observed. Removed `store` field (single store
  in v0).
- **Specified conflict resolution mechanism.** Replaced feature list ("confidence,
  specificity, recency") with actual algorithm: highest-confidence wins → evidence count
  tiebreak → specificity tiebreak → human review.
- **Added concrete extraction strategy** (§7). Three layers of editorial decisions (lexical,
  phrasal, stylistic) with honest assessment: v0 heuristics cover Layers 1–2 only. Layer 3
  (voice, phrasing) requires contrastive/LLM analysis beyond v0 scope.
- **Softened "static" assumption.** Translator Memory is now "assumed stable within a
  single corpus," not "effectively static."
- **Acknowledged monolingual ambiguity** (§3). Without source text, singleton occurrences
  are ambiguous. Confidence model accounts for this; ambiguous cases flagged, not
  overwritten.
- **Added evaluation resource estimates.** Gold-labeling: ~4–6 hours. Reader evaluation:
  3–5 evaluators, ~1 hour each.
- **Removed file-level implementation layout** (former §19 directory tree). Architecture
  stays conceptual; developer docs are separate.
- **Pulled glossary check into M2** (was M3). Lightweight automated validation available
  earlier.
- **Flattened three-store hierarchy for v0.** Single `PolicyStore` with `type` field.
  Three-store split deferred until Story/Language extraction exists.

Codebase alignment:

- `Policy` class moved from `models.py` to `policy/schema.py` (resolving the
  single-source-of-truth contradiction).
- Versioning fields removed from dataclass.
- `Chapter` kept in `models.py` (shared across packages).

---

## Current state (post-D10)

- Architecture: refined and scoped. v0 = 5 components + ablation study.
- Plan archived: previous version in `docs/PLAN-v1.md`.
- First deliverable: Policy Miner + JSON store → `policies.jsonl`.
- Gate: human review of 100+ extracted policies from a sample corpus.
- If extraction quality is good → build Retriever + Rewriter → run ablation → evaluate.

---

## D11 — Architecture confirmation: spaCy+LLM hybrid; GLiNER out; evaluation independence

Triggered by web research on style-preserving translation, LLM-evaluation circularity, and
spaCy+LLM hybrid pipelines, building on the earlier abandonment of the gliner-spacy backend
(environment conflict). See `PLAN.md` §13 (Evaluation independence), §15 (Language Memory
schema, GLiNER out) and the new "Data scenarios & coverage" section.

**1. GLiNER stays out (confirmed, not merely deferred).** GLiNER answers "which spans look
like entities of these labels?" — an NER-fit question. Our real question is "which recurring
editorial decisions in this corpus should be remembered and reapplied?" Those are not the same
task. An LLM can reason about terminology, aliases, honorifics, canonical forms, and
contextual significance together; GLiNER mostly yields candidate spans. spaCy + LLM already
covers this. Do not reintroduce unless later benchmarked with a measurable extraction benefit.

**2. Component positioning (Evidence → Inference → Policy preserved):**
- **spaCy:** cheap, deterministic signal generation + structural analysis (POS/dependency,
  sentence structure, boundaries, measurable style statistics).
- **LLM:** primary semantic extractor AND verifier.
- **Policy Miner:** deterministic aggregation, evidence tracking, scoring, dedup, policy
  construction.
- The LLM must NOT become the Miner; keep the deterministic layer around it. Example flow:
  spaCy emits `"Azure Dragon Palace" PROPN PROPN PROPN @ ch 2,5,9,14`; LLM emits
  `type=organization, canonical=Azure Dragon Palace, variants=[Azure Dragon Hall]`; Miner
  emits `support=12, cross-chapter=4, confidence=0.91, policy=entity-naming`.

**3. Style needs no separate extraction model yet.** The LLM is the primary style-pattern
extractor (later, for Language Memory) while spaCy supplies the measurable evidence (excerpts
+ statistics). A candidate Language Pattern is `{type, observation, evidence[], counterexamples[],
confidence}` — far more useful than a latent style vector ("similarity 0.78"). It requires
evidence AND counterexamples, not just a score.

**4. Evaluation independence is a hard constraint (LLM circularity).** Research shows same-
model produce+judge inflates results: Dietz et al. 2025 (Tropes #1 Circularity, #2 LLM-
Evaluator-as-Ranker — self-reinforcing, inflated scores); Panickssery et al. 2024 (LLMs self-
recognize — GPT-4 at 73.5% — and that drives self-preference); DBG / consensus-deviation
metrics exist to quantify and debias. Therefore:
- Extraction-LLM, rewrite-LLM, and evaluator must be **independent**.
- Evaluation stack = (a) deterministic glossary adherence [primary, always]; (b) human reader
  judgments [gold]; (c) spaCy-derived stylometry [independent, structural]; (d) optional LLM
  judge from a **different model family** than the rewriter.
- BLEU/lexical overlap alone is inadequate for literary style (DITING 2025, Border Town 2026);
  use MQM/SQM/BWS + human where possible.

**5. Style preservation is a known-hard, example-validated problem.** LLMs produce fluent-but-
generic output (SAMAS 2026). In-context example banks improve style-matching **2–4× with no
quality loss** (Steering LLMs for MT Personalization, EACL 2026) — this validates the style-
bank / example-bank approach for Language Memory and the max-fidelity reference path for
chapters that have an original.

**Implications for current work:**
- Keep M0/extraction as-is (spaCy POS + LLM verify).
- Style bank (example excerpts + spaCy stats) is the core style signal for chapters without an
  original (40+); the per-chapter original reference is a fidelity/validation bonus only.
- All evaluation avoids same-model produce+judge; no-original chapters use proxy metrics
  labeled "no gold."

---

## Current state (post-D11)

- Architecture confirmed: spaCy (deterministic signals) + LLM (extract/verify) + deterministic
  Policy Miner. GLiNER explicitly out (D11).
- Evaluation independence codified: extraction / rewrite / judge must be separate models; eval
  stack = glossary adherence + human + spaCy stylometry + optional different-family LLM judge.
- Style handled by a style bank (example excerpts + spaCy stats); Language Memory pattern schema
  is `{type, observation, evidence, counterexamples, confidence}`.
- Data-handling framed as learn / apply / evaluate across three per-chapter states; "Data
  scenarios & coverage" section added to PLAN.md (S1 actual dataset, S2 pure-separation
  hypothesis, S3 full overlap, S4 cold-start).
- Next implementation: style bank + two-mode rewrite (supervised reference / unsupervised
  style-bank) + alignment eval (tier-1 real, tier-2 proxy).
