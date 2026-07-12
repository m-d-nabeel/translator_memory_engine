# Translator Memory Engine

[![CI](https://github.com/m-d-nabeel/translator_memory_engine/actions/workflows/ci.yml/badge.svg)](https://github.com/m-d-nabeel/translator_memory_engine/actions/workflows/ci.yml)

Extracts named-entity/terminology/honorific policies from good-translated + MTL web-novel text, then rewrites MTL chapters into fluent, voice-consistent output. Includes a full web application for reading, reprocessing, and managing editorial policies.

## Quick Start

### 1. Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js](https://nodejs.org/) & [pnpm](https://pnpm.io/) (for frontend)

### 2. Backend Setup

```bash
# Install dependencies
uv sync

# Download spaCy English model (used for NER + stylometry)
uv run python -m spacy download en_core_web_sm

# Configure environment variables
cp .env.example .env
# Edit .env and add your LLM API keys (e.g. GROQ_API_KEY)
```

### 3. Frontend Setup

```bash
cd web/frontend
pnpm install
```

### 4. Running the App

Start both the backend and frontend development servers:

```bash
# In one terminal (Backend):
uv run uvicorn web.backend.app:app --reload --port 8000

# In another terminal (Frontend):
cd web/frontend
pnpm run dev
```

Visit `http://localhost:5173` to access the Translator Memory Engine Dashboard.

## Features

- **Decoupled Architecture:** Core python engine exposed via FastAPI, with a React/Vite frontend.
- **Smart Terminology:** Automatically extracts character names, techniques, and sects to apply consistent corrections.
- **Stateful Lore & Arc Engine:** Tracks character personality, identity, speech style, and verbatim introduction quotes with gated human-in-the-loop review (`[New Character]` vs `[Character Arc Shift]`).
- **Hybrid Deduplication:** Semantic blocking and exact quote auditability to easily merge duplicate character cards and aliases.
- **In-Browser Reader:** A fully-featured reader with Dark Mode, Sepia, dynamic fonts, and real-time streaming AI rewrites.
- **Engine Inspector:** View exact rate limits, LLM requests, and processing times in the UI.

## End-to-End Workflow (Step 0 to Reading & Lore Mastery)

Follow this concise, step-by-step lifecycle to translate novels with high consistency and autonomous character growth tracking:

### Step 0: Novel Creation & Chapter Import

1. **Create Novel:** Click **"+ Add Novel"** on the Dashboard and enter the title/author.
2. **Upload Chapters:** In the Novel View, click **"Upload Chapters"**. Upload reference human translations as **Original Translation (OG TL)** and raw machine-translated text as **Machine Translation (MTL)**.
   - *Tip:* Uploading 3–5 early chapters as `OG TL` first gives the engine the best baseline for names and tone.

### Step 1: Baseline Policy & Lore Extraction

1. **Mine Terminology Policies:** Go to the **Policies Tab** and click **"Mine Policies"**. The engine extracts proper nouns (characters, sects, techniques, honorifics) into deterministic translation rules (`Original -> Refined -> MTL`).
2. **Extract Character Lore & Profiles:** Go to the **Lore & Glossary Tab** and click **"Extract Lore"** (scanning `OG TL` chapters by default).
   - *Background Learning:* The engine uses structured LLM JSON extraction to build profiles (`Gender`, `Identity & Role`, `Speech Style`) along with **Verbatim Introduction Quotes (`introduction_context`)** from the text for side-by-side auditability.

### Step 2: Hybrid Deduplication & Profile Verification

Before rewriting chapters, clean and lock your knowledge base:

1. **Detect & Merge Duplicates:** Click **"Detect Duplicates 🔍"** in the **Lore Tab**. The engine uses semantic blocking (substring containment, token intersection, and Levenshtein similarity while protecting single-token proper subsets) to group duplicate variations. Review side-by-side introduction quotes and click **"Merge into Canonical"**.
2. **Manual Alias Linking:** Click the link icon (`🔗`) on any character card to select and absorb other alias cards into that canonical profile.
3. **Verify Baseline Profiles:** Click **"Verify & Lock Profile"** on new yellow `[New Character]` cards to lock their starting identity.

### Step 3: AI Translation & Chapter Rewriting

1. **Trigger Rewrite:** Go to any `MTL` chapter in the **Chapters Tab** or **Reader View** and click **"Rewrite Chapter"**.
2. **Execution Pipeline:** The engine runs a multi-stage translation pipeline:
   - **Deterministic Enforcement:** Pre-applies locked terminology policies so names never drift.
   - **Stylometric Alignment:** Matches sentence rhythm and dialogue voice against verified character profiles (`Speech Style`).
   - **High-Quality Rewrite:** Streams fluent, voice-consistent prose directly into your reader.

### Step 4: Autonomous Arc Tracking & Continuous Learning

1. **Zero-Friction Reading:** Read your chapters smoothly in the **In-Browser Reader**.
2. **Background Arc Shifts:** Every time a chapter rewrite finishes, the engine asynchronously extracts updated character lore in the background without interrupting your reading.
3. **Gated Growth Review:** If a verified character undergoes a personality change or major plot development, the engine flags a blue **`[Character Arc Shift]`** card in the **Lore Tab**. Review the exact proposed changes (e.g., `Identity: Timid Apprentice -> Sect Master`) and click **"Accept Growth"** or **"Reject"** to evolve your database.

## Data & Logs

- `data/translator_memory.db` — Your SQLite database (created automatically).
- `logs/app.log` — Backend service and API logs (rotating file handler).
