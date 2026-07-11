# Web UI Plan — Translator Memory Engine

## 1. Technology Stack

| Layer             | Choice                | Version | Rationale                                                |
| ----------------- | --------------------- | ------- | -------------------------------------------------------- |
| **Backend**       | FastAPI               | 0.139.0 | Auto OpenAPI docs, async, Pydantic v2, largest ecosystem |
| **ORM**           | SQLAlchemy (async)    | 2.0.51  | Mature, SQLite support, async-first                      |
| **DB Driver**     | aiosqlite             | 0.22.1  | Async SQLite driver                                      |
| **Database**      | SQLite                | —       | Lightweight, local, zero config                          |
| **Server**        | uvicorn               | 0.51.0  | Standard ASGI server                                     |
| **Frontend**      | React                 | 19.2.7  | Latest stable, react-dom bundled                         |
| **Language**      | TypeScript            | —       | Type safety, better DX                                   |
| **Build**         | Vite                  | 8.1.4   | Fast HMR, ESM-native                                     |
| **CSS**           | Tailwind CSS          | 4.3.2   | CSS-first config (v4), `@tailwindcss/vite` plugin        |
| **Routing**       | react-router-dom      | 7.18.1  | v7 stable                                                |
| **Data Fetching** | @tanstack/react-query | 5.101.2 | Caching, polling, revalidation                           |

## 2. Decoupled Architecture

```
translator-memory-engine/
├── translator_memory_engine/     # Core engine (UNCHANGED, pure Python)
│   ├── extract/
│   ├── policy/
│   ├── rewrite/
│   ├── retrieve/
│   ├── memory/
│   ├── style/
│   └── eval/
│
├── web/                          # Web application (DEDICATED folder)
│   ├── backend/                  # FastAPI server
│   │   ├── app.py                # FastAPI app, CORS, static mount
│   │   ├── config.py             # Settings (DB path, API keys)
│   │   ├── db/
│   │   │   ├── database.py       # Async engine, session maker
│   │   │   └── models.py         # SQLAlchemy models
│   │   ├── api/
│   │   │   ├── novels.py
│   │   │   ├── chapters.py
│   │   │   ├── policies.py
│   │   │   └── jobs.py
│   │   ├── schemas/
│   │   │   ├── novel.py
│   │   │   ├── chapter.py
│   │   │   ├── policy.py
│   │   │   └── job.py
│   │   └── services/
│   │       ├── extract_service.py
│   │       ├── rewrite_service.py
│   │       └── job_runner.py
│   │
│   └── frontend/                 # React app
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── index.html
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           ├── index.css          # Tailwind v4 CSS-first config
│           ├── pages/
│           │   ├── Dashboard.tsx
│           │   ├── NovelView.tsx
│           │   └── Reader.tsx
│           ├── components/
│           │   ├── NovelCard.tsx
│           │   ├── ChapterList.tsx
│           │   ├── PasteForm.tsx
│           │   ├── ReaderView.tsx
│           │   └── ThemeToggle.tsx
│           ├── hooks/
│           │   ├── useReaderSettings.ts
│           │   └── useChapterData.ts
│           └── api/
│               └── client.ts
│
├── pipeline.py                   # CLI (unchanged)
├── data/
│   ├── translator_memory.db      # SQLite DB (created at runtime)
│   ├── known_errors.json
│   ├── originals/
│   ├── mtl/
│   ├── output/
│   └── policies/
├── tests/
├── pyproject.toml
└── ...
```

### Dependency Flow (One-Way)

```
web/backend/services/  ──imports──►  translator_memory_engine/
        │
        ▼
   web/backend/api/  ──imports──►  web/backend/services/
        │
        ▼
   web/backend/app.py  ──imports──►  web/backend/api/
```

**Decoupling rules:**

1. Core engine (`translator_memory_engine/`) has **zero knowledge** of the web layer
2. Web backend imports from core engine, **never the reverse**
3. Core engine stays pure Python — usable via CLI (`pipeline.py`) or web
4. Services layer wraps core functions, handles DB persistence, returns Pydantic models
5. Frontend talks to backend via REST API only

## 3. Database Schema

```sql
-- Novels (containers)
CREATE TABLE novels (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    title TEXT,
    source_language TEXT DEFAULT 'korean',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chapters
CREATE TABLE chapters (
    id INTEGER PRIMARY KEY,
    novel_id INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('mtl', 'original')),
    raw_text TEXT NOT NULL,
    refined_text TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,
    processing_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(novel_id, chapter_number, source_type)
);

-- Policies (per novel)
CREATE TABLE policies (
    id INTEGER PRIMARY KEY,
    novel_id INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    policy_id TEXT NOT NULL,
    type TEXT NOT NULL,
    trigger TEXT NOT NULL,
    match_forms TEXT NOT NULL,       -- JSON array
    action TEXT NOT NULL,            -- JSON object
    confidence REAL NOT NULL,
    evidence_chapters TEXT,          -- JSON array
    applies TEXT DEFAULT 'deterministic',
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Glossary (per novel, derived from policies)
CREATE TABLE glossary (
    id INTEGER PRIMARY KEY,
    novel_id INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    canonical TEXT NOT NULL,
    aliases TEXT NOT NULL,           -- JSON array
    entity_type TEXT,
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Processing jobs
CREATE TABLE processing_jobs (
    id INTEGER PRIMARY KEY,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK(job_type IN ('extract', 'rewrite', 'eval')),
    status TEXT DEFAULT 'queued' CHECK(status IN ('queued', 'running', 'completed', 'failed')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    result_summary TEXT              -- JSON summary
);
```

## 4. API Endpoints

```
POST   /api/v1/novels                           → Create novel
GET    /api/v1/novels                           → List novels
GET    /api/v1/novels/{id}                      → Get novel details
DELETE /api/v1/novels/{id}                      → Delete novel

POST   /api/v1/novels/{id}/chapters             → Create chapter (paste text + chapter_number)
GET    /api/v1/novels/{id}/chapters             → List chapters
GET    /api/v1/novels/{id}/chapters/{ch_num}    → Get specific chapter

POST   /api/v1/chapters/{id}/process            → Trigger rewrite
POST   /api/v1/chapters/{id}/reprocess          → Retrigger
GET    /api/v1/chapters/{id}/status             → Check processing status
GET    /api/v1/chapters/{id}/read               → Get refined text

GET    /api/v1/novels/{id}/policies             → List policies
GET    /api/v1/novels/{id}/glossary             → Get glossary

GET    /api/v1/jobs/{id}                        → Get job status
```

## 5. User Flow

```
1. Dashboard → See all novels, create new novel
2. Click novel → Chapter list + paste interface
3. Paste MTL text into <textarea>
4. Enter chapter number
5. Click "Process" → triggers rewrite pipeline via API
6. While processing: show spinner, poll /status every 2s
7. After completion: chapter appears in list with "Read" button
8. Click "Read" → WebNovel-style reader
9. "Reprocess" button on each chapter if needed
```

## 6. Reader Design

- **Mobile:** Single-column scroll, `max-width: 680px`, comfortable reading spacing
- **Desktop:** Double-page toggle, `max-width: 1200px`
- **Themes:** Dark (default), Light, Sepia — persisted in localStorage
- **Font controls:** Increase/decrease font size, font family selector
- **Reading position:** Remembered in localStorage

## 7. Dependencies

### Python (pyproject.toml additions)

```
fastapi>=0.139.0
uvicorn[standard]>=0.51.0
sqlalchemy[asyncio]>=2.0.51
aiosqlite>=0.22.1
```

### Frontend (package.json)

```
react@19.2.7
react-dom@19.2.7
react-router-dom@7.18.1
@tanstack/react-query@5.101.2
tailwindcss@4.3.2
@tailwindcss/vite@4.3.2
typescript@5.x
@types/react
@types/react-dom
@vitejs/plugin-react
vite@8.1.4
```

## 8. Implementation Phases

| Phase | What                                                        | Est. |
| ----- | ----------------------------------------------------------- | ---- |
| **1** | Backend foundation (DB models, config, CRUD API)            | 5h   |
| **2** | Pipeline integration (extract/rewrite services, job runner) | 4h   |
| **3** | Frontend shell (React + routing + novel list + paste form)  | 5h   |
| **4** | Reader component (mobile/desktop + themes + fonts)          | 5h   |
| **5** | Polish (error handling, loading states, status polling)     | 3h   |
