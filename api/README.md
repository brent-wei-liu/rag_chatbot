# api/

FastAPI service for the course-materials RAG chatbot. Handles HTTP requests from the frontend, runs Claude with tool-use to answer questions, and reads from the ChromaDB vector store populated by `db/`.

This module is **read-only** with respect to the vector store — it never ingests documents. Ingestion is a separate offline step (`python -m db.ingest`).

## Run

From project root:

```bash
uv run uvicorn api.app:app --reload --port 8000
```

Or via the wrapper that ingests first:

```bash
./run.sh
```

Then open http://localhost:8000 (web UI) or http://localhost:8000/docs (OpenAPI).

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/query` | Answer a question. Body: `{query, session_id?}`. Returns `{answer, sources, session_id}`. |
| `POST` | `/api/new-session` | Create a new conversation session. |
| `GET`  | `/api/courses` | Course catalog stats: `{total_courses, course_titles}`. |

## Files

- `app.py` — FastAPI entry point. Defines endpoints, mounts `frontend/` as static files, instantiates the global `RAGSystem`.
- `rag_system.py` — Orchestrator. `query()` builds the prompt, fetches conversation history, calls the AI with tools, collects sources, and updates the session.
- `ai_generator.py` — Anthropic Claude client. Implements a single-round tool-use loop: initial request → if Claude calls a tool, execute it via `ToolManager` → send results back for the final answer.
- `search_tools.py` — Tool abstraction layer. `Tool` ABC, `CourseSearchTool` and `CourseOutlineTool` (both wrap `core.vector_store`), `ToolManager` for registration and dispatch.
- `session_manager.py` — In-memory per-session conversation history. History is injected into the system prompt as formatted text rather than as message history.

## Dependencies

- `core/` — `VectorStore`, `Config`, Pydantic models
- `db/chroma_db/` — populated by `db/ingest.py`; this module only reads from it
- Environment: `ANTHROPIC_API_KEY` in `.env` at project root
