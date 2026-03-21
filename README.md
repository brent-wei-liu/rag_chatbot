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
| **Tooling** | Python | 3.13+ |
| | uv | Package manager |
| | python-dotenv | 1.1.1 |
| | python-multipart | 0.0.20 |

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
