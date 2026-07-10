# Translator Memory Engine

## 1. Positioning

Not a translation tool. **The translation already exists (the MTL).** This system
reconstructs a translator's editorial behavior and applies it to new MTL so the output
reads as if the same person wrote it.

*Translator Memory Engine* captures the right level of abstraction: specific enough that
people immediately understand "translation consistency / terminology / long-form
localization," not so narrow as "Novel MTL Fixer," and not so broad as "Editorial Memory
Engine." The underlying architecture generalizes to editorial memory (fan-fiction
voice-matching, API-documentation styling, manga/game localization) — but that broader
framing is introduced *after* the core is proven.

---

## 2. Research hypothesis (falsifiable)

> **Explicit translator-policy retrieval produces better cross-chapter consistency than
> document-level retrieval for long-form translation rewriting.**

This is the question the whole system is built to test. Every design decision must clear
this bar.

**Secondary claim** (weaker, tracked separately): policy retrieval needs less prompt
context than passage retrieval — measured via a **context-budget metric** (tokens of
retrieved material fed to the rewriter).

**North-star success criterion:**

> Given 30 high-quality chapters and chapter 31 as raw MTL, can the system produce a
> rewritten chapter that independent readers consistently judge as being translated by
> the same person who translated chapters 1–30?

**Critical confound** (see §12 Ablation): the system uses both a deterministic pre-pass
(guaranteed term substitution) and LLM-prompted policy retrieval. The ablation study must
isolate whether the gains come from structured extraction, deterministic application,
policy retrieval, or their combination. Without this, the hypothesis is untestable.

---

## 3. Hard constraint

**Only input: high-quality translated chapters (target language, e.g. English). No source
text, no source↔target alignment.**

- Everything is **monolingual** (target in → target out).
- The "glossary" is an **English→English normalization map**, recoverable from the target
  text alone.
- Future MTL chapters are also target language; consistency enforcement is purely in-target.

**Acknowledged limitation:** without source text, the system cannot distinguish between a
translator's deliberate context-specific rendering and an inconsistency. A term that appears
once as "Heavenly Mysterious Sect" and four times as "Tianxuan Sect" is *probably*
inconsistency — but it might be a deliberate contextual choice. The confidence model must
account for this: singleton occurrences receive low confidence, and the deterministic
pre-pass only applies policies above a configurable threshold. Ambiguous cases are flagged
for human review, not silently overwritten.

---

## 4. Core abstraction: Policies (not documents)

The system revolves around **Policies**, not documents. A Policy is an explicit editorial
decision:

```
IF   trigger matches        (e.g. surface form "Elder Brother")
THEN apply action           (render as "Senior Brother")
```

Retrieval fetches Policies — not whole chapters. That is the central contribution: instead
of hoping the LLM infers style from long context, editorial choices are extracted into a
structured, reusable knowledge layer and retrieved on demand.

**Three-layer derivation (Evidence → Inference → Policy)**

```
Evidence    {ch.3, "Li Qing"}, {ch.9, "Li Qing"}, ...     (raw occurrences)
   |
Inference   "translator consistently prefers 'Li Qing'"    (pattern + confidence)
   |
Policy      IF "Li Qing" THEN render "Li Qing"  [p_184]   (actionable)
```

Separating Evidence from Inference from Policy makes debugging tractable: a bad Policy can
be traced to its Inference and the Evidence that produced it.

**v0 Policy schema (minimal):**

```json
{
  "id": "p_184",
  "type": "entity-naming",
  "trigger": "Li Qing",
  "match": ["Li Qing", "Li Ching", "Li-Qing"],
  "action": {"render_as": "Li Qing"},
  "applies": "deterministic",
  "confidence": 0.99,
  "scores": {
    "frequency": 0.92,
    "consistency": 0.99,
    "context": 0.80
  },
  "evidence": [3, 9, 11, 18]
}
```

> **Schema discipline:** `type` is one of: `entity-naming`, `honorific`, `terminology`,
> `formatting`. (Style policies are a future extension — see §15.) The `match` field lists
> every known surface form (canonical + aliases + forbidden variants) the Retriever and
> pre-pass test against. Versioning fields (`valid_from`, `valid_until`, `superseded_by`)
> are omitted from v0: translator terminology is assumed stable within a single corpus (see
> §5). If policy evolution is observed in practice, versioning is added as a schema
> extension, not a redesign.

Glossary, character DB, and translation memory are **derived views** over the policy
store — one source of truth, multiple projections.

---

## 5. Memory model

### Conceptual framework: three kinds of editorial knowledge

The three kinds of information a translator encodes are fundamentally different:

**Translator Memory — Policy (stable within a corpus).**
Naming, formatting, terminology, honorific choices. `Li Qing` → `Li Qing` rarely changes
mid-series, though translators do evolve across long series (editor changes, publisher
decisions, improved understanding). The assumption of stability is a simplification, not a
fact. It is scoped to "within the provided corpus" — not "forever."

**Story Memory — Fact (changes constantly).**
Relationships, events, deaths, locations, world state. `Li Qing: Alive → Dead`.

**Language Memory — Pattern (evolves slowly).**
Recurring idioms, narration style, dialogue patterns, emotional-scene voice.

### v0 implementation: single typed store

v0 uses a **single `PolicyStore`** with a `type` discriminator. The three-memory
hierarchy is a conceptual lens, not a v0 storage architecture. Separating into three
physical stores is deferred until Story Memory and Language Memory extraction actually
exist — building three store interfaces for one populated store is premature abstraction.

The store interface is:

```
store.add(policy)
store.get(id) → Policy
store.query(trigger) → [Policy]
store.all() → [Policy]
store.export_glossary() → derived glossary view
```

Backend: JSON for prototype, SQLite for production, behind the same interface.

---

## 6. Architecture: hypothesis-testing core vs. full vision

### Hypothesis-testing core (v0 — what gets built)

```
Corpus (good chapters)
        |
   Policy Miner
   (Evidence → Inference → Policy)
        |
   Policy Store
        |
        ├─── Deterministic Pre-pass ───┐
        |    (term substitution)       |
        |                              |
   Policy Retriever                    |
   (lexical match → relevant policies) |
        |                              |
   Conflict Resolver                   |
   (highest-confidence wins)           |
        |                              |
   Prompt Builder ─────────────────────┘
        |
   LLM Rewrite
        |
   Glossary Check (lightweight)
        |
   Output + Change Trace
```

**Five components.** Everything else is future work.

### Full system vision (post-validation)

```
                 Corpus
                   |
        ┌──────────┴──────────┐
   Knowledge Extraction   Pattern Mining
        |                      |
        └──────────┬──────────┘
                   |
             Policy Miner
                   |
        ┌──────────┼──────────┐
   Translator    Story     Language
    Memory       Memory     Memory
        |          |          |
        └──────────┼──────────┘
                   |
            Retrieval Engine
                   |
           Conflict Resolver
                   |
          ┌────────┴────────┐
   Deterministic        Prompt Builder
    Pre-pass                 |
          └────────┬────────┘
                   |
              LLM Rewrite
                   |
            Explainability
                   |
          Modular Validators
                   |
             Final Output
```

The full vision includes Story Memory, Language Memory, modular validators, vector
retrieval, pattern mining, and a feedback loop. These are **future work** — they are not
required to answer the research question and should not be built until the v0 prototype
validates the core policy abstraction.

---

## 7. Extraction strategy

This is the make-or-break. If extraction fails, nothing downstream matters.

### Three layers of editorial decisions

A translator's editorial work operates at three layers. Each has different extraction
difficulty:

**Layer 1 — Lexical (deterministic extraction feasible)**

- Character names: `Li Qing` vs `Li Ching`
- Organization names: `Tianxuan Sect` vs `Heavenly Mysterious Sect`
- Place names, item names, technique names
- Source-language honorifics: `-san`, `Senior Brother`, `hyung`

**Layer 2 — Phrasal (heuristic extraction feasible)**

- Term preferences: `cultivation base` not `cultivation foundation`
- Compound terms: `Nascent Soul realm` not `Yuan Ying stage`
- Recurring phrases the translator has standardized

**Layer 3 — Stylistic (requires LLM-based or contrastive analysis)**

- Sentence structure preferences (active vs passive, clause ordering)
- Verb choices (`dashed` vs `rushed`, `cultivate` vs `practice`)
- Voice: formality, contractions in dialogue, narrator tone
- Omission of MTL artifacts (filler words, excessive demonstratives)

### v0 extraction: Layers 1–2 only

v0 targets Layers 1–2 using heuristics. This is sufficient to test the hypothesis if
lexical/phrasal consistency is a significant component of reader-perceived consistency.

**Extraction heuristics (v0):**

- Capitalized multi-word phrases → candidate entity names
- Domain-suffix mining (Sect, Palace, Hall, Peak, Clan, Court) → organization/place names
- Source-aware patterns: CJK title/honorific detection (`-san/-sama`, `Senior/Junior
  Brother/Sister`, `Dao Friend`, `hyung/noona`)
- Bracketed/italic term capture → technique/item names
- Frequency + cross-chapter consistency → confidence scoring
- Variant clustering by string normalization → canonical form + aliases

**Verification:** heuristic candidates are optionally confirmed by a verification backend
(LLM, rules, or human review). The backend is pluggable and off by default (passthrough).

### What v0 cannot extract

Layer 3 (voice, phrasing, sentence structure) is **out of scope for v0 extraction.** This
is an honest limitation, not a deferral of convenience. Heuristic pattern matching cannot
identify that a translator prefers active voice or avoids certain clause structures. Layer 3
extraction requires contrastive analysis (comparing good translation against literal MTL of
the same source) or LLM-based stylometric analysis — both of which need source text or
paired data that the monolingual constraint excludes.

If the v0 evaluation (§12) shows that Layer 1–2 policies produce significant consistency
gains but readers still perceive voice mismatch, that result *validates the policy
architecture* while identifying Layer 3 extraction as the next research frontier.

### Recommended pre-validation experiment

Before building the Policy Miner, manually annotate 2–3 chapters to catalog every
editorial difference between MTL and the good translation. Classify each as Layer 1
(lexical), Layer 2 (phrasal), or Layer 3 (stylistic). If Layers 1–2 account for >60% of
differences, the heuristic extraction strategy is well-targeted. If Layer 3 dominates, the
extraction strategy needs rethinking before building further.

---

## 8. Application model

The system applies policies through two distinct mechanisms. Their contributions must be
measured independently (see §12 Ablation).

**Mechanism 1: Deterministic pre-pass (guaranteed consistency)**

High-confidence policies (`applies: "deterministic"`, confidence ≥ threshold) are applied
as literal string substitution *before* the LLM sees the text. Every occurrence of a
`match` form is replaced with the canonical `action.render_as` value.

This is the most reliable path to terminology consistency. It does not depend on the LLM
following instructions. It handles the bulk of Layer 1 (entity names, honorifics) and some
Layer 2 (fixed terminology).

**Mechanism 2: Prompted policy retrieval (LLM-guided)**

Lower-confidence or context-dependent policies are assembled into the LLM prompt as
explicit instructions ("Always render X as Y", "Use the following terminology"). The LLM
rewrites the pre-passed text while following these instructions.

This handles Layer 2 policies that are too contextual for blind substitution and,
eventually, Layer 3 stylistic guidance.

**Why the split matters for the hypothesis:**

The deterministic pre-pass alone might capture most of the consistency gains. If so, the
contribution is "structured policy extraction + deterministic application," not "policy
retrieval." The ablation study (§12) isolates this.

---

## 9. Conflict resolution

When multiple policies match a passage (e.g. `Senior Brother` and `Elder Brother` both
triggered), the system must disambiguate before rewriting. Without this, the rewriter
receives contradictory instructions.

**v0 mechanism: highest-confidence wins**

```
1. Score each matching policy by confidence
2. Break ties by evidence count (more evidence = more reliable)
3. Break remaining ties by specificity (longer trigger = more specific)
4. If still tied, flag for human review (do not guess)
```

This is a simple, deterministic ranking. It handles the common case (one policy is clearly
better-supported) and explicitly refuses to guess on the hard case (two equally-supported
conflicting policies).

**What v0 does NOT do:** context-dependent resolution (e.g. "Master" → "Teacher" when
speaking to a student, "Master" when addressing a martial arts elder). This requires
speaker attribution and scene-type classification, which are separate research problems.
Context-dependent policies are flagged `applies: "prompted"` and passed to the LLM with
the conflicting alternatives noted — the LLM chooses, and the choice is logged for review.

---

## 10. Risks (ranked)

### Risk 1: Extraction quality (v0 gating risk)

Can heuristics extract 100+ high-quality policies from ~30 chapters?

**Mitigation:** the validation gate (§13 M0) blocks all downstream work until extraction
quality is confirmed by human review. If heuristics fail, the extraction strategy pivots
(LLM-assisted extraction, user-seeded glossaries) before building the rewriter.

### Risk 2: Policy applicability (v1 research problem)

The hardest reasoning problem: knowing *which* policy applies when the same source term is
rendered differently by context (`Master` → Teacher / Master / Instructor).

**Scoping decision:** this is explicitly out of scope for v0. v0 targets unambiguous
policies (entity names, fixed terminology) where context-dependence is rare. The
deterministic pre-pass sidesteps the problem for high-confidence policies. Ambiguous
policies are passed to the LLM with alternatives noted, not resolved deterministically.

This is almost a separate research project. It requires speaker attribution, register
detection, and relationship modeling — none of which are prerequisites for testing the core
hypothesis.

### Risk 3: Evaluation resourcing

The Reader benchmark requires human evaluators. The Extraction benchmark requires
human-labeled gold policies. Both require real effort.

**Mitigation:** §12 includes concrete resource estimates. If human evaluation is
infeasible, automated proxy metrics (glossary adherence %, embedding-based style similarity)
provide a weaker but still useful signal.

---

## 11. Explainability

Every rewrite answers *"why did you change this?"* Each edit cites the policy applied, its
confidence, and the evidence chapters.

```json
{"original": "Heavenly Mysterious Sect", "output": "Tianxuan Sect",
 "policy": "p_184", "confidence": 0.98, "evidence": [3, 11, 19]}
```

The change trace is a debugging and trust surface. It doubles as a verification aid: if a
rewrite cites no policy, either the LLM hallucinated a change (bad) or the policy was
applied via the pre-pass and correctly traced (good). A review interface showing
`changed → policy → confidence → evidence` makes human review dramatically cheaper.

v0 implementation: the change trace is emitted as a JSON sidecar alongside the rewritten
chapter. No review UI in v0 — JSON inspection is sufficient for the prototype.

---

## 12. Evaluation and ablation

### Four-condition ablation study

This is the most important evaluation component. Without it, the hypothesis is
unattributable.

| Condition | Pre-pass | Policy retrieval | Purpose |
|---|---|---|---|
| **(A) Baseline RAG** | No | No (passage retrieval) | Control: standard document-level RAG |
| **(B) Pre-pass only** | Yes | No (LLM sees pre-passed text, no policy instructions) | Isolates the deterministic substitution contribution |
| **(C) Retrieval only** | No | Yes (policies in prompt, no pre-pass) | Isolates the policy-retrieval contribution |
| **(D) Full pipeline** | Yes | Yes | The complete system |

**Possible outcomes and what they mean:**

- **D ≫ A, B ≈ A, C ≈ A:** Both mechanisms contribute, but only together. Policy retrieval
  is the contribution.
- **D ≈ B ≫ A, C ≈ A:** The deterministic pre-pass does the work. Contribution is
  "structured extraction + deterministic application," not retrieval.
- **D ≈ C ≫ A, B ≈ A:** Policy retrieval alone is sufficient. Pre-pass is redundant.
- **D ≈ B ≈ C ≫ A:** Either mechanism alone captures the gains. The contribution is
  "explicit policies" (extraction), not the application method.

Each outcome is a valid research finding. The ablation prevents the failure mode of
claiming "policy retrieval works" when actually "deterministic substitution works."

### Evaluation benchmarks (three classes)

Each layer has its own benchmark so failures localize:

**Extraction:** precision/recall of mined policies vs human-labeled gold. Duplicate rate,
low-confidence rate, coverage of named entities. *Resource estimate: 4–6 hours to manually
label gold policies for one 30-chapter corpus.*

**Retrieval:** retrieval precision/recall @k on held-out passages. How often does the
retriever surface the right policies for a given MTL passage? *Automated once gold policies
exist.*

**Generation + Reader (combined):** glossary adherence %, honorific retention %,
meaning-preservation (NLI score vs original MTL). Blinded A/B preference: "was chapter 31
translated by the same person as chapters 1–30?" *Resource estimate: 3–5 evaluators, each
reading 2–3 rewritten chapters (~1 hour per evaluator). Evaluators should be regular novel
readers, not domain experts.*

### Context-budget metric

For each condition, measure the tokens of retrieved material fed to the LLM. The secondary
claim is that policy retrieval uses less context than passage retrieval for equivalent or
better consistency.

### Regression

Every observed bug becomes a permanent test case. If the system renames "Azure Dragon Sect"
to "Azure Dragon Palace," that input/output pair is asserted to never recur.

---

## 13. Milestones — prove the hypothesis FIRST

### Pre-validation: manual annotation experiment

Before writing the Policy Miner, manually catalog editorial differences across 2–3
chapters. Classify as Layer 1/2/3 (see §7). Gate: if Layers 1–2 are <40% of differences,
reconsider the extraction strategy before building.

### M0 — Policy Miner + store (the make-or-break)

Build the extractor and populate the policy store. Emit `policies.jsonl` and a derived
`glossary.json`.

**Gate:** human review of 100+ extracted policies. Measured: precision (what fraction are
correct?), recall (what fraction of entities in the text were found?), duplicate rate.

### M1 — Retriever + Conflict Resolver + Rewriter

Minimal retriever (lexical match of `match` forms against MTL chapter). Conflict resolver
(§9). Simple rewriter: deterministic pre-pass + LLM with policy-augmented prompt. Change
trace emitted.

**Gate:** run the four-condition ablation (§12) on at least one corpus. Does the full
pipeline (D) outperform baseline RAG (A)?

### M2 — Evaluation + glossary validation

Run the full evaluation protocol. Add a lightweight glossary adherence check (automated:
does the output contain only canonical forms from the policy store?). Collect human reader
judgments.

**Evaluation independence is a hard constraint (see D11).** LLM circularity is a documented
failure mode: the same model that extracts style, rewrites using it, and evaluates will
report inflated success. Therefore the evaluation stack must keep the three roles apart:
- **Deterministic glossary adherence** — primary, always on, no LLM signal.
- **Human reader judgments** — the gold standard.
- **spaCy-derived stylometry** — independent, structural/lexical comparison (sentence
  shape, dialogue density, punctuation, type-token ratio); does not depend on the rewrite LLM.
- **Optional LLM judge** — only from a *different model family* than the rewriter; never the
  same model that produced the text.
BLEU/lexical overlap alone is inadequate for literary style (use MQM/SQM/BWS where possible).
On chapters with no original (no gold), report **proxy metrics only**, explicitly labeled
"no gold": style-consistency vs the style bank, policy/name adherence, cross-chapter
consistency.

**Gate:** statistically meaningful preference for the policy pipeline over baseline RAG. If
not, diagnose: is it extraction quality? Retrieval? LLM compliance? The layered evaluation
isolates the failure.

### Beyond M2 — see §15 (Future Work)

Do not build Story Memory, Language Memory, modular validators, pattern mining, vector
retrieval, or versioning until M2 confirms the policy abstraction works.

---

### Data scenarios & coverage (how the pipeline behaves under every data-availability case)

The system is defined by a **learn / apply / evaluate** split, not by chapter pairs. Per
chapter, the data can be in one of three states: **(orig, MTL)** both exist, **(orig only)**
no MTL to rewrite, **(MTL only)** no original to compare against. Each state maps to a role:

| Chapter state | Role | What happens |
| --- | --- | --- |
| orig + MTL | **Validate** | Supervised reference post-edit; real alignment `sim(gen, orig)` measured. Also the subset that *certifies* the method. |
| orig only | **Learn** | Nothing to rewrite (no MTL input), but feeds policy + style-bank extraction. |
| MTL only | **Apply** | Rewrite using learned policies + style bank. No gold → proxy metrics only. |

This separation is what makes the project work when the two corpora don't line up. Concrete
scenarios:

- **S1 — our actual dataset.** Originals 1–39; MTL for 1–5 and 039 (paired → validate); MTL
  for 40–41 (no original → apply). Learn from 1–39, validate on 1–5/039 (generated≈original),
  apply to 40–41 with the style bank and proxy eval. **This dataset already exercises every
  role**, so it is sufficient to demonstrate the full loop end-to-end.
- **S2 — pure separation (user hypothetical): originals 1–50, no MTL; MTL 51+, no original.**
  There is **no paired (MTL, original) data anywhere**, so the method can never be directly
  trained or scored on it. Handling: learn policies + style bank from 1–50 (no MTL needed);
  apply to 51+ with policies + style bank (no per-chapter reference possible). Evaluation has
  *no gold* → proxy metrics (style-consistency, name adherence, cross-chapter) + human review.
  **Escape hatch:** synthesize degraded MTL by MT round-tripping the originals
  (original → foreign → MT English) to create (synthetic-MTL, original) pairs, recovering a
  real alignment number even with zero real MTL.
- **S3 — full overlap (ideal):** every chapter has both. Fully supervised; maximum fidelity
  and full real-alignment evaluation. The reference path is used everywhere.
- **S4 — MTL only, zero originals (cold start):** cannot learn policies or style → the engine
  degrades to a generic MTL cleaner. Requires at least a seed corpus of good translations
  (any size) before it adds value. This is the one case the architecture cannot recover from
  on its own; it is an input requirement, not a code path.

**Key invariants the design must preserve:**
1. Learning needs originals; applying needs MTL + learned artifacts; real evaluation needs
   overlap *somewhere* — proxy metrics + the style bank cover the rest.
2. The per-chapter original is a **bonus for validation/fidelity only**; the style bank is the
   universal style signal (S2 proves it must carry chapters 51+ alone).
3. Evaluation must never let the same LLM produce *and* judge (D11).

---

## 14. Configuration (locked for v0)

| Decision | Value | Consequence |
|---|---|---|
| **Input format** | Mixed **txt + epub** | Ingestion handles both; epub via stdlib zipfile |
| **Target language** | **English** | All policies and checks are English→English |
| **Source language** | **Korean / Japanese / Chinese** (per corpus) | Heuristics tuned per source: honorific patterns, title conventions |
| **Storage** | **JSON** (prototype) → **SQLite** (production) | Behind the same store interface |
| **Extraction** | **Hybrid** (heuristics + optional verification backend) | Verification backend is pluggable: LLM / rules / human. Off by default |
| **Rewrite** | **Cloud LLM** | API key via env var |
| **Corpus size** | **30–100 chapters** | `min_support` and confidence thresholds scale with evidence |

**RAG baseline** (condition A in §12): a standard document-level retriever that embeds each
MTL passage, retrieves the k most similar good-chapter passages, and rewrites with those as
few-shot context. No explicit policy layer. This is the control.

---

## 15. Future work (post-hypothesis-validation)

Everything below is deferred until M2 confirms the policy abstraction works. Each item is a
real extension, not filler — but none are prerequisites for testing the hypothesis.

**Story Memory (Fact extraction + world state):**
Track relationships, events, deaths, locations, character statuses across chapters. Requires
incremental chapter-by-chapter extraction. Enables timeline validators and relationship
consistency checks.

**Language Memory (Pattern extraction + example banks):**
Extract stylistic patterns: dialogue voice, narration style, combat pacing, emotional scene
tone. Store as example banks retrieved by scene type. Requires contrastive or
LLM-based analysis that goes beyond v0 heuristics.

A candidate Language Pattern is a structured record, not a latent vector — far more useful
than a style-embedding "similarity 0.78" (D11):
```json
{
  "type": "dialogue-style",
  "observation": "Informal dialogue consistently uses contractions.",
  "evidence": [
    {"chapter": 3, "excerpt": "I don't think he'll come."},
    {"chapter": 8, "excerpt": "You can't leave now."}
  ],
  "counterexamples": [
    {"chapter": 11, "excerpt": "I will not tolerate this.", "context": "formal speech"}
  ],
  "confidence": 0.84
}
```
The **LLM is the primary style-pattern extractor** (it reasons over voice, tone, rhythm
together); **spaCy supplies the measurable evidence** (excerpts + statistics: sentence
length, dialogue density, punctuation patterns, type-token ratio). Patterns require evidence
*and* counterexamples, not just a score.

**Three-store split:**
When Story and Language extraction exist, split the single PolicyStore into three physical
stores with different update cadences, confidence models, and retrieval paths.

**Modular validators:**
Pluggable, report-only checkers: entity consistency, relationship consistency, timeline
validation, style matching, dialogue honorifics, formatting. Each emits structured findings.
Never edits text — auto-fixes live in the rewriter's post-processor.

**Policy versioning and lifecycle:**
`valid_from / valid_until / superseded_by` fields on the Policy schema. Handles translator
style drift (e.g. "Azure Dragon Sect" renamed to "Azure Dragon Clan" after chapter 50).
Requires evidence of policy evolution, which v0 may or may not surface.

**Vector retrieval:**
Semantic/embedding-based retrieval for policies that don't have exact lexical triggers.
Needed for Layer 3 (stylistic) policies.

**Context-dependent conflict resolution:**
Speaker attribution, register detection, scene-type classification for resolving
ambiguous policies (`Master` → Teacher vs Master). Almost a separate research project.

**Pattern mining:**
Automated detection of recurring idioms, dialogue patterns, and narration structures for
Language Memory population.

**Feedback loop:**
Validator findings and human review feed policy refinement — low-confidence or contradicted
policies are re-weighted, split, or deprecated. Makes the system self-correcting.

**Alternative NER backend (gliner-spacy):** **Out (decision D11), not merely deferred.**
GLiNER answers "which spans look like entities of these labels?" — an NER-fit question. Our
real question is "which recurring editorial decisions in this corpus should be remembered and
reapplied?" An LLM reasons over terminology, aliases, honorifics, canonical forms, and
contextual significance together; GLiNER mostly yields candidate spans. The spaCy + LLM hybrid
already covers this. Originally also blocked by a `transformers>=5.x` conflict with the pinned
`tensorflow`/embedding stack. Do **not** reintroduce unless later benchmarked against the
current pipeline with a *measurable* extraction benefit.

---

## 16. Scope discipline

The scope of the full vision (§15) is large. The feature filter remains:

> *Does this make it more likely that readers say "chapter 31 was translated by the same
> person as chapters 1–30"?*

If the answer isn't clearly yes *for the current milestone*, it belongs in future work. Do
not build ingestion robustness, world-state tracking, or evaluation infrastructure before
M0–M2 validates the policy abstraction.

---

*Previous versions of this plan are archived in `docs/PLAN-v1.md`. Decision history is
recorded in `docs/decision-history.md`.*
