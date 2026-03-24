# Course Materials RAG System

A Retrieval-Augmented Generation (RAG) system designed to answer questions about course materials using semantic search and AI-powered responses.

## Overview

This application is a full-stack web application that enables users to query course materials and receive intelligent, context-aware responses. It uses ChromaDB for vector storage, Anthropic's Claude for AI generation, and provides a web interface for interaction.

## Tech Stack

| Layer | Technology | Version / Notes |
|-------|-----------|-----------------|
| **Application** | FastAPI | 0.116.1 |
| | Uvicorn | 0.35.0 |
| **AI** | Anthropic SDK | 0.58.2 (Model: `claude-opus-4-6`) |
| | sentence-transformers | 5.0.0 (Model: `all-MiniLM-L6-v2`) |
| **Data** | ChromaDB | 1.0.15 |
| **Frontend** | HTML / CSS / JS | Static, no framework |
| **Testing** | Playwright | Via pytest-playwright |
| | pytest | 9.0+ |
| **Tooling** | Python | 3.13+ |
| | uv | Package manager |
| | python-dotenv | 1.1.1 |
| | python-multipart | 0.0.20 |

## RAG Search Design: Tool Use vs Direct Injection

Traditional RAG systems use a direct injection approach: take the user's question, search the vector database, and stuff the results into the prompt. This project takes a different approach — it gives Claude a **search tool** and lets the AI decide how to search.

| | Direct Injection | Tool Use (This Project) |
|---|---|---|
| **Search query** | User's raw question | Claude crafts optimized search terms |
| **Filtering** | Hard-coded or none | Claude decides whether to filter by course/lesson |
| **Flow** | Question → Search → Prompt → Answer | Question → Claude → Tool Call → Search → Answer |

The key component is `CourseSearchTool` (`backend/search_tools.py`), which wraps the ChromaDB vector store as an Anthropic tool-use compatible tool. When a user asks a question, Claude receives the question along with the tool definition, decides what to search for (and whether to filter by course name or lesson number), invokes the tool, receives the results, and then generates a grounded answer.

The underlying search still hits the local ChromaDB — the tool just lets **Claude drive the search strategy** instead of hard-coding it in the backend.

## Prerequisites

- Python 3.13 or higher
- uv (Python package manager)
- An Anthropic API key (for Claude AI)
- **For Windows**: Use Git Bash to run the application commands - [Download Git for Windows](https://git-scm.com/downloads/win)

## Installation

1. **Install uv** (if not already installed)
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install Python dependencies**
   ```bash
   uv sync
   ```

3. **Set up environment variables**

   Create a `.env` file in the root directory:
   ```bash
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

## Running the Application

### Quick Start

Use the provided shell script:
```bash
chmod +x run.sh
./run.sh
```

### Manual Start

```bash
cd backend
uv run uvicorn app:app --reload --port 8000
```

The application will be available at:
- Web Interface: `http://localhost:8000`
- API Documentation: `http://localhost:8000/docs`

## Testing

The project includes end-to-end UI tests using Playwright. Tests mock all backend API calls via route interception, so no API key or running backend is required.

### Setup

```bash
# Install test dependencies
uv sync --extra test

# Install Playwright browsers (one-time)
uv run playwright install chromium
```

### Running Tests

```bash
# Run all UI tests
uv run pytest tests/test_ui.py -v

# Run a specific test
uv run pytest tests/test_ui.py::test_send_message -v

# Run with a visible browser for debugging
uv run pytest tests/test_ui.py -v --headed

# Run with slow motion for visual debugging
uv run pytest tests/test_ui.py -v --headed --slowmo 500
```

### Test Coverage

| Test | What it verifies |
|------|-----------------|
| `test_page_loads` | Page title, input, send button, and welcome message render |
| `test_course_stats_load` | Sidebar displays course count and titles |
| `test_send_message` | User and assistant messages appear in chat |
| `test_loading_state` | Loading spinner and disabled input while waiting |
| `test_suggested_questions` | Clicking a suggestion sends the query |
| `test_sources_displayed` | Sources shown in collapsible after response |
| `test_error_handling` | Error message displayed on API failure |
| `test_enter_key_sends` | Enter key triggers message send |
| `test_empty_input_no_send` | Empty input does nothing |
| `test_session_id_persistence` | Session ID carried across requests |
