# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A RAG (Retrieval-Augmented Generation) chatbot for course materials. Users ask questions via a web UI, the backend retrieves relevant course content from ChromaDB using semantic search, then generates answers via Claude API with tool use.

## Commands

```bash
# Install dependencies
uv sync

# Run the application (ingest docs, then start FastAPI on port 8000)
./run.sh
# Or manually, two steps:
uv run python -m db.ingest --docs docs           # idempotent; skips already-ingested courses
uv run uvicorn api.app:app --reload --port 8000

# Retrieval eval (Recall@k, MRR). Only regression gate — no unit test framework.
uv run python evals/run_retrieval_eval.py

# Manual A/B for multi-round tool-use (N=1 vs N=2 answer quality)
uv run python evals/ab_multiround.py
```

The app serves at http://localhost:8000 (web UI) and http://localhost:8000/docs (API docs).

## Architecture

The backend is split into three top-level Python modules that communicate through a shared `core/` package. All modules are run from the project root (not from inside their own directory).

**`core/`** — shared code, imported by both `db/` and `api/`:
- `config.py` — Dataclass config loaded from env vars. Key settings: `CHUNK_SIZE=800`, `CHUNK_OVERLAP=100`, `MAX_RESULTS=5`, `MAX_HISTORY=2`, `MAX_TOOL_ROUNDS=2`, `CHROMA_PATH=./db/chroma_db`.
- `models.py` — Pydantic models: `Course`, `Lesson`, `CourseChunk`.
- `vector_store.py` — ChromaDB wrapper with two collections: `course_catalog` (course metadata, title as ID) and `course_content` (chunked text). `search()` optionally resolves fuzzy course names via the catalog before searching content.

**`db/`** — offline data layer (CLI, write-only to the vector store):
- `ingest.py` — CLI entry point: `python -m db.ingest [--docs path] [--clear]`. Iterates files, parses via `DocumentProcessor`, writes to ChromaDB via `core.vector_store`. Idempotent (skips courses by title).
- `document_processor.py` — Parses course `.txt` files (Course Title/Link/Instructor header, then `Lesson N:` sections). Chunks by sentence respecting `CHUNK_SIZE`/`CHUNK_OVERLAP`, prefixes each chunk with `"Course <title> Lesson <N> content: "` before embedding.
- `chroma_db/` — ChromaDB persistence (sqlite + HNSW .bin segments). Gitignored.

**`api/`** — online FastAPI service (read-only to the vector store):
- `app.py` — FastAPI entry point. Mounts `frontend/` as static files at `/`. Endpoints: `POST /api/query` and `GET /api/courses`. Does **not** read `docs/` on startup — ingestion is a separate CLI step.
- `rag_system.py` — Central orchestrator. The `query()` method: build prompt → get history → call AI with tools → collect sources → update session.
- `ai_generator.py` — Anthropic Claude client. Implements a **multi-round tool-use loop** capped at `config.MAX_TOOL_ROUNDS = 2`. Each round: call Claude → if `stop_reason == "tool_use"`, execute tools via `ToolManager` and append `tool_result` blocks → loop. If the cap is hit with the model still wanting tools, one final tool-less request forces a text answer. `CourseSearchTool.last_sources` accumulates + dedupes across rounds.
- `search_tools.py` — Tool abstraction. `Tool` ABC, `CourseSearchTool`, `CourseOutlineTool`, `ToolManager` (registration + dispatch by name).
- `session_manager.py` — In-memory conversation history per session. Passed as formatted text in the system prompt (not as message history).

**`evals/`** — retrieval evaluation harness (Recall@k, MRR) + A/B scripts. The only regression gate — no unit test framework.

**`frontend/`** — Static HTML/CSS/JS served by FastAPI. No build step.

**`docs/`** — Course transcript `.txt` files with structured headers.

## Environment

Requires `ANTHROPIC_API_KEY` in `.env` at project root (see `.env.example`). Python 3.13+, managed with `uv`.

## Key Details

- The server and CLI both run from the project **root** (not from inside `api/` or `db/`). Imports are absolute (`from core.config import config`, `from api.rag_system import RAGSystem`, etc.).
- ChromaDB data persists to `db/chroma_db/`.
- `api/` is **read-only** to the vector store. `db/ingest` is the only writer. Ingestion is a separate CLI step — the API server does **not** read `docs/` on startup.
- The AI uses Claude's tool-use feature for search rather than directly injecting context into prompts.
- Tool execution is **multi-round**, capped at `config.MAX_TOOL_ROUNDS = 2`: Claude can call tools, see results, and call tools again before producing a final answer. If the cap is hit, a final tool-less request forces a text answer.
