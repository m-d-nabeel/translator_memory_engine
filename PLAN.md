# Translator Memory Engine — Future Work Plan

The core prototype (extracting policies, rewriting text via LLM, and the full web application interface) has been completed. The items below represent the only outstanding future features we intend to build, following a rigorous critical engineering review that rejected over-engineered abstractions (like Vector DBs and Story Graphs).

## 1. Language Memory (Manual Example Banks)

Capture translator *voice* (rhythm, phrasing, tone) rather than just names and nouns. Instead of a complex contrastive-analysis pipeline, we will allow users to manually save "great translation snippets" in the UI. These curated snippets will be injected into the LLM prompt as a static "Style Bank" to heavily steer generation style.

## 2. Modular Validators (Entity Checks)

Provide programmatic, report-only automated checks to ensure the LLM didn't hallucinate or break rules. Specifically, "Entity Consistency" validators (scanning the final output string to ensure the LLM outputted the canonical names we told it to) are cheap to build and offer massive trust/quality benefits. Auto-fixes will live in the rewriter's post-processor.
