# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Always use `uv` to run Python files and manage dependencies.

**Install dependencies:**
```bash
uv sync
```

**Add a dependency:**
```bash
uv add <package>
```

**Run a Python file:**
```bash
uv run python <file.py>
```

**Run the server:**
```bash
./run.sh
# or manually:
cd backend && uv run uvicorn app:app --reload --port 8000
```

The app is served at `http://localhost:8000` (UI) and `http://localhost:8000/docs` (API docs). The server must be run from the `backend/` directory because paths like `../docs` and `./chroma_db` are relative to it.

There are no tests or linting configured.

## Architecture

This is a full-stack RAG chatbot: a FastAPI backend serving both the API and the static frontend, with ChromaDB for vector storage and Claude (Anthropic) as the LLM.

### Request flow
1. Frontend (`frontend/script.js`) POSTs to `/api/query` with `{query, session_id}`
2. `app.py` delegates to `RAGSystem.query()`
3. `RAGSystem` passes the query + conversation history to `AIGenerator`
4. **Turn 1**: Claude decides whether to call the `search_course_content` tool (Anthropic tool use, `tool_choice: auto`)
5. If tool use: `CourseSearchTool` → `VectorStore.search()` → ChromaDB semantic search → formatted results returned to Claude
6. **Turn 2**: Claude synthesizes a final answer from the retrieved chunks
7. Response + sources + session_id returned to the frontend

### Key design decisions

- **Tool-based retrieval**: Claude autonomously decides when to search via Anthropic tool use. The tool (`search_course_content`) supports filtering by `course_name` (resolved via semantic search on `course_catalog`) and `lesson_number`.
- **Two ChromaDB collections**: `course_catalog` stores course-level metadata (title, instructor, links, lessons as serialized JSON); `course_content` stores chunked lesson text for semantic search.
- **Embeddings**: `all-MiniLM-L6-v2` via SentenceTransformers, run locally.
- **Session state**: In-memory only (`SessionManager`), keyed by `session_N` strings. Keeps last 2 exchanges (4 messages). Lost on server restart.
- **Deduplication on startup**: `add_course_folder()` checks existing course titles in ChromaDB before ingesting, so restarts don't re-embed documents.

### Document format
Course files in `docs/` must follow this structure:
```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 0: <lesson title>
Lesson Link: <url>
<lesson content>

Lesson 1: <lesson title>
...
```
`DocumentProcessor` parses this format, chunks lesson content at 800 chars with 100-char sentence-level overlap, and prepends lesson/course context to each chunk before storing.

### Component responsibilities
| File | Responsibility |
|---|---|
| `backend/app.py` | FastAPI routes, startup document loading, static file serving |
| `backend/rag_system.py` | Orchestrates the full RAG pipeline |
| `backend/ai_generator.py` | Anthropic API calls, two-turn tool-use loop |
| `backend/vector_store.py` | ChromaDB read/write, course name resolution |
| `backend/document_processor.py` | File parsing, sentence-based chunking |
| `backend/search_tools.py` | Tool definitions and `ToolManager` registry |
| `backend/session_manager.py` | In-memory conversation history |
| `backend/models.py` | Pydantic models: `Course`, `Lesson`, `CourseChunk` |
| `backend/config.py` | Config dataclass loaded from `.env` |
