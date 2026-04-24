"""
Tests for AIGenerator in ai_generator.py.

Covers: direct (non-tool) responses, the two-turn tool-use loop,
message construction for the second API call, and system prompt handling.

Key question answered: does the generator correctly detect tool use,
call the tool manager, and pass the result back to Claude?
"""

import pytest
from unittest.mock import MagicMock, patch
from ai_generator import AIGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def generator():
    with patch("ai_generator.anthropic.Anthropic"):
        gen = AIGenerator(api_key="test-key", model="claude-test-model")
    return gen


@pytest.fixture
def tool_manager():
    mgr = MagicMock()
    mgr.execute_tool.return_value = "Relevant course content from ChromaDB."
    return mgr


# ---------------------------------------------------------------------------
# Helpers to build mock Anthropic responses
# ---------------------------------------------------------------------------

def _text_response(text, stop_reason="end_turn"):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = [block]
    return resp


def _tool_use_response(name, inputs, tool_id="tool_001"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.id = tool_id
    block.input = inputs
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


# ---------------------------------------------------------------------------
# 1. Direct (no-tool) response path
# ---------------------------------------------------------------------------

class TestDirectResponse:

    def test_returns_text_directly_when_stop_reason_is_end_turn(self, generator):
        generator.client.messages.create.return_value = _text_response("Direct answer.")
        result = generator.generate_response(query="Hello")
        assert result == "Direct answer."

    def test_only_one_api_call_made_when_no_tool_use(self, generator):
        generator.client.messages.create.return_value = _text_response("Answer.")
        generator.generate_response(query="Hello")
        assert generator.client.messages.create.call_count == 1

    def test_query_appears_in_user_message(self, generator):
        generator.client.messages.create.return_value = _text_response("ok")
        generator.generate_response(query="What is Python?")
        call_kwargs = generator.client.messages.create.call_args[1]
        messages = call_kwargs["messages"]
        user_message = next(m for m in messages if m["role"] == "user")
        assert "What is Python?" in user_message["content"]

    def test_system_prompt_is_sent_with_every_request(self, generator):
        generator.client.messages.create.return_value = _text_response("ok")
        generator.generate_response(query="test")
        call_kwargs = generator.client.messages.create.call_args[1]
        assert "system" in call_kwargs
        assert len(call_kwargs["system"]) > 0

    def test_conversation_history_prepended_to_system_prompt(self, generator):
        generator.client.messages.create.return_value = _text_response("ok")
        generator.generate_response(
            query="follow-up",
            conversation_history="User: hi\nAssistant: hello"
        )
        call_kwargs = generator.client.messages.create.call_args[1]
        assert "hi" in call_kwargs["system"]
        assert "hello" in call_kwargs["system"]

    def test_no_tools_key_in_params_when_tools_not_provided(self, generator):
        generator.client.messages.create.return_value = _text_response("ok")
        generator.generate_response(query="general question")
        call_kwargs = generator.client.messages.create.call_args[1]
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    def test_tools_and_tool_choice_set_when_tools_provided(self, generator, tool_manager):
        generator.client.messages.create.return_value = _text_response("ok")
        tools = [{"name": "search_course_content"}]
        generator.generate_response(query="test", tools=tools, tool_manager=tool_manager)
        call_kwargs = generator.client.messages.create.call_args[1]
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == {"type": "auto"}


# ---------------------------------------------------------------------------
# 2. Two-turn tool-use loop
# ---------------------------------------------------------------------------

class TestToolUseLoop:

    def test_two_api_calls_made_when_tool_use_occurs(self, generator, tool_manager):
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "python"}),
            _text_response("Python is a language."),
        ]
        generator.generate_response(
            query="what is python",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        assert generator.client.messages.create.call_count == 2

    def test_execute_tool_called_with_correct_name_and_args(self, generator, tool_manager):
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "python", "course_name": "ML"}),
            _text_response("Answer."),
        ]
        generator.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="python", course_name="ML"
        )

    def test_final_answer_returned_after_tool_use(self, generator, tool_manager):
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "python"}),
            _text_response("Final synthesized answer."),
        ]
        result = generator.generate_response(
            query="what is python",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        assert result == "Final synthesized answer."

    def test_second_api_call_has_no_tools_parameter(self, generator, tool_manager):
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "test"}),
            _text_response("Answer."),
        ]
        generator.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        second_call_kwargs = generator.client.messages.create.call_args_list[1][1]
        assert "tools" not in second_call_kwargs
        assert "tool_choice" not in second_call_kwargs

    def test_second_api_call_includes_assistant_tool_use_message(self, generator, tool_manager):
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "test"}),
            _text_response("Answer."),
        ]
        generator.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        second_call_kwargs = generator.client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]
        assistant_messages = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_messages) == 1

    def test_tool_result_included_in_second_api_call(self, generator, tool_manager):
        tool_manager.execute_tool.return_value = "the search results text"
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "test"}, tool_id="tid_42"),
            _text_response("Answer."),
        ]
        generator.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        second_call_kwargs = generator.client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]

        # Find the user message that contains the tool result
        tool_result_message = next(
            (m for m in messages
             if m["role"] == "user"
             and isinstance(m.get("content"), list)
             and any(c.get("type") == "tool_result" for c in m["content"])),
            None,
        )
        assert tool_result_message is not None, (
            "No tool_result message found in second API call. "
            "The tool result was not passed back to Claude."
        )
        result_block = tool_result_message["content"][0]
        assert result_block["tool_use_id"] == "tid_42"
        assert result_block["content"] == "the search results text"

    def test_tool_result_message_has_correct_structure(self, generator, tool_manager):
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "x"}, tool_id="id_99"),
            _text_response("Answer."),
        ]
        generator.generate_response(
            query="x",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        second_kwargs = generator.client.messages.create.call_args_list[1][1]
        messages = second_kwargs["messages"]
        tool_msg = next(
            m for m in messages
            if m["role"] == "user" and isinstance(m.get("content"), list)
        )
        block = tool_msg["content"][0]
        assert block["type"] == "tool_result"
        assert "tool_use_id" in block
        assert "content" in block

    def test_system_prompt_preserved_in_second_api_call(self, generator, tool_manager):
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "test"}),
            _text_response("Answer."),
        ]
        generator.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        second_kwargs = generator.client.messages.create.call_args_list[1][1]
        assert "system" in second_kwargs
        assert len(second_kwargs["system"]) > 0


# ---------------------------------------------------------------------------
# 3. Exception propagation (the "query failed" diagnostic)
# ---------------------------------------------------------------------------

class TestExceptionPropagation:

    def test_api_exception_propagates_to_caller(self, generator, tool_manager):
        """
        If the Anthropic API raises (bad API key, invalid model, rate limit),
        generate_response must NOT swallow it. The exception must propagate
        so the caller (RAGSystem.query) can decide how to handle it.

        A swallowed exception here would mask the real error behind 'query failed'.
        """
        generator.client.messages.create.side_effect = Exception("Invalid API key")

        with pytest.raises(Exception, match="Invalid API key"):
            generator.generate_response(
                query="what is python",
                tools=[{"name": "search_course_content"}],
                tool_manager=tool_manager,
            )

    def test_api_exception_on_second_call_propagates(self, generator, tool_manager):
        """Second API call (after tool use) can also fail."""
        generator.client.messages.create.side_effect = [
            _tool_use_response("search_course_content", {"query": "test"}),
            Exception("Rate limit exceeded"),
        ]

        with pytest.raises(Exception, match="Rate limit exceeded"):
            generator.generate_response(
                query="test",
                tools=[{"name": "search_course_content"}],
                tool_manager=tool_manager,
            )
