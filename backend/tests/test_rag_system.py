"""
Tests for RAGSystem.query() in rag_system.py.

Covers: orchestration of the full content-query pipeline — tool definitions
passed to the AI, sources retrieved and reset, exception propagation,
and session history handling.

All heavy I/O (VectorStore, AIGenerator, ChromaDB, Anthropic) is mocked
so these tests run without infrastructure.
"""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config():
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


@pytest.fixture
def rag(mock_config):
    """
    RAGSystem with all infrastructure dependencies mocked out.
    After construction, tool_manager is replaced with a controlled mock
    so individual tests can configure it.
    """
    with patch("rag_system.DocumentProcessor"), \
         patch("rag_system.VectorStore"), \
         patch("rag_system.AIGenerator"), \
         patch("rag_system.SessionManager"), \
         patch("rag_system.CourseSearchTool"), \
         patch("rag_system.CourseOutlineTool"), \
         patch("rag_system.ToolManager"):
        from rag_system import RAGSystem
        system = RAGSystem(mock_config)

    # Replace tool_manager with a fully controlled mock
    system.tool_manager = MagicMock()
    system.tool_manager.get_tool_definitions.return_value = [
        {"name": "search_course_content"},
        {"name": "get_course_outline"},
    ]
    system.tool_manager.get_last_sources.return_value = []

    # AI generator returns a sensible default
    system.ai_generator.generate_response.return_value = "Here is the answer."

    return system


# ---------------------------------------------------------------------------
# 1. Return value shape
# ---------------------------------------------------------------------------

class TestQueryReturnValue:

    def test_query_returns_a_tuple(self, rag):
        result = rag.query("what is python")
        assert isinstance(result, tuple)

    def test_query_returns_response_string_and_sources_list(self, rag):
        response, sources = rag.query("what is python")
        assert isinstance(response, str)
        assert isinstance(sources, list)

    def test_query_response_matches_ai_generator_output(self, rag):
        rag.ai_generator.generate_response.return_value = "Python is a language."
        response, _ = rag.query("what is python")
        assert response == "Python is a language."

    def test_query_sources_match_tool_manager_output(self, rag):
        rag.tool_manager.get_last_sources.return_value = ["Course A - Lesson 1"]
        _, sources = rag.query("content question")
        assert sources == ["Course A - Lesson 1"]

    def test_query_sources_empty_when_no_tool_was_called(self, rag):
        rag.tool_manager.get_last_sources.return_value = []
        _, sources = rag.query("general knowledge question")
        assert sources == []


# ---------------------------------------------------------------------------
# 2. Arguments forwarded to AIGenerator
# ---------------------------------------------------------------------------

class TestQueryAIGeneratorArgs:

    def test_both_tool_definitions_passed_to_ai_generator(self, rag):
        rag.query("content question")
        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        tools = call_kwargs.get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "search_course_content" in tool_names
        assert "get_course_outline" in tool_names

    def test_tool_manager_instance_passed_to_ai_generator(self, rag):
        rag.query("test")
        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        assert call_kwargs.get("tool_manager") is rag.tool_manager

    def test_query_text_appears_in_prompt_sent_to_ai(self, rag):
        rag.query("what is machine learning?")
        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        prompt = call_kwargs.get("query", "")
        assert "machine learning" in prompt

    def test_no_conversation_history_when_session_id_is_none(self, rag):
        rag.query("question without session")
        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        assert call_kwargs.get("conversation_history") is None

    def test_conversation_history_provided_when_session_has_history(self, rag):
        rag.session_manager.get_conversation_history.return_value = (
            "User: hello\nAssistant: hi"
        )
        rag.query("follow-up", session_id="session_1")
        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        history = call_kwargs.get("conversation_history")
        assert history is not None
        assert "hello" in history

    def test_no_history_sent_when_session_is_new_and_empty(self, rag):
        rag.session_manager.get_conversation_history.return_value = None
        rag.query("first question", session_id="session_new")
        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        assert call_kwargs.get("conversation_history") is None


# ---------------------------------------------------------------------------
# 3. Source lifecycle
# ---------------------------------------------------------------------------

class TestQuerySourceLifecycle:

    def test_sources_reset_after_every_query(self, rag):
        rag.query("question one")
        rag.tool_manager.reset_sources.assert_called()

    def test_sources_reset_called_exactly_once_per_query(self, rag):
        rag.query("question one")
        assert rag.tool_manager.reset_sources.call_count == 1

    def test_get_last_sources_called_before_reset(self, rag):
        """Sources must be read before being cleared."""
        call_order = []
        rag.tool_manager.get_last_sources.side_effect = lambda: call_order.append("get")
        rag.tool_manager.reset_sources.side_effect = lambda: call_order.append("reset")

        rag.query("test")

        assert call_order.index("get") < call_order.index("reset"), (
            "reset_sources() was called before get_last_sources(). "
            "Sources are cleared before they can be returned."
        )


# ---------------------------------------------------------------------------
# 4. Exception propagation — the root cause of "query failed" (HTTP 500)
# ---------------------------------------------------------------------------

class TestQueryExceptionPropagation:

    def test_ai_generator_exception_propagates_to_caller(self, rag):
        """
        Any exception from AIGenerator.generate_response() must NOT be swallowed.
        The FastAPI handler in app.py catches it and turns it into a 500 response,
        which the frontend displays as 'query failed'.

        This test confirms the exception path is intact.  If it PASSES, the
        exception propagates correctly and the 500 is expected behaviour for
        infrastructure failures (bad API key, wrong model name, etc.).
        """
        rag.ai_generator.generate_response.side_effect = Exception(
            "anthropic.AuthenticationError: invalid API key"
        )
        with pytest.raises(Exception, match="invalid API key"):
            rag.query("what is python?")

    def test_tool_manager_exception_propagates_to_caller(self, rag):
        rag.tool_manager.get_tool_definitions.side_effect = Exception(
            "ToolManager internal error"
        )
        with pytest.raises(Exception, match="ToolManager internal error"):
            rag.query("test")


# ---------------------------------------------------------------------------
# 5. Session management side-effects
# ---------------------------------------------------------------------------

class TestQuerySessionSideEffects:

    def test_exchange_saved_when_session_id_provided(self, rag):
        rag.ai_generator.generate_response.return_value = "The answer."
        rag.query("the question", session_id="session_5")
        rag.session_manager.add_exchange.assert_called_once()

    def test_exchange_not_saved_when_no_session_id(self, rag):
        rag.query("question without session")
        rag.session_manager.add_exchange.assert_not_called()
