# Split `backend/` into `api/` + `db/` + `core/`

**Date:** 2026-04-07
**Status:** Approved

## Goal

Decouple offline data ingestion from the online API service by splitting the current monolithic `backend/` directory into three top-level modules with clear responsibilities. The API process should no longer touch `docs/` at startup; ingestion becomes an explicit, separately-runnable step.

## Target Directory Structure

```
project-root/
├── core/                       # Shared code, depended on by api/ and db/
│   ├── __init__.py
│   ├── models.py               # Course, Lesson, CourseChunk
│   ├── config.py               # Dataclass config (paths, keys, chunking)
│   └── vector_store.py         # ChromaDB wrapper (read + write)
├── db/                         # Offline ingestion module
│   ├── __init__.py
│   ├── document_processor.py
│   ├── ingest.py               # CLI entry point
│   └── chroma_db/              # ChromaDB persistence (gitignored)
├── api/                        # Online FastAPI service (renamed from backend/)
│   ├── __init__.py
│   ├── app.py
│   ├── rag_system.py
│   ├── ai_generator.py
│   ├── search_tools.py
│   └── session_manager.py
├── frontend/
├── docs/
└── run.sh
```

## Module Responsibilities

### `core/`
Shared library. Depends on no other project module.

- `models.py` — Pydantic models: `Course`, `Lesson`, `CourseChunk`
- `config.py` — Dataclass config from env vars. `CHROMA_PATH = "./db/chroma_db"` (relative to project root). All other settings unchanged.
- `vector_store.py` — ChromaDB wrapper. Both read and write methods stay together in one cohesive class.

### `db/`
Offline, one-shot ingestion task. **Not imported by `api/`.**

- `document_processor.py` — Unchanged logic; parses course `.txt` files and chunks them.
- `ingest.py` — New CLI entry point. Runnable as `python -m db.ingest`.
  - Args: `--docs <path>` (default `docs`), `--clear` (drop existing collections before ingesting)
  - Reads files from the docs folder, parses via `document_processor`, writes via `core.vector_store`
  - Skips courses already present (by title), matching current behavior
  - Prints summary: courses added, chunks created, courses skipped
- `chroma_db/` — ChromaDB persistence directory. Added to `.gitignore`.

### `api/`
FastAPI service. Startup no longer touches `docs/` or runs ingestion.

- `app.py` — Remove the `add_course_folder("../docs")` call from the startup hook. Static file mount paths updated for new working directory (see below).
- `rag_system.py` — Remove `add_course_document` and `add_course_folder` methods (logic moved to `db/ingest.py`). Keep `query()` and `get_course_analytics()`. No longer instantiates `DocumentProcessor`.
- `ai_generator.py`, `search_tools.py`, `session_manager.py` — Unchanged except for import paths.

## Data Flow

**Offline (manual trigger):**
```
docs/*.txt → db/ingest.py → document_processor → core/vector_store → db/chroma_db/
```

**Online (per request):**
```
HTTP → api/app.py → api/rag_system → api/ai_generator
                                    ↘ api/search_tools → core/vector_store → db/chroma_db/
```

## Working Directory Change

The server's working directory changes from `backend/` to **project root**. All relative paths must be updated accordingly:

| Path | Before (cwd=`backend/`) | After (cwd=project root) |
|------|------|------|
| Docs folder | `../docs` | `docs` |
| Frontend mount | `../frontend` | `frontend` |
| ChromaDB | `./chroma_db` | `db/chroma_db` |

## `run.sh` Changes

Before:
```bash
cd backend && uv run uvicorn app:app --reload --port 8000
```

After:
```bash
#!/bin/bash
# Ingest documents (idempotent - skips existing courses)
uv run python -m db.ingest --docs docs

# Start API
uv run uvicorn api.app:app --reload --port 8000
```

## Import Path Changes

Examples of how imports change:

```python
# Before (backend/rag_system.py)
from document_processor import DocumentProcessor
from vector_store import VectorStore
from models import Course

# After (api/rag_system.py)
from core.vector_store import VectorStore
from core.models import Course
# document_processor is no longer imported — it lives in db/
```

```python
# db/ingest.py (new)
from core.config import config
from core.vector_store import VectorStore
from db.document_processor import DocumentProcessor
```

## One-Time Migration Steps

These must be performed once when applying the change:

1. Move existing data: `mv backend/chroma_db db/chroma_db` (preserves already-ingested courses so users don't need to re-run ingest immediately).
2. Add `db/chroma_db/` to `.gitignore` if not already ignored.
3. Update `pyproject.toml` if it declares packages explicitly (currently does not need adjustment).

## Verification

No automated test suite exists. Manual verification:

1. Run `uv run python -m db.ingest --docs docs` — confirm `db/chroma_db/` is populated and the log lists courses.
2. Start the API via `./run.sh` — confirm startup logs do **not** contain any document-processing output (proves API no longer reads `docs/`).
3. `GET /api/courses` returns the correct course count and titles.
4. `POST /api/query` returns an answer with sources for a known question.
5. Re-run `python -m db.ingest` — confirm all courses are reported as "already exists, skipping".
6. Run `python -m db.ingest --clear` — confirm collections are cleared and re-ingested.

## Out of Scope (YAGNI)

- File watching / auto re-ingestion on changes
- Per-file incremental updates beyond current title-based dedup
- Frontend changes
- New dependencies
- Rewriting `pyproject.toml` package layout beyond what's strictly required
- Multi-round Claude tool use, session persistence, or other unrelated improvements

## Risks

- **Stale paths:** Any hardcoded relative path missed during the move will break at runtime. The verification steps above should catch all of them.
- **Forgotten migration:** If a user pulls the change without moving `backend/chroma_db/`, the API will appear to have an empty database. Mitigation: document the migration step prominently in the commit message.
