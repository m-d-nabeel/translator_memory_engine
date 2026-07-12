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
- **In-Browser Reader:** A fully-featured reader with Dark Mode, Sepia, dynamic fonts, and real-time streaming AI rewrites.
- **Engine Inspector:** View exact rate limits, LLM requests, and processing times in the UI.

## Data & Logs
- `data/translator_memory.db` — Your SQLite database (created automatically).
- `logs/app.log` — Backend service and API logs (rotating file handler).
