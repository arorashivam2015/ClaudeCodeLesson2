import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add backend/ to path so tests can import backend modules directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Shared configuration mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config():
    """Shared mock of the Config dataclass."""
    cfg = MagicMock()
    cfg.CHUNK_SIZE = 800
    cfg.CHUNK_OVERLAP = 100
    cfg.CHROMA_PATH = "/tmp/test_chroma"
    cfg.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    cfg.MAX_RESULTS = 5
    cfg.ANTHROPIC_API_KEY = "test-key"
    cfg.ANTHROPIC_MODEL = "claude-test-model"
    cfg.MAX_HISTORY = 2
    return cfg


# ---------------------------------------------------------------------------
# API test infrastructure
# ---------------------------------------------------------------------------

def _make_mock_rag():
    """Return a RAGSystem mock with sensible defaults."""
    rag = MagicMock()
    rag.query.return_value = ("Test answer.", [])
    rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Course A", "Course B"],
    }
    rag.session_manager.create_session.return_value = "session_1"
    rag.add_course_folder.return_value = (0, 0)
    return rag


@pytest.fixture(scope="session")
def _app_session():
    """
    Import app.py once per test session with infrastructure mocked:
      - RAGSystem → mock (no ChromaDB / Anthropic connections)
      - StaticFiles → mock (no frontend directory required)

    app.py has two module-level side-effects that would fail in the test
    environment: RAGSystem(config) connects to ChromaDB, and
    StaticFiles(directory="../frontend") raises RuntimeError when the
    frontend directory does not exist.  Both are patched before the fresh
    import so the module-level code runs cleanly under the patches.

    A single TestClient is kept alive for the whole session; individual
    tests reset mock state via the function-scoped `api_client` fixture.
    """
    from fastapi.testclient import TestClient

    mock_rag = _make_mock_rag()
    sys.modules.pop("app", None)  # force a fresh import under the patches

    with patch("rag_system.RAGSystem") as MockRAG, \
         patch("fastapi.staticfiles.StaticFiles") as MockStatic:
        MockRAG.return_value = mock_rag
        MockStatic.return_value = MagicMock()   # no-op ASGI placeholder

        import app as _app_module  # noqa: PLC0415

        # Override the module-level rag_system instance created at import time
        _app_module.rag_system = mock_rag

        with TestClient(_app_module.app, raise_server_exceptions=False) as session_client:
            yield session_client, mock_rag


@pytest.fixture
def api_client(_app_session):
    """
    Function-scoped fixture that yields (TestClient, mock_rag).

    Resets mock call counts and restores default return values / clears any
    side_effect set by previous tests so each test starts from a known state.
    """
    client, mock_rag = _app_session

    mock_rag.reset_mock()

    # Restore default return values (reset_mock() does not touch these)
    mock_rag.query.return_value = ("Test answer.", [])
    mock_rag.query.side_effect = None
    mock_rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Course A", "Course B"],
    }
    mock_rag.get_course_analytics.side_effect = None
    mock_rag.session_manager.create_session.return_value = "session_1"
    mock_rag.session_manager.create_session.side_effect = None
    mock_rag.add_course_folder.return_value = (0, 0)

    yield client, mock_rag
