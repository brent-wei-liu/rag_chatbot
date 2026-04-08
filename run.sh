#!/bin/bash
set -e

# Ingest documents (idempotent — existing courses are skipped)
uv run python -m db.ingest --docs docs

# Start API (cwd = project root)
uv run uvicorn api.app:app --reload --port 8000
