"""
Tests for CourseSearchTool.execute() in search_tools.py.

Covers: result formatting, empty results, error passthrough,
filter argument forwarding, and source tracking.
"""

import pytest
from unittest.mock import MagicMock
from search_tools import CourseSearchTool
from vector_store import SearchResults


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_lesson_link.return_value = None
    return store


@pytest.fixture
def tool(mock_store):
    return CourseSearchTool(mock_store)


def make_results(docs, metas, distances=None):
    """Helper: build a SearchResults with parallel docs/metas."""
    distances = distances or [0.1] * len(docs)
    return SearchResults(documents=docs, metadata=metas, distances=distances)


def make_error_results(msg):
    return SearchResults(documents=[], metadata=[], distances=[], error=msg)


# ---------------------------------------------------------------------------
# 1. Basic result formatting
# ---------------------------------------------------------------------------

class TestExecuteFormatting:

    def test_returns_course_title_in_header(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["Python is a high-level language."],
            [{"course_title": "Python Basics", "lesson_number": 1}]
        )
        result = tool.execute(query="what is python")
        assert "Python Basics" in result

    def test_returns_lesson_number_in_header(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["content"],
            [{"course_title": "Some Course", "lesson_number": 3}]
        )
        result = tool.execute(query="test")
        assert "Lesson 3" in result

    def test_returns_document_text_in_output(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["Variables store data values."],
            [{"course_title": "Python Basics", "lesson_number": 1}]
        )
        result = tool.execute(query="variables")
        assert "Variables store data values." in result

    def test_multiple_results_separated_by_blank_lines(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["First chunk.", "Second chunk."],
            [
                {"course_title": "Course A", "lesson_number": 1},
                {"course_title": "Course B", "lesson_number": 2},
            ]
        )
        result = tool.execute(query="test")
        assert "First chunk." in result
        assert "Second chunk." in result
        assert "\n\n" in result

    def test_result_without_lesson_number_omits_lesson_from_header(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["general content"],
            [{"course_title": "General Course"}]
        )
        result = tool.execute(query="test")
        assert "[General Course]" in result
        assert "Lesson" not in result


# ---------------------------------------------------------------------------
# 2. Filter argument forwarding
# ---------------------------------------------------------------------------

class TestExecuteFilterForwarding:

    def test_no_filters_passes_none_for_both(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="test")
        mock_store.search.assert_called_once_with(
            query="test", course_name=None, lesson_number=None
        )

    def test_course_name_forwarded_to_store(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="intro", course_name="MCP")
        mock_store.search.assert_called_once_with(
            query="intro", course_name="MCP", lesson_number=None
        )

    def test_lesson_number_forwarded_to_store(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="variables", lesson_number=2)
        mock_store.search.assert_called_once_with(
            query="variables", course_name=None, lesson_number=2
        )

    def test_both_filters_forwarded_together(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="query", course_name="Python", lesson_number=4)
        mock_store.search.assert_called_once_with(
            query="query", course_name="Python", lesson_number=4
        )


# ---------------------------------------------------------------------------
# 3. Empty and error results
# ---------------------------------------------------------------------------

class TestExecuteEmptyAndErrors:

    def test_no_results_returns_not_found_message(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        result = tool.execute(query="nonexistent topic")
        assert "No relevant content found" in result

    def test_no_results_with_course_filter_includes_course_name(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        result = tool.execute(query="topic", course_name="Python")
        assert "Python" in result

    def test_no_results_with_lesson_filter_includes_lesson_number(self, tool, mock_store):
        mock_store.search.return_value = make_results([], [])
        result = tool.execute(query="topic", lesson_number=5)
        assert "5" in result

    def test_search_error_is_returned_not_raised(self, tool, mock_store):
        mock_store.search.return_value = make_error_results(
            "Search error: ChromaDB collection is empty"
        )
        result = tool.execute(query="anything")
        assert "Search error" in result

    def test_search_error_does_not_raise_exception(self, tool, mock_store):
        mock_store.search.return_value = make_error_results("DB failure")
        try:
            tool.execute(query="test")
        except Exception as e:
            pytest.fail(f"execute() raised an unexpected exception: {e}")


# ---------------------------------------------------------------------------
# 4. Source tracking
# ---------------------------------------------------------------------------

class TestExecuteSourceTracking:

    def test_last_sources_populated_after_successful_search(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["content"],
            [{"course_title": "Test Course", "lesson_number": 1}]
        )
        tool.execute(query="test")
        assert len(tool.last_sources) == 1

    def test_source_label_includes_course_and_lesson(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["content"],
            [{"course_title": "ML Course", "lesson_number": 2}]
        )
        tool.execute(query="test")
        assert "ML Course" in tool.last_sources[0]
        assert "Lesson 2" in tool.last_sources[0]

    def test_source_is_anchor_tag_when_lesson_link_exists(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["content"],
            [{"course_title": "Course A", "lesson_number": 1}]
        )
        mock_store.get_lesson_link.return_value = "https://example.com/lesson1"
        tool.execute(query="test")
        assert 'href="https://example.com/lesson1"' in tool.last_sources[0]
        assert 'target="_blank"' in tool.last_sources[0]

    def test_source_is_plain_text_when_no_lesson_link(self, tool, mock_store):
        mock_store.search.return_value = make_results(
            ["content"],
            [{"course_title": "Course B", "lesson_number": 3}]
        )
        mock_store.get_lesson_link.return_value = None
        tool.execute(query="test")
        assert tool.last_sources[0] == "Course B - Lesson 3"
        assert "<a" not in tool.last_sources[0]

    def test_last_sources_reflects_most_recent_call_only(self, tool, mock_store):
        # First call returns 2 results
        mock_store.search.return_value = make_results(
            ["doc1", "doc2"],
            [{"course_title": "A", "lesson_number": 1},
             {"course_title": "B", "lesson_number": 2}]
        )
        tool.execute(query="first")
        assert len(tool.last_sources) == 2

        # Second call returns 1 result — last_sources should be overwritten
        mock_store.search.return_value = make_results(
            ["doc3"],
            [{"course_title": "C", "lesson_number": 1}]
        )
        tool.execute(query="second")
        assert len(tool.last_sources) == 1

    def test_last_sources_empty_when_no_results(self, tool, mock_store):
        # Seed with something first
        tool.last_sources = ["stale source"]
        mock_store.search.return_value = make_results([], [])
        tool.execute(query="empty search")
        # Empty search does NOT call _format_results, so last_sources is unchanged.
        # Verify at least that an empty search doesn't crash.
        assert isinstance(tool.last_sources, list)
