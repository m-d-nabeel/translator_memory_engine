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

# Download spaCy English model (used for NER + stylometry)
uv run python -m spacy download en_core_web_sm
```

### Environment Variables

```bash
# Copy the example and fill in your keys
cp .env.example translator_memory_engine/.env
```

Or create `translator_memory_engine/.env` manually:

```
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key  # optional, for judge
```

## Quick Start: Translate MTL Chapter 40

Chapter 40 has no original translation (unsupervised). The engine learns voice from chapters 1-39 and applies it.

### Step 1: Extract Policies (one-time preprocessing)

Analyzes all 39 good-translation chapters and extracts editorial rules:

```bash
uv run python pipeline.py extract \
    test-dataset/feasting-lord-in-another-world \
    --verify llm \
    --output outputs
```

**Produces:**
- `outputs/policies.jsonl` — 39 editorial rules (entity naming, honorifics, terminology)
- `outputs/glossary.json` — 27 canonical name entries with surface forms

### Step 2: Rewrite Chapter 40 (all features enabled)

```bash
uv run python pipeline.py rewrite \
    test-dataset/feasting-lord-in-another-world-input/chapter-040.txt \
    --reference test-dataset/feasting-lord-in-another-world \
    --policies outputs/policies.jsonl \
    --glossary outputs/glossary.json \
    --output outputs
```

**What happens internally:**
1. **Style bank built** from 39 reference chapters (in-memory, ~78 voice excerpts)
2. **Exemplar index built** with fastembed embeddings (bge-base-en-v1.5, ~451 exemplars)
3. **Per-chapter retrieval** — top 8 excerpts selected by cosine similarity to ch040
4. **Known error correction** — scans for known MTL errors and injects corrections
5. **Entity shielding** — glossary names replaced with `__ENT_N__` placeholders before LLM
6. **Deterministic pre-pass** — high-confidence substitutions applied
7. **LLM rewrite** — repairs MTL using style bank + policies as guidance
8. **Faithfulness guard** — detects/invents characters not in source, re-prompts to strip
9. **Entity restore** — placeholders replaced with canonical names
10. **Deterministic post-pass** — ensures canonical forms survive

**Produces:**
- `outputs/rewritten_chapter-040.txt` — repaired chapter

### Step 3: Evaluate

```bash
uv run python pipeline.py align outputs \
    --mtl test-dataset/feasting-lord-in-another-world-input \
    --reference test-dataset/feasting-lord-in-another-world \
    --glossary outputs/glossary.json
```

## Full Pipeline Reference

### Preprocessing (one-time)

| Step | Command | Produces | Cost |
|------|---------|----------|------|
| Extract policies | `pipeline.py extract <corpus> --verify llm` | `policies.jsonl`, `glossary.json` | ~50 LLM calls |
| Download embeddings | (automatic on first rewrite) | `~/.cache/fastembed/` | One-time ~130MB |

The style bank and exemplar index are built in-memory from `--reference` during rewrite. No separate build step needed.

### Translation (per chapter)

| Feature | Flag | What it does |
|---------|------|-------------|
| LLM rewrite | `--reference` (forces on) or `--llm` | Calls LLM to repair MTL |
| Style bank | `--reference <dir>` | Builds voice profile from good translations |
| Entity shielding | `--glossary <file>` | Protects names during LLM rewrite |
| Cross-chapter context | process dir (not single file) | Passes previous chapter's tail for continuity |
| Faithfulness guard | (always on) | Strips invented characters post-rewrite |
| Known error correction | (automatic) | Applies corrections from `data/known_errors.json` |

### Examples

**Single chapter (unsupervised, all features):**
```bash
uv run python pipeline.py rewrite \
    test-dataset/feasting-lord-in-another-world-input/chapter-040.txt \
    --reference test-dataset/feasting-lord-in-another-world \
    --policies outputs/policies.jsonl \
    --glossary outputs/glossary.json \
    --output outputs
```

**All chapters (with cross-chapter context):**
```bash
uv run python pipeline.py rewrite \
    test-dataset/feasting-lord-in-another-world-input \
    --reference test-dataset/feasting-lord-in-another-world \
    --policies outputs/policies.jsonl \
    --glossary outputs/glossary.json \
    --output outputs
```

**Pre-pass only (no LLM, fast, deterministic edits only):**
```bash
uv run python pipeline.py rewrite \
    test-dataset/feasting-lord-in-another-world-input/chapter-040.txt \
    --policies outputs/policies.jsonl \
    --output outputs
```

### Evaluation

**Paired eval (chapters with originals):**
```bash
uv run python pipeline.py align outputs \
    --original test-dataset/feasting-lord-in-another-world \
    --mtl test-dataset/feasting-lord-in-another-world-input \
    --reference test-dataset/feasting-lord-in-another-world \
    --glossary outputs/glossary.json \
    --report outputs/alignment_report.json
```

**With Gemini judge (independent scoring):**
```bash
uv run python pipeline.py align outputs \
    --original test-dataset/feasting-lord-in-another-world \
    --mtl test-dataset/feasting-lord-in-another-world-input \
    --reference test-dataset/feasting-lord-in-another-world \
    --glossary outputs/glossary.json \
    --judge
```

## Architecture

```
Preprocessing (one-time):
  Good translations ──→ Extract ──→ policies.jsonl + glossary.json
                          │
                          └─ spaCy NER + heuristics + LLM verification

Per-chapter rewrite:
  Reference dir ──→ Style Bank (in-memory)
                 ──→ Exemplar Index (fastembed embeddings)
                 ──→ Per-chapter retrieval (cosine similarity)

  MTL chapter ──→ Known error scan ──→ Shield entities ──→ Pre-pass ──→ LLM rewrite ──→ Restore entities ──→ Post-pass
                      │                      │                              │
                      └─ known_errors.json    └─ glossary → placeholders      └─ style bank + exemplars + policies
```

### Key Concepts

- **Evidence → Inference → Policy**: Raw signals → aggregated patterns → editorial rules
- **Dual-path application**: Deterministic pre-pass (high-confidence) + LLM prompt (context-dependent)
- **Learn/apply/evaluate by availability**: Supervised when originals exist, unsupervised from style bank otherwise
- **Entity shielding**: Glossary entries replaced with placeholders during LLM rewrite to prevent name mangling
- **Cross-chapter context**: Previous chapter's tail passed to LLM for pronoun/scene continuity
- **Known error correction**: Dictionary of MTL errors mapped to Korean source + correct English translation

## Data Layout

```
data/
  originals/          # Original translations (gitignored, add your own)
  mtl/                # MTL chapters to rewrite (gitignored, add your own)
  output/             # Rewritten chapters (gitignored, auto-generated)
  policies/           # Extracted policies (gitignored, auto-generated)
  known_errors.json   # MTL error corrections (tracked in git)
```

**Note:** The data files are gitignored to keep the repository clean. The directory structure is preserved with `.gitkeep` files. To use the engine, place your data in the appropriate directories.

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
data/                 # Data directory (gitignored except known_errors.json)
  originals/          # Original translations
  mtl/                # MTL chapters to rewrite
  output/             # Rewritten chapters
  policies/           # Extracted policies
  known_errors.json   # MTL error corrections
```

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## Known Error Dictionary

The `data/known_errors.json` file maps MTL errors to their Korean source and correct English translation. When rewriting, the engine scans for these errors and injects corrections into the LLM prompt.

**Example entry:**
```json
{
  "id": "corpse-minus-stamina",
  "mtl_phrase": "corpse minus the stamina",
  "korean_source": "시체 빼고 다 OK",
  "correct_translation": "It's a piece of cake",
  "category": "literal_translation",
  "context": "reassuring that something is easy/fine"
}
```

**To add a new error:**
1. Add an entry to `data/known_errors.json`
2. The engine will automatically detect and correct it in future rewrites

**Current errors covered:**
- `corpse minus the stamina` → "It's a piece of cake"
- `Hee!` → "Heh!" (Korean squeal)
- `Profit!` → "Tch!" (teeth-gritting)
- `Growl-` → "Ugh-" (groan)
- `cried and ate mustard` → "gritting their teeth"
- `suck honey` → "flattering"
- `head case` → "idiot"
