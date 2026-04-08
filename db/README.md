# db/

Offline data layer for the course-materials RAG chatbot. Owns the document parser, the ingestion CLI, and the on-disk ChromaDB store.

This module is **write-only** with respect to the vector store from the application's perspective — it produces the data that `api/` later reads. It is run as a standalone CLI, not imported by the API process.

## Run

From project root:

```bash
# Ingest docs/, skip courses already in the store
uv run python -m db.ingest

# Custom docs folder
uv run python -m db.ingest --docs path/to/docs

# Drop existing collections and re-ingest from scratch
uv run python -m db.ingest --clear
```

Idempotent: re-running with the default flags is safe — courses already present (matched by title) are skipped.

## Files

- `ingest.py` — CLI entry point. Walks the docs folder, parses each file via `DocumentProcessor`, and writes to ChromaDB through `core.vector_store`. Prints a summary of added/skipped courses.
- `document_processor.py` — Parses course `.txt` files with the project's specific format (Course Title / Link / Instructor header followed by `Lesson N:` sections). Chunks text by sentences honoring `CHUNK_SIZE` / `CHUNK_OVERLAP` from `core.config`.
- `chroma_db/` — ChromaDB persistence directory. Holds two collections: `course_catalog` (course metadata, title as ID) and `course_content` (chunked text). Gitignored.

## Course file format

`document_processor.py` expects files like:

```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 1: <lesson title>
Lesson Link: <url>
<lesson body...>

Lesson 2: <lesson title>
...
```

Files without this header are skipped with an error logged to stderr.

## Dependencies

- `core/` — `Config`, `VectorStore`, Pydantic models
- ChromaDB (via `core.vector_store`) — persisted to `db/chroma_db/`

## Not in scope

- File watching / auto re-ingestion on changes
- Per-file incremental updates beyond title-based dedup
- Answer-quality evaluation — see `evals/` for the retrieval eval harness
