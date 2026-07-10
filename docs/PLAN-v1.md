# NovelMTL — Translator Memory Engine

## 1. Positioning

Not a translation tool. **The translation already exists (the MTL).** This system
reconstructs a translator's editorial behavior and applies it to new MTL so the output
reads as if the same person wrote it.

*Translator Memory Engine* is the right level of abstraction: specific enough that people
immediately understand "translation consistency / terminology / long-form localization,"
not so narrow as "Novel MTL Fixer," and not so broad as "Editorial Memory Engine" (which
evokes Grammarly/copy-editing). The underlying architecture **generalizes to editorial
memory** and can later serve fan-fiction voice-matching, API-documentation styling, manga
and game localization — but that broader framing is introduced *after* the core is proven.

**Naming:** the system is the **Translator Memory Engine**; `NovelMTL` is the working
code-name for this implementation (repo: `NovelMTL-Training`).

---

## 2. Research hypothesis (falsifiable)

> **Explicit translator-policy retrieval produces better cross-chapter consistency than
> document-level retrieval for long-form translation rewriting.**

This is measurable, not a slogan. It is the question the whole system is built to test,
and the bar every design decision must clear. (A secondary, weaker claim — *policy retrieval
needs less prompt context than passage retrieval* — is tracked separately via a
**context-budget metric**: tokens of retrieved material fed to the rewriter. The primary
evaluated claim is cross-chapter consistency.)

**North-star success criterion** (define everything else in service of this):

> Given 30 high-quality chapters and chapter 31 as raw MTL, can the system produce a
> rewritten chapter that independent readers consistently judge as being translated by
> the same person who translated chapters 1–30?

---

## 3. Hard constraint

**Only input: high-quality translated chapters (target language, e.g. English). No source
text, no source↔target alignment.**

- Everything is **monolingual** (target in → target out).
- The "glossary" is an **English→English normalization map**, recoverable from the target text.
- Future MTL chapters are also target language; consistency enforcement is purely in-target.

---

## 4. Core abstraction: Policies (not documents)

The system revolves around **Policies**, not documents. A Policy is an explicit inference policy:

```
IF   trigger matches        (e.g. surface form "Elder Brother")
THEN apply action           (render as "Senior Brother")
```

Retrieval fetches Policies — not whole chapters. That is the central contribution: instead of
hoping the LLM infers style from long context, editorial choices are extracted into a
structured, reusable knowledge layer and retrieved on demand.

**Three-layer derivation (Evidence → Inference → Policy)**

```
Evidence    {chapter 3, "Li Qing"}, {chapter 9, "Li Qing"}, ...   (raw occurrences)
   |
Inference   "translator consistently prefers 'Li Qing'"           (pattern + confidence)
   |
Policy        IF "Li Qing" THEN render "Li Qing"  [r_184, conf 0.99]  (actionable)
```

Separating Evidence from Inference from Policy makes debugging tractable: a bad Policy can be
traced to its Inference and the Evidence that produced it.

```json
{
  "id": "r_184",
  "type": "entity-naming",
  "store": "translator",
  "trigger": "Li Qing",
  "match": ["Li Qing", "Li Ching", "Li-Qing"],
  "action": {"render_as": "Li Qing"},
  "applies": "deterministic",
  "valid_from": 3,
  "valid_until": null,
  "superseded_by": null,
  "scores": {
    "frequency": 0.92,
    "consistency": 0.99,
    "context": 0.80,
    "verification": 0.95
  },
  "confidence": 0.99,
  "evidence": [3, 9, 11, 18]
}
```

Glossary, character DB, and TM are **derived views** over the policy store — one source of
truth, multiple indexes.

> **Vocabulary note:** the object is standardized as **Policy** (earlier drafts called it
> "Rule"); the miner that produces it is the **Policy Miner** (earlier "Rule Generator"),
> reflecting that extraction is uncertain and verification-gated rather than deterministic.
> When context-dependent applicability is implemented (e.g. `Master` → `Teacher` sometimes,
> `Master` other times), policies behave less like hard IF-THEN rules and more like
> recommendations with applicability and confidence — the abstraction (trigger/condition →
> action + evidence + confidence) stays the same. `valid_from / valid_until / superseded_by`
> let a later policy override an earlier one (policy evolution).

**Application model (resolves much of the Policy-applicability risk):** high-confidence
naming / terminology / honorific policies are applied as a **deterministic pre-pass** (guaranteed
substitution of known forms), so consistency does not depend on the LLM obeying instructions.
Lower-confidence or context-dependent policies (voice, phrasing) are supplied to the LLM as
**prompted** guidance. Validators then verify both. This splits the problem: deterministic
policies buy guaranteed terminology consistency; the LLM handles style. The `match` field lists
every known surface form (canonical + aliases + forbidden) the Retriever/Resolver/Validators
test against — not just the canonical `trigger`.

---

## 5. Hierarchical memory (three types that evolve differently)

A flat store is wrong: the three kinds of information are fundamentally different.

**Translator Memory — Policy (effectively static).**
Naming policies, formatting policies, terminology, honorific policy. `Li Qing -> Li Qing` never changes.

**Story Memory — Fact (changes constantly).**
Relationships, events, deaths, locations, world state, statuses. `Li Qing: Alive -> Dead`.

**Language Memory — Pattern (evolves slowly).**
Recurring idioms, narration style, dialogue patterns, emotional-scene voice (example banks).

Separating **Policy / Fact / Pattern** matters because they have different extractor
cadences, confidence models, and retrieval paths. Mixing them causes stale or over-eager
application of policies.

> **Assumption:** Translator Memory is treated as *effectively static* (a translator's
> naming/formatting choices rarely change mid-series). Translator *style drift* (early vs late
> volumes) is not modeled; if observed, it becomes a Story/Language Memory concern or a v2 item.

---

## 6. Architecture diagram

```
                 Corpus (good chapters, target lang)
                           |
             ┌─────────────┴─────────────┐
             |                           |
       Knowledge Extraction      Pattern Mining
       (entities, terms,         (idioms, voice,
        honorifics, story)        dialogue patterns)
             |                           |
             └─────────────┬─────────────┘
                           |
                     Policy Miner
                (Evidence -> Inference -> Policy)
                           |
        ┌──────────────────┼──────────────────┐
        |                  |                   |
   Translator Memory  Story Memory      Language Memory
      (Policy)          (Fact)            (Pattern)
        |                  |                   |
        └──────────────────┼──────────────────┘
                           |
                     Retrieval Engine
                  (policies + facts + patterns)
                           |
                   Conflict Resolver
             (confidence / specificity / recency)
                           |
                      Prompt Builder
                           |
                       LLM Rewrite
                           |
                     Explainability
                           |
                  Modular Validators
                           |
                       Final Output
```

> **Feedback loop (not shown above):** Modular Validators and human review feed *policy
> refinement* — a low-confidence or contradicted policy is re-weighted, versioned, or split.
> The architecture is thus self-correcting rather than purely linear.

---

## 7. Module breakdown

| Module | Dir | Responsibility |
|---|---|---|
| Ingest & Normalize | `ingest/` | Load good chapters; split; strip Translator Notes / page breaks |
| Signal extractors | `extract/` (`entity/`, `terminology/`, `honorific/`, `formatting/`, `style/`) | Produce *signals* (Evidence → Signals) |
| **Policy Miner** | `policy/` (`miner.py`, `verifier.py`, `scorer.py`, `lifecycle.py`, `confidence.py`, `versioning.py`, `schema.py`) | Signals → verified Policies; the heart of the system |
| Memory (3 stores) | `memory/` (`translator/`, `story/`, `language/`, `storage/`, `index/`) | Translator (Policy), Story (Fact), Language (Pattern) + storage/index |
| Retriever + Resolver | `retrieve/` (`lexical.py`, `vector.py`, `policy.py`, `resolver.py`, `orchestrator.py`) | Retrieve policies/facts/patterns; resolve conflicts |
| Rewriter | `rewrite/` (`prompt_builder.py`, `preprocessor.py`, `llm.py`, `postprocessor.py`) | Prompt assembly + pluggable LLM; emits change trace |
| Explainability | `explain/` (`change_trace.py`, `renderer.py`, `formatter.py`) | Maps each change → policy + evidence + confidence |
| Modular Validators | `validate/` (`glossary.py`, `entity.py`, `relationship.py`, `timeline.py`, `dialogue.py`, `formatting.py`, `style.py`, `report.py`) | **Report-only** checkers; never edit text |
| Eval + Regression | `eval/` (`extraction/`, `retrieval/`, `generation/`, `reader/`, `regression/`) | Four benchmark classes + regression suite |
| Orchestrator | `pipeline.py` + `configs/` | Stages, paths, model, thresholds |

> Note: `Policy Refinement` (versioning, confidence updates) is **folded into `policy/`
> (`lifecycle.py`, `versioning.py`), not a separate top-level package. The Policy schema has
> **one** source of truth: `policy/schema.py`; every other package imports it rather than
> redefining it.

**Observability (every module emits metrics):** each stage prints/structured-logs a metrics
block so the pipeline is debuggable end-to-end, e.g.

- *Policy Miner*: `extracted=142 avg_support=18.2 low_confidence=12 duplicates=4`.
- *Retriever*: `retrieved=8 unused=2 conflicting=1`.
- *Rewriter*: `applied=7 ignored=1`.
This makes regressions and extraction drift visible without reading the JSON by hand.

---

## 8. Data schema

**Policy** (central unit) — see §4. **Stores**:

- Translator Memory (Policy): naming/term/formatting/honorific policies. Glossary is a derived view:
  `{"canonical":"Tianxuan Sect","aliases":["Tian Xuan Sect","the Sect"],"forbidden":[...],"first_chapter":3,"occurrences":[3,12,18,35],"confidence":0.92}`
- Story Memory (Fact): relationships / events / statuses. World snapshot:
  `{"chapter":35,"entities":{"c_001":{"status":"active"}},"events":[...],"open_threads":[...]}`
- Language Memory (Pattern): `{"chapter":7,"text":"...","pattern":"villain_dialogue"}`

**Character / Entity DB** (derived from naming policies; referenced by Story Memory):

```json
{"id":"c_001","name":"Tianxuan Sect","type":"organization","first_appearance":3,
 "aliases":["Tian Xuan Sect","the Sect"],"relationships":[{"to":"c_002","type":"rival","since_chapter":12}],
 "status":"active","policy_ref":"r_001"}
```

**Policy `type` enumeration:** `entity-naming`, `honorific`, `terminology`, `formatting`,
`style` (style policies are `applies: prompted`). The runtime Policy carries `match` (canonical +
known variant/forbidden forms) so Retriever / Conflict Resolver / Validators detect and fix
variant spellings, not just the canonical trigger.

> `profile.yaml` `honorifics` is a *default*; per-source / per-policy honorific policies
> override it (a mixed CN/JP/KR corpus has different honorific handling per policy).

**Lean profile** (`profile.yaml`) — only mechanically enforceable facts:

```yaml
honorifics: retain          # retain | translate | drop
capitalization: title-case
paragraph_spacing: double-newline
```

> Style (tone, voice, contractions) is transferred via **example banks + contrastive
> few-shot**, NOT abstract descriptors. LLMs imitate far better than they obey
> "tone = semi-formal". Stats are kept only as **diagnostics**, never as generation constraints.

**Explainability record** (per rewrite):

```json
{"original":"Heavenly Mysterious Sect","output":"Tianxuan Sect",
 "policy":"r_184","confidence":0.98,"evidence":[3,11,19]}
```

---

## 9. Translation Memory → stylistic patterns (Language Memory)

Sentence-exact TM is weak for novels. Retrieve **stylistic patterns**: dialogue snippets,
recurring descriptions, idioms, narrator voice, combat narration, emotional scenes — stored
in Language Memory as example banks + a fuzzy/vector index, retrieved by *scene type*.

---

## 10. Top technical risk: Policy applicability

The hardest reasoning problem is no longer extraction or clustering — it is **knowing which
policy applies**. The translator may intentionally render one source term differently by
context, e.g. `Master` sometimes `Master`, sometimes `Teacher`, sometimes `Instructor`. A
Policy keyed only on the trigger is ambiguous. Applicability requires modeling context
(speaker, register, relationship, scene), which pushes the Policy abstraction from a simple
trigger→action table toward context-conditioned policies. This is the gating research risk.

(Secondary risks, in order: Policy extraction quality — is a singleton "Elder Brother" a
mistake or a real alternative policy?; variant clustering — `Azure Dragon Palace` vs `Hall`.)

> **Staging:** v0 targets *extraction quality* (can we get 100+ good policies?). Applicability
> becomes the active risk only once the Rewriter + Validators exist and can observe conflicts.
> The deterministic pre-pass in §4 already removes the easiest class of applicability errors
> (unambiguous naming/terminology), leaving context-conditioned voice/phrasing as the hard core.

---

## 11. Conflict Resolver

When multiple Policies match a passage (e.g. `Senior Brother` vs `Elder Brother`), the system
must disambiguate before rewriting. Resolution signal (phased): **v0 — confidence,
specificity, recency, evidence count**; later — **speaker, context** (requires speaker/context
attribution not yet extracted). Without this, retrieval is ambiguous and the rewriter
receives contradictory instructions. This module sits between Retriever and Prompt Builder.

---

## 12. Modular validators

Each validator is pluggable and emits a structured finding; they run in series into one
Final Report:

```
Glossary   -> canonical-form usage
Entity     -> name/alias consistency vs Translator Memory
Relationship-> relationships not contradicted (Story Memory)
Timeline   -> no dead character acting, no renamed sword, no changed realm
Style      -> matches Language Memory voice (embedding/contrastive)
Dialogue   -> honorifics + voice retained
Formatting -> italics/quotes/spacing per profile
```

Auto-fixes apply safe substitutions; everything else goes to a human-review queue.

---

## 13. Explainability (central, not optional)

Every rewrite answers *"why did you change this?"* Each edit cites the Policy applied, its
confidence, and the evidence chapters. This is a debugging and trust surface, and it doubles
as a verification aid for the validators. A review UI showing
`changed -> reason -> policy # -> confidence -> evidence` makes human review dramatically cheaper.

---

## 14. Evaluation — four independent benchmark classes

Each layer has its own benchmark so a failure localizes to one stage:

```
Extraction      How good are the mined policies?
                precision/recall of policies vs human-labeled gold;
                duplicate rate; low-confidence rate; coverage of named entities.

Retrieval       Did we retrieve the correct policies?
                retrieval precision/recall @k on held-out passages;
                conflicting-policy rate; unused-policy rate.

Generation      Did the LLM apply them?
                glossary adherence %, honorific retention %,
                meaning-preservation (NLI vs MTL), auto-fix success rate.

Reader          Did humans prefer it?
                blinded A/B: "same translator as chapters 1–30?";
                style-match score (embedding/contrastive vs good chapters).
```

- **Primary comparison**: policy-retrieval pipeline vs standard document-level RAG baseline
  (directly tests the hypothesis in §2) on the Retrieval + Generation + Reader classes.
- **Context-budget metric** (secondary hypothesis): tokens of retrieved material fed to the
  rewriter — policy pipeline should be ≤ passage-retrieval baseline.

**Regression suite**: every observed bug becomes a permanent test (e.g. renamed
"Azure Dragon Sect" → "Azure Dragon Palace" is asserted never to recur).

---

## 15. Milestones — prove the hypothesis FIRST

**Validation prototype (before full build):** extract 50–100 naming/terminology Policies from
30 chapters; retrieve the relevant Policies for one unseen MTL chapter; rewrite using only
those Policies + a baseline LLM; compare against a standard RAG-based approach on the metrics
above. If policy retrieval shows a measurable consistency gain, the central idea is validated.

Then expand:

- **M0 — Policy Miner + store structure.** Build the three-store schema and populate the
  Translator (Policy) store with extracted policies; Story/Language stores created empty.
  *Gate: human review of 100+ extracted policies.*
- **M1 — Retriever + Conflict Resolver.** Right Policies, disambiguated. *Gate: retrieval precision.*
- **M2 — Simple Rewriter + Explainability.** Applying Policies improves consistency? *Gate: human read vs baseline.*
- **M3 — Modular validators + auto-fix.** Policies verified? *Gate: adherence % on M2 output.*
- **M4 — Ingestion robustness + corpus scale + derived views.**
- **M5 — Story Memory depth (world state) + Language Memory patterns.**
- **M6 — Vector/stylistic retrieval + regression suite end-to-end.**

---

## 16. Scope discipline

The scope is dangerously large. **Feature filter:** for every proposed addition (another
checker, memory, retriever, index) ask one question — *Does this make it more likely that
readers say "chapter 31 was translated by the same person as chapters 1–30"?* If the answer
isn't clearly yes, it belongs in v2. Do not build ingestion/world-state/eval infra before
the M0–M3 prototype validates the policy abstraction.

---

## 17. Configuration (locked)

Decisions captured from setup; these drive the v0 implementation and are recorded in
`config.yaml`.

| Decision | Value | Consequence |
|---|---|---|
| **Input format** | Mixed **txt + epub** | Ingestion must handle both; epub parsed from zipped xhtml via stdlib. |
| **Target language** | **English** | All stores, policies, and checks are English↔English. |
| **Source language** | **Korean / Japanese / Chinese** (per corpus) | Heuristics are tuned per source: `-san/-sama` (JP), `Senior Brother/Junior Sister/Dao` (CN), `hyung/ahjussi` (KR). A corpus may mix; the extractor applies all source-aware patterns. |
| **Storage** | **JSON** for prototype → **SQLite** for production (graph deferred) | v0 persists Policies as JSON; switch backend behind the same store interface later. |
| **Extraction** | **Hybrid** (heuristics find candidates + Policy Verification Backend) | Heuristics are deterministic/explainable; the verification backend (LLM / rules / human review / another classifier) confirms candidates. Backend-agnostic by design — not tied to today's models. Off (passthrough) until a backend is configured. |
| **Goal** | **Balanced** (consistency / readability / fidelity) | Rewriter aggressiveness tuned to a balanced trade-off. |
| **Rewrite location** | **Cloud** | Rewriter uses a cloud LLM; API key via env var. |
| **Corpus size** | **30–40 up to 100s** | `min_support` and confidence thresholds scale with available evidence. |

**RAG baseline** (for the §14/§15 comparison): a standard document-level retriever that, for
each MTL passage, embeds it, retrieves the k most similar good-chapter passages, and rewrites
with those as few-shot context — no explicit Policy layer. This is the control the hypothesis is
tested against.

---

## 18. v0 build order (implementation)

1. **Scaffold** — `config.yaml`, package layout, JSON store.
2. **Ingest** — txt + epub loaders → normalized `Chapter` objects (chapter split, note stripping).
3. **Policy Miner** — the make-or-break: can it extract 100+ high-quality Policies from ~30
   chapters? Heuristics: capitalized-phrase + domain-suffix mining, bracketed/italic term
   capture, source-aware honorific/title detection, variant clustering by normalization,
   confidence from support + cluster tightness, optional Policy Verification Backend hook.
4. **Memory store** — write Policies as JSON (with `match` forms); emit `glossary.json` derived view.
5. **Minimal Retriever** — lexical match of policy `match` forms against an MTL chapter to select
   the relevant policies (enough to run the validation prototype end-to-end).
6. **Validation run** — extract from a sample corpus; retrieve policies for one unseen MTL chapter;
   report policy count, retrieval precision, and a sample rewrite. *Gate: extraction + retrieval
   quality confirmed before building the full Rewriter/Validators.*

Only after step 6 confirms extraction + retrieval quality do we proceed to the full
Rewriter, Validators, and refinements.

---

## 19. Repository layout (domain-driven, not technology-driven)

**Principle:** top-level packages map to *architecture concepts* (bounded contexts), never
to technologies (`llm/`, `rag/`, `embeddings/`, `database/`). The LLM is an implementation
detail of `rewrite/llm.py`, not an architecture pillar. The **`policy/`** package is the
heart — every other package produces, stores, retrieves, or consumes policies.

**Target layout** (Python-idiomatic; `cmd/`/`internal/` Go conventions avoided — use a
`pipeline.py` entrypoint and `configs/`):

```
translator-memory-engine/        # repo root
├── pipeline.py              # orchestrator / CLI entrypoint
├── configs/
│   └── default.yaml
├── translator_memory_engine/   # the engine package (importable name; namespaces domain subpackages)
│   ├── ingest/              # signal source: normalized Chapter objects
│   │   └── loader.py
│   ├── extract/             # Evidence -> Signals (NOT policies yet)
│   │   ├── entity/
│   │   ├── terminology/
│   │   ├── honorific/
│   │   ├── formatting/
│   │   └── style/
│   ├── policy/              # THE HEART: Signals -> Policies
│   │   ├── schema.py        # single source of truth for the Policy type
│   │   ├── miner.py         # assemble signals into candidate policies
│   │   ├── verifier.py      # Policy Verification Backend (llm/rules/human)
│   │   ├── scorer.py        # decomposed confidence scores
│   │   ├── lifecycle.py     # versioning + confidence updates (refinement)
│   │   ├── confidence.py
│   │   └── versioning.py    # valid_from / valid_until / superseded_by
│   ├── memory/              # storage of the three memories
│   │   ├── translator/      # glossary.py, policies.py, entities.py
│   │   ├── story/           # events.py, world_state.py, timeline.py
│   │   ├── language/        # examples.py, patterns.py
│   │   ├── storage/         # JSON (prototype) -> SQLite (prod) -> graph
│   │   └── index/
│   ├── retrieve/            # retrieve() asks, gets results; knows no storage
│   │   ├── lexical.py
│   │   ├── vector.py
│   │   ├── policy.py
│   │   ├── resolver.py      # Conflict Resolver
│   │   └── orchestrator.py
│   ├── rewrite/             # tiny: prompt_builder != llm
│   │   ├── prompt_builder.py
│   │   ├── preprocessor.py  # deterministic pre-pass (term substitution)
│   │   ├── llm.py
│   │   └── postprocessor.py  # auto-fix application (separate from validators)
│   ├── validate/            # REPORT-ONLY; never edits text
│   │   ├── glossary.py
│   │   ├── entity.py
│   │   ├── relationship.py
│   │   ├── timeline.py
│   │   ├── dialogue.py
│   │   ├── formatting.py
│   │   ├── style.py
│   │   └── report.py
│   ├── explain/
│   │   ├── change_trace.py
│   │   ├── renderer.py
│   │   └── formatter.py
│   └── eval/
│       ├── extraction/
│       ├── retrieval/
│       ├── generation/
│       ├── reader/
│       └── regression/
├── datasets/                # raw + sample corpora
├── outputs/                 # generated policies.jsonl, rewritten chapters, reports
├── docs/                    # PLAN.md, decision-history.md
└── tests/
```

**Rules enforced by this layout:**

- `policy/schema.py` is the **only** definition of the `Policy` type. `memory/`, `retrieve/`,
  `validate/`, `rewrite/` import it; they never redefine it.
- `validate/` checkers return *findings* only. Text edits / auto-fixes happen in
  `rewrite/postprocessor.py` (or a dedicated fixer), never inside a validator.
- `retrieve/` depends on `policy` (to read `match` forms) and on `memory` (via `retrieve()`),
  not on storage internals.
- `extract/` produces **signals**; `policy/` consumes signals and emits **policies**. The
  Miner does not itself do entity/terminology extraction.

**Build status (v0):** only the packages needed to clear the extraction gate exist as code:
`ingest/` (done), `extract/` (signals), `policy/` (miner + schema), `memory/` (storage).
The remaining packages above are the *target* shape, created only when their stage is built.
This avoids scaffolding 30 empty directories that then rot.
