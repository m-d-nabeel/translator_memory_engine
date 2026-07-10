# Future Small Improvements (backlog)

Accumulated small ideas and refinements that are NOT blocking the current
milestone. Captured so we don't re-litigate them while pushing the hypothesis
forward (avoid local minima). Each item is small and self-contained.

## M0 extraction (done enough — review-gated)
- [ ] **`review` subcommand** for `pipeline.py`: print rejected / `needs_review`
      policies with their LLM reasons for quick human eyeballing at the M0 gate.
- [ ] **RETYPE held behind `needs_review`**: currently RETYPE mutates `Policy.type`
      directly. Consider flagging RETYPE (keep policy, don't change type) until a
      human confirms — same safety model as DROP. KEEP/RETYPE application by LLM
      was accepted by the user; this is a stricter optional variant.
- [ ] **Send context only to low-confidence / ambiguous candidates** (DONE): the
      verification prompt already attaches `example_usage` only for `needs_review`
      policies. Keep as is.
- [ ] **Retry / exponential backoff on 429**: the verifier sleeps a fixed 1s between
      batches but does not retry on `RESOURCE_EXHAUSTED`. Add backoff so transient
      free-tier limits self-heal instead of degrading to passthrough-keep.
- [ ] **Deterministic pre-pass for the glossary check** (M2): a lightweight check
      that output contains only canonical forms — reuse the pre-pass logic.

## M1 retriever / rewriter
- [ ] **Vector / fuzzy retrieval** fallback when lexical match misses (PLAN §15).
- [ ] **Context-dependent conflict resolution** (speaker/register) — explicitly
      deferred in v0 (PLAN §9, D6).
- [ ] **Change-trace review UI** — JSON change trace is emitted; a small viewer
      would make human review cheaper (PLAN §11).

## Process
- [ ] **Regression tests for every observed bug** (PLAN §12): continue adding as
      new behaviors land (verifier verdicts, conflict resolution, pre-pass).
