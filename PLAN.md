# Translator Memory Engine — Future Work Plan

The core prototype (extracting policies, rewriting text via LLM, and the full web application interface) has been completed. The items below represent outstanding future features and extensions.

## 1. Story Memory (Fact extraction + world state)

Track relationships, events, deaths, locations, character statuses across chapters. Requires incremental chapter-by-chapter extraction. Enables timeline validators and relationship consistency checks.

## 2. Language Memory (Pattern extraction + example banks)

Extract stylistic patterns: dialogue voice, narration style, combat pacing, emotional scene tone. Store as example banks retrieved by scene type. Requires contrastive or LLM-based analysis.

## 3. Modular validators

Pluggable, report-only checkers: entity consistency, relationship consistency, timeline validation, style matching, dialogue honorifics, formatting. Each emits structured findings. Never edits text — auto-fixes live in the rewriter's post-processor.

## 4. Policy versioning and lifecycle

`valid_from / valid_until / superseded_by` fields on the Policy schema. Handles translator style drift (e.g. "Azure Dragon Sect" renamed to "Azure Dragon Clan" after chapter 50). Requires evidence of policy evolution.

## 5. Vector retrieval

Semantic/embedding-based retrieval for policies that don't have exact lexical triggers. Needed for stylistic policies.

## 6. Context-dependent conflict resolution

Speaker attribution, register detection, scene-type classification for resolving ambiguous policies (`Master` → Teacher vs Master). Almost a separate research project.

## 7. Pattern mining

Automated detection of recurring idioms, dialogue patterns, and narration structures for Language Memory population.

## 8. Feedback loop

Validator findings and human review feed policy refinement — low-confidence or contradicted policies are re-weighted, split, or deprecated. Makes the system self-correcting.

## 9. Low-Confidence Policy Management (UI)

For policies with low confidence, provide a UI mechanism for the user to fix or remove them. (User feature request).

## 10. Vector DB for Semantic Terminology Matching

Create a vector database containing all words from the novel (read and unread, original and MTL) to allow similarity matching for term corrections. (User feature request).
