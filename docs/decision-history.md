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
+ config — no retriever, rewriter, validators, or UI yet. The immediate goal: prove the
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
