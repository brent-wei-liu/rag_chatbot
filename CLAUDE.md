# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A RAG (Retrieval-Augmented Generation) chatbot for course materials. Users ask questions via a web UI, the backend retrieves relevant course content from ChromaDB using semantic search, then generates answers via Claude API with tool use.

## Commands

```bash
# Install dependencies
uv sync

# Run the application (starts FastAPI on port 8000)
./run.sh
# Or manually:
uv run uvicorn api.app:app --reload --port 8000
```

No test suite exists. The app serves at http://localhost:8000 (web UI) and http://localhost:8000/docs (API docs).

## Architecture

**Backend** (`backend/`) — Python with FastAPI, all modules use relative imports from the `backend/` directory:

- `app.py` — FastAPI entry point. Mounts `frontend/` as static files at `/`. Two API endpoints: `POST /api/query` (RAG query) and `GET /api/courses` (course stats). Loads documents from `../docs` on startup.
- `rag_system.py` — Central orchestrator. Wires together document processing, vector store, AI generation, session management, and tool-based search. The `query()` method is the main flow: build prompt → get history → call AI with tools → collect sources → update session.
- `ai_generator.py` — Anthropic Claude API client. Implements a tool-use loop: sends initial request, if Claude wants to use a tool, executes it via `ToolManager`, then sends results back for a final response (single round only).
- `search_tools.py` — Tool abstraction layer. `Tool` ABC defines the interface. `CourseSearchTool` wraps vector store search as an Anthropic tool-use compatible tool. `ToolManager` registers tools and dispatches execution by name.
- `vector_store.py` — ChromaDB wrapper with two collections: `course_catalog` (course metadata, title as ID) and `course_content` (chunked text). `search()` optionally resolves fuzzy course names via catalog before searching content.
- `document_processor.py` — Parses course `.txt` files with a specific format (Course Title/Link/Instructor header, then `Lesson N:` sections). Chunks text by sentences respecting `CHUNK_SIZE`/`CHUNK_OVERLAP`.
- `session_manager.py` — In-memory conversation history per session. Conversation is passed as formatted text in the system prompt (not as message history).
- `models.py` — Pydantic models: `Course`, `Lesson`, `CourseChunk`.
- `config.py` — Dataclass config loaded from env vars. Key settings: `CHUNK_SIZE=800`, `CHUNK_OVERLAP=100`, `MAX_RESULTS=5`, `MAX_HISTORY=2`.

**Frontend** (`frontend/`) — Static HTML/CSS/JS served by FastAPI. No build step.

**Data** (`docs/`) — Course transcript `.txt` files with structured headers.

## Environment

Requires `ANTHROPIC_API_KEY` in `.env` at project root (see `.env.example`). Python 3.13+, managed with `uv`.

## Key Details

- The server runs from `backend/` as working directory — all relative paths in backend code are relative to `backend/` (e.g., `../docs`, `../frontend`).
- ChromaDB data persists to `db/chroma_db/`.
- The AI uses Claude's tool-use feature for search rather than directly injecting context into prompts.
- Tool execution is single-round: Claude calls a tool once, gets results, then produces a final answer.
