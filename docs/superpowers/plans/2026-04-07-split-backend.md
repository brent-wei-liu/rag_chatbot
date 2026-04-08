# Split `backend/` into `api/` + `db/` + `core/` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple offline document ingestion from the online FastAPI service by splitting `backend/` into three top-level modules: `core/` (shared), `db/` (offline ingestion + ChromaDB persistence), `api/` (FastAPI service).

**Architecture:** `core/` holds models, config, and the ChromaDB wrapper — depended on by both other modules. `db/` owns ingestion code and the `chroma_db/` data directory and is run as a CLI (`python -m db.ingest`). `api/` is the renamed `backend/` minus all ingestion code; it no longer touches `docs/` at startup. The server's working directory moves from `backend/` to project root.

**Tech Stack:** Python 3.13, FastAPI, ChromaDB, Anthropic SDK, `uv`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-07-split-backend-design.md`

**Verification approach:** No unit test suite. Use the existing retrieval evaluation harness in `evals/` as the acceptance gate — it imports `config` and `vector_store` directly and exercises real ChromaDB. After the migration, re-running `evals/run_retrieval_eval.py` and getting the same metrics as the pre-migration baseline proves both the import paths and the data path are correct.

---

## Pre-flight

### Task 0: Capture pre-migration baseline

**Files:**
- Read: `evals/baselines/` (whatever exists)

- [ ] **Step 1: Confirm ChromaDB is populated**

Run: `ls backend/chroma_db/`
Expected: directory exists and is non-empty (contains `chroma.sqlite3` etc).

If empty, run `./run.sh` once, wait for "Loaded N courses" log, ctrl-c.

- [ ] **Step 2: Run retrieval eval to capture pre-migration metrics**

Run: `uv run python evals/run_retrieval_eval.py`
Expected: prints a JSON report with `overall.mrr`, `overall.recall@1/3/5`. A new file appears under `evals/baselines/<today>.json`.

- [ ] **Step 3: Save pre-migration baseline filename**

Note the filename printed at the end (e.g. `evals/baselines/2026-04-07.json`). After the migration, the new run must produce identical numbers.

- [ ] **Step 4: Commit baseline**

```bash
git add evals/baselines/
git commit -m "evals: capture pre-migration retrieval baseline"
```

---

## Task 1: Create `core/` package

**Files:**
- Create: `core/__init__.py`
- Create: `core/models.py` (moved from `backend/models.py`)
- Create: `core/config.py` (moved + edited from `backend/config.py`)
- Create: `core/vector_store.py` (moved from `backend/vector_store.py`)

- [ ] **Step 1: Create the package directory and `__init__.py`**

```bash
mkdir -p core
```

Create `core/__init__.py` as an empty file:
```python
```

- [ ] **Step 2: Move `models.py` into `core/`**

```bash
git mv backend/models.py core/models.py
```

No content edits — `models.py` has no project-internal imports.

- [ ] **Step 3: Move `config.py` into `core/` and update CHROMA_PATH**

```bash
git mv backend/config.py core/config.py
```

Edit `core/config.py` line 25:

```python
    # Database paths
    CHROMA_PATH: str = "./db/chroma_db"  # ChromaDB storage location (relative to project root)
```

- [ ] **Step 4: Move `vector_store.py` into `core/`**

```bash
git mv backend/vector_store.py core/vector_store.py
```

Then check imports inside `core/vector_store.py`. Run:

```bash
grep -n "^from \|^import " core/vector_store.py
```

If it imports `from models import ...`, change to `from core.models import ...`. If it uses no project-internal imports, leave it.

- [ ] **Step 5: Sanity check core/ is importable**

Run from project root:
```bash
uv run python -c "from core.config import config; from core.models import Course; from core.vector_store import VectorStore; print('ok', config.CHROMA_PATH)"
```
Expected: `ok ./db/chroma_db`

- [ ] **Step 6: Commit**

```bash
git add core/ backend/
git commit -m "refactor: move models, config, vector_store into core/ package"
```

---

## Task 2: Create `db/` package and move data + processor

**Files:**
- Create: `db/__init__.py`
- Create: `db/document_processor.py` (moved from `backend/document_processor.py`)
- Move: `backend/chroma_db/` → `db/chroma_db/`
- Modify: `.gitignore`

- [ ] **Step 1: Create the package directory**

```bash
mkdir -p db
```

Create `db/__init__.py` as an empty file.

- [ ] **Step 2: Move `document_processor.py`**

```bash
git mv backend/document_processor.py db/document_processor.py
```

Check internal imports:
```bash
grep -n "^from \|^import " db/document_processor.py
```

If it imports `from models import ...`, change to `from core.models import ...`. Other project-internal imports get the same treatment (`core.config`, etc.).

- [ ] **Step 3: Move ChromaDB data directory**

This is **untracked** by git (chroma_db is data, not code), so use plain `mv`:

```bash
mv backend/chroma_db db/chroma_db
```

- [ ] **Step 4: Add `db/chroma_db/` to .gitignore**

Read current `.gitignore`:
```bash
cat .gitignore
```

If `db/chroma_db/` (or a parent pattern that covers it) is not present, append:

```
db/chroma_db/
```

If `chroma_db/` is already in `.gitignore` as a bare pattern, that already covers `db/chroma_db/` — leave it.

- [ ] **Step 5: Verify data is reachable from new path**

```bash
uv run python -c "
from core.config import config
from core.vector_store import VectorStore
s = VectorStore(config.CHROMA_PATH, config.EMBEDDING_MODEL, config.MAX_RESULTS)
print('courses:', s.get_course_count())
print('titles:', s.get_existing_course_titles())
"
```
Expected: prints the same course count as before the migration (non-zero).

- [ ] **Step 6: Commit**

```bash
git add db/ backend/ .gitignore
git commit -m "refactor: move document_processor and chroma_db data into db/"
```

---

## Task 3: Write `db/ingest.py` CLI

**Files:**
- Create: `db/ingest.py`

- [ ] **Step 1: Create the CLI**

Create `db/ingest.py`:

```python
"""CLI entry point for ingesting course documents into ChromaDB.

Usage:
    python -m db.ingest                     # ingest ./docs, skip existing
    python -m db.ingest --docs path/to/docs # custom docs folder
    python -m db.ingest --clear             # drop existing collections first
"""
import argparse
import os
import sys

from core.config import config
from core.vector_store import VectorStore
from db.document_processor import DocumentProcessor


def ingest(docs_path: str, clear_existing: bool) -> tuple[int, int]:
    """Ingest all course files from docs_path into ChromaDB.

    Returns (courses_added, chunks_added). Courses already present (by title)
    are skipped unless clear_existing is True.
    """
    if not os.path.exists(docs_path):
        print(f"ERROR: docs folder not found: {docs_path}", file=sys.stderr)
        sys.exit(1)

    processor = DocumentProcessor(config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    store = VectorStore(config.CHROMA_PATH, config.EMBEDDING_MODEL, config.MAX_RESULTS)

    if clear_existing:
        print("Clearing existing collections...")
        store.clear_all_data()

    existing_titles = set(store.get_existing_course_titles())

    courses_added = 0
    chunks_added = 0
    skipped = 0

    for file_name in sorted(os.listdir(docs_path)):
        file_path = os.path.join(docs_path, file_name)
        if not (os.path.isfile(file_path) and file_name.lower().endswith((".pdf", ".docx", ".txt"))):
            continue

        try:
            course, course_chunks = processor.process_course_document(file_path)
        except Exception as e:
            print(f"  error parsing {file_name}: {e}", file=sys.stderr)
            continue

        if not course:
            continue

        if course.title in existing_titles:
            print(f"  skip (exists): {course.title}")
            skipped += 1
            continue

        store.add_course_metadata(course)
        store.add_course_content(course_chunks)
        existing_titles.add(course.title)
        courses_added += 1
        chunks_added += len(course_chunks)
        print(f"  added: {course.title} ({len(course_chunks)} chunks)")

    print(f"\nDone. Added {courses_added} course(s), {chunks_added} chunk(s). Skipped {skipped}.")
    return courses_added, chunks_added


def main():
    parser = argparse.ArgumentParser(description="Ingest course documents into ChromaDB.")
    parser.add_argument("--docs", default="docs", help="Path to docs folder (default: docs)")
    parser.add_argument("--clear", action="store_true", help="Clear existing collections before ingesting")
    args = parser.parse_args()
    ingest(args.docs, args.clear)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI runs and is idempotent**

Run from project root:
```bash
uv run python -m db.ingest --docs docs
```
Expected: every existing course prints `skip (exists): ...`, summary says `Added 0 course(s), 0 chunk(s). Skipped N.` (N = number of courses in `docs/`).

- [ ] **Step 3: Commit**

```bash
git add db/ingest.py
git commit -m "feat(db): add ingest CLI for offline document loading"
```

---

## Task 4: Rename `backend/` → `api/` and fix imports

**Files:**
- Rename: `backend/` → `api/`
- Modify: `api/app.py` (remove startup ingestion, fix paths and imports)
- Modify: `api/rag_system.py` (remove ingestion methods, fix imports)
- Modify: `api/ai_generator.py`, `api/search_tools.py`, `api/session_manager.py` (fix imports if any)

- [ ] **Step 1: Rename the directory**

```bash
git mv backend api
```

- [ ] **Step 2: Add `api/__init__.py` if missing**

```bash
ls api/__init__.py 2>/dev/null || touch api/__init__.py
git add api/__init__.py
```

- [ ] **Step 3: Update `api/rag_system.py` — fix imports and delete ingestion methods**

Read the current file at `api/rag_system.py`. Replace the import block (lines 1–8) with:

```python
from typing import List, Optional, Dict, Tuple

from core.vector_store import VectorStore
from api.ai_generator import AIGenerator
from api.session_manager import SessionManager
from api.search_tools import ToolManager, CourseSearchTool, CourseOutlineTool
```

Note: `DocumentProcessor` and `models` imports are removed — neither is used after the deletions below.

Then delete two methods entirely:
- `add_course_document` (currently lines 29–52)
- `add_course_folder` (currently lines 54–102)

Also delete the `self.document_processor = ...` line in `__init__` (currently line 17).

After edits, `RAGSystem` should expose only `__init__`, `query`, and `get_course_analytics`.

- [ ] **Step 4: Update `api/app.py` — fix imports, paths, remove startup ingestion**

Edit `api/app.py`:

Replace lines 12–13:
```python
from core.config import config
from api.rag_system import RAGSystem
```

Delete the entire startup hook (currently lines 104–114):
```python
@app.on_event("startup")
async def startup_event():
    """Load initial documents on startup"""
    docs_path = "../docs"
    ...
```

Replace the static mount (currently line 135):
```python
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
```

(Path changed from `../frontend` to `frontend` because cwd is now project root.)

- [ ] **Step 5: Fix imports in remaining api/ files**

For each of `api/ai_generator.py`, `api/search_tools.py`, `api/session_manager.py`, check imports:

```bash
grep -n "^from \|^import " api/ai_generator.py api/search_tools.py api/session_manager.py
```

For any line like `from models import ...`, `from config import ...`, `from vector_store import ...`, prefix with `core.`. For any cross-imports between these files (e.g., `from search_tools import ...`), prefix with `api.`.

- [ ] **Step 6: Sanity check the import graph**

```bash
uv run python -c "from api.app import app; print('ok')"
```
Expected: `ok`. No `ModuleNotFoundError`.

If you see `ModuleNotFoundError`, find the offending import and add the appropriate `core.` or `api.` prefix.

- [ ] **Step 7: Commit**

```bash
git add api/
git commit -m "refactor: rename backend/ to api/, drop startup ingestion, fix imports"
```

---

## Task 5: Update `run.sh`

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Replace `run.sh` contents**

Read current `run.sh` first to preserve any shebang/comments. Replace the runnable portion with:

```bash
#!/bin/bash
set -e

# Ingest documents (idempotent — existing courses are skipped)
uv run python -m db.ingest --docs docs

# Start API (cwd = project root)
uv run uvicorn api.app:app --reload --port 8000
```

- [ ] **Step 2: Make sure it's executable**

```bash
chmod +x run.sh
```

- [ ] **Step 3: Smoke test the server starts and serves requests**

Run in one terminal:
```bash
./run.sh
```

In another terminal (or background the server):
```bash
curl -s http://localhost:8000/api/courses
```
Expected: JSON with `total_courses` matching the pre-migration count.

Then test a query:
```bash
curl -s -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"what is MCP"}'
```
Expected: JSON with non-empty `answer` and `sources`.

Stop the server (ctrl-c).

- [ ] **Step 4: Verify startup no longer reads docs/**

Look at the server's startup logs from the previous step. Confirm there is **no** "Loading initial documents..." or "Loaded N courses" line. (Ingestion ran via `db.ingest` before the server started, not inside it.)

- [ ] **Step 5: Commit**

```bash
git add run.sh
git commit -m "chore: update run.sh to use new api/db layout"
```

---

## Task 6: Update `evals/` for new layout

**Files:**
- Modify: `evals/run_retrieval_eval.py`
- Modify: `evals/generate_groundtruth.py`
- Modify: `evals/README.md`

- [ ] **Step 1: Update `evals/run_retrieval_eval.py` imports and chroma path**

Edit `evals/run_retrieval_eval.py`:

Replace lines 13–17:
```python
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import config  # noqa: E402
from core.vector_store import VectorStore  # noqa: E402
```

Replace the chroma_path resolution (currently lines 52–53):
```python
    # CHROMA_PATH is relative to project root
    chroma_path = str(ROOT / config.CHROMA_PATH.lstrip("./"))
```

- [ ] **Step 2: Update `evals/generate_groundtruth.py` imports**

Edit `evals/generate_groundtruth.py`. Find the block at lines 13–18:
```python
# Make backend importable for config
...
sys.path.insert(0, str(ROOT / "backend"))

from anthropic import Anthropic  # noqa: E402
from config import config  # noqa: E402
```

Replace with:
```python
# Make project root importable
sys.path.insert(0, str(ROOT))

from anthropic import Anthropic  # noqa: E402
from core.config import config  # noqa: E402
```

- [ ] **Step 3: Update `evals/README.md` references to backend/chroma_db**

Read `evals/README.md`. Replace any occurrence of `backend/chroma_db/` with `db/chroma_db/`. Also update the ingestion instruction in the "运行方式" section:

Replace:
```
# 2. 确保 ChromaDB 已被填充（运行一次应用来 ingest docs/）
./run.sh   # 看到启动日志显示 ingestion 完成后 ctrl-c 退出
```

With:
```
# 2. 确保 ChromaDB 已被填充
uv run python -m db.ingest --docs docs
```

And in "对比改动" section, replace `删除 backend/chroma_db/ 再重启应用` with `删除 db/chroma_db/ 后跑 python -m db.ingest --clear`.

- [ ] **Step 4: Run the eval and confirm metrics match the baseline**

```bash
uv run python evals/run_retrieval_eval.py
```

Compare the printed `overall` block to the baseline file from Task 0:

```bash
diff <(jq .overall evals/baselines/<pre-migration>.json) <(jq .overall evals/baselines/$(date +%Y-%m-%d).json)
```

Expected: empty diff (identical metrics). Same data, same vector store, same code path → same numbers.

If metrics differ, the migration corrupted something — investigate before continuing. Most likely cause: chroma path resolved to a different (empty) directory.

- [ ] **Step 5: Commit**

```bash
git add evals/
git commit -m "evals: update imports and paths for new api/db layout"
```

---

## Task 7: Final cleanup and verification

- [ ] **Step 1: Confirm no stray references to old paths**

Run:
```bash
grep -rn "from backend\|backend/chroma_db\|backend\.app\|cd backend" \
    --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=db --exclude-dir=evals/baselines .
```

Expected: no matches in code (matches in `docs/superpowers/specs/` describing the migration are fine).

If anything turns up in code, fix it and amend the appropriate prior commit (or add a follow-up commit).

- [ ] **Step 2: Confirm `backend/` no longer exists**

```bash
ls backend 2>&1
```
Expected: `ls: backend: No such file or directory`

- [ ] **Step 3: End-to-end smoke test**

Start the server:
```bash
./run.sh &
sleep 3
curl -s http://localhost:8000/api/courses | head -c 200
curl -s -X POST http://localhost:8000/api/query \
    -H 'Content-Type: application/json' \
    -d '{"query":"what is retrieval augmented generation"}' | head -c 500
kill %1
```

Expected: both curls return valid JSON; the query response has a non-empty `answer`.

- [ ] **Step 4: Final commit if any cleanup happened**

```bash
git status
# If changes exist:
git add -A
git commit -m "chore: final cleanup after backend split"
```

---

## Definition of Done

- `backend/` directory no longer exists.
- `core/`, `db/`, `api/` exist with the structure described in the spec.
- `db/chroma_db/` holds the migrated ChromaDB data and is gitignored.
- `python -m db.ingest` works from project root and is idempotent.
- `./run.sh` ingests then starts the server; the server's startup logs do **not** mention loading documents.
- `GET /api/courses` and `POST /api/query` work end-to-end.
- `evals/run_retrieval_eval.py` produces metrics identical to the pre-migration baseline.
- All changes committed in small, logical commits.
