# Translator Memory Engine

Extracts named-entity/terminology/honorific policies from good-translated + MTL web-novel text, then rewrites MTL chapters into fluent, voice-consistent output.

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Install

```bash
# Clone the repo
git clone <repo-url>
cd translator-memory-engine

# Install dependencies and create virtual environment
uv sync

# Download spaCy English model
uv run python -m spacy download en_core_web_sm
```

### Environment Variables

Create `translator_memory_engine/.env`:

```
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key  # optional, for judge
```

## Usage

All commands use `uv run` to execute within the project's virtual environment.

### Extract Policies

Extract editorial policies from a corpus of good translations:

```bash
uv run python pipeline.py extract test-dataset/feasting-lord-in-another-world \
    --verify llm \
    --output outputs
```

### Rewrite MTL Chapters

Rewrite MTL chapters using mined policies:

```bash
# Supervised mode (with original translations as reference)
uv run python pipeline.py rewrite \
    test-dataset/feasting-lord-in-another-world-input \
    --reference test-dataset/feasting-lord-in-another-world \
    --policies outputs/policies.jsonl \
    --glossary outputs/glossary.json \
    --output outputs

# Unsupervised mode (uses style bank, no originals needed)
uv run python pipeline.py rewrite \
    test-dataset/feasting-lord-in-another-world-input \
    --policies outputs/policies.jsonl \
    --glossary outputs/glossary.json \
    --output outputs

# Pre-pass only (no LLM call)
uv run python pipeline.py rewrite \
    test-dataset/feasting-lord-in-another-world-input \
    --policies outputs/policies.jsonl \
    --output outputs
```

### Evaluate Alignment

Compare generated chapters against originals:

```bash
uv run python pipeline.py align outputs \
    --original test-dataset/feasting-lord-in-another-world \
    --mtl test-dataset/feasting-lord-in-another-world-input \
    --reference test-dataset/feasting-lord-in-another-world \
    --glossary outputs/glossary.json \
    --report outputs/alignment_report.json
```

Add `--judge` to enable independent Gemini scoring (costs API calls).

### Run Style Experiment

Run the 4-condition A/B/C/D style experiment:

```bash
uv run python scripts/style_experiment.py \
    --mtl-dir test-dataset/feasting-lord-in-another-world-input \
    --original-dir test-dataset/feasting-lord-in-another-world \
    --policies outputs/policies.jsonl \
    --glossary outputs/glossary.json \
    --output-dir outputs/experiment
```

## Development

### Run Tests

```bash
uv run pytest tests/ -v
```

### Lint

```bash
uv run ruff check .
uv run ruff format .
```

## Architecture

```
Extract → Policy Miner → Retrieve → Conflict Resolver → Pre-pass → LLM Rewrite → Eval
   │                                          │              │            │
   │                                          │              │            └─ Entity Shielding
   │                                          │              └─ Deterministic substitutions
   │                                          └─ Lexical match (word-boundary)
   └─ spaCy NER + heuristics + LLM verification
```

### Key Concepts

- **Evidence → Inference → Policy**: Raw signals → aggregated patterns → editorial rules
- **Dual-path application**: Deterministic pre-pass (high-confidence) + LLM prompt (context-dependent)
- **Learn/apply/evaluate by availability**: Supervised when originals exist, unsupervised from style bank otherwise
- **Entity shielding**: Glossary entries replaced with placeholders during LLM rewrite to prevent name mangling
- **Cross-chapter context**: Previous chapter's tail passed to LLM for pronoun/scene continuity

## Data Layout

```
test-dataset/
  feasting-lord-in-another-world/          # Original translations (ch 1-39)
  feasting-lard-in-another-world-input/    # MTL chapters (ch 1-5, 039-041)
  feasting-lard-in-another-world-output/   # Generated output
```

## Project Structure

```
translator_memory_engine/
  style/              # StyleProfile, stylometry, exemplar retrieval
  rewrite/            # LLM rewrite, entity shielding, pre-pass
  retrieve/           # Policy retrieval (word-boundary matching)
  memory/             # Style bank, policy store
  eval/               # Alignment, faithfulness, judge
  extract/            # Signal extraction (NER, terminology, honorifics)
  policy/             # Policy schema, miner, verifier
  ingest/             # Corpus loading (txt, epub)
pipeline.py           # CLI entry point
scripts/              # Experiment scripts
```
