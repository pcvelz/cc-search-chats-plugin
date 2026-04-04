"""Tests for JSONL parser."""
import json
import tempfile
from pathlib import Path

from search_chat.parser import content_to_text, parse_line, parse_session
from search_chat.types import CompactBoundary, ParsedMessage


class TestContentToText:
    def test_string_content(self):
        assert content_to_text("hello world") == "hello world"

    def test_list_with_text_items(self):
        content = [
            {"type": "text", "text": "First paragraph."},
            {"type": "text", "text": "Second paragraph."},
        ]
        assert content_to_text(content) == "First paragraph.\nSecond paragraph."

    def test_list_with_tool_use(self):
        content = [
            {"type": "text", "text": "Running command."},
            {"type": "tool_use", "name": "Bash", "id": "t1", "input": {}},
        ]
        result = content_to_text(content)
        assert "Running command." in result
        assert "[TOOL:Bash]" in result

    def test_empty_string(self):
        assert content_to_text("") == ""

    def test_none_content(self):
        assert content_to_text(None) == ""

    def test_empty_list(self):
        assert content_to_text([]) == ""

    def test_list_with_non_dict_items(self):
        assert content_to_text(["not a dict", 42]) == ""

    def test_truncates_unknown_type(self):
        result = content_to_text(12345)
        assert result == "12345"


class TestParseLine:
    def test_user_message(self):
        line = json.dumps({
            "type": "user", "uuid": "u1", "parentUuid": None,
            "timestamp": "2026-01-15T10:00:00Z",
            "message": {"role": "user", "content": "hello"},
        })
        result = parse_line(line)
        assert isinstance(result, ParsedMessage)
        assert result.uuid == "u1"
        assert result.role == "user"
        assert result.content == "hello"
        assert result.parent_uuid is None

    def test_assistant_message_with_list_content(self):
        line = json.dumps({
            "type": "assistant", "uuid": "a1", "parentUuid": "u1",
            "timestamp": "2026-01-15T10:00:05Z",
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": "Here is the answer."}]},
        })
        result = parse_line(line)
        assert isinstance(result, ParsedMessage)
        assert result.role == "assistant"
        assert result.content == "Here is the answer."
        assert result.parent_uuid == "u1"

    def test_compact_boundary(self):
        line = json.dumps({
            "type": "system", "subtype": "compact_boundary", "uuid": "cb1",
            "timestamp": "2026-01-15T11:00:00Z",
            "compactMetadata": {"trigger": "auto", "preTokens": 48000},
        })
        result = parse_line(line)
        assert isinstance(result, CompactBoundary)
        assert result.uuid == "cb1"
        assert result.trigger_type == "auto"
        assert result.token_count_before == 48000

    def test_malformed_json(self):
        assert parse_line("not json at all") is None

    def test_empty_line(self):
        assert parse_line("") is None

    def test_unknown_type(self):
        assert parse_line(json.dumps({"type": "progress", "uuid": "p1"})) is None

    def test_system_without_compact_boundary(self):
        assert parse_line(json.dumps({"type": "system", "subtype": "other", "uuid": "s1"})) is None

    def test_no_message_field(self):
        assert parse_line(json.dumps({"type": "user", "uuid": "u1", "timestamp": "T"})) is None

    def test_message_with_non_user_assistant_role(self):
        line = json.dumps({
            "type": "user", "uuid": "u1", "timestamp": "T",
            "message": {"role": "system", "content": "ignored"},
        })
        assert parse_line(line) is None

    def test_compact_boundary_non_numeric_pretokens(self):
        line = json.dumps({
            "type": "system", "subtype": "compact_boundary", "uuid": "cb2",
            "timestamp": "T", "compactMetadata": {"trigger": "manual", "preTokens": "many"},
        })
        result = parse_line(line)
        assert isinstance(result, CompactBoundary)
        assert result.token_count_before == 0

    def test_non_dict_json(self):
        assert parse_line(json.dumps([1, 2, 3])) is None
        assert parse_line(json.dumps("just a string")) is None

    def test_null_bytes_in_content(self):
        line = json.dumps({
            "type": "user", "uuid": "u1", "timestamp": "T",
            "message": {"role": "user", "content": "hello\x00world"},
        })
        result = parse_line(line)
        assert isinstance(result, ParsedMessage)
        assert "hello" in result.content


class TestParseSession:
    def test_sample_session(self, sample_session_path):
        records = list(parse_session(sample_session_path))
        assert len(records) == 4
        assert all(isinstance(r, ParsedMessage) for r in records)
        assert records[0].role == "user"
        assert records[1].role == "assistant"

    def test_compressed_session(self, compressed_session_path):
        records = list(parse_session(compressed_session_path))
        messages = [r for r in records if isinstance(r, ParsedMessage)]
        boundaries = [r for r in records if isinstance(r, CompactBoundary)]
        assert len(messages) == 4
        assert len(boundaries) == 1
        assert boundaries[0].trigger_type == "auto"

    def test_nonexistent_file(self):
        records = list(parse_session("/nonexistent/file.jsonl"))
        assert records == []

    def test_generator_does_not_accumulate(self, sample_session_path):
        gen = parse_session(sample_session_path)
        assert hasattr(gen, '__next__')
