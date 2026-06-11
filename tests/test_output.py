"""Tests for list output formatters."""
import json

from search_chat.output import format_session_list_json, format_session_list_text
from search_chat.types import SessionListItem

_ITEMS = [
    SessionListItem("aaaaaaaa-1111-2222-3333-444444444444",
                    "How do I deploy to staging?", "-tmp-testproject", 1_700_000_000.0),
    SessionListItem("bbbbbbbb-5555-6666-7777-888888888888",
                    "redis cache config", "-tmp-testproject", 1_700_000_500.0),
]


class TestFormatSessionListText:
    def test_lists_candidates(self):
        out = format_session_list_text(_ITEMS, "-tmp-testproject")
        assert "Candidate sessions" in out
        assert "[aaaaaaaa]" in out
        assert "How do I deploy to staging?" in out
        assert "aaaaaaaa-1111-2222-3333-444444444444" in out
        assert "/summarize-chat" in out and "/search-chat" in out

    def test_empty_gives_hint(self):
        out = format_session_list_text([], "-tmp-testproject")
        assert "No candidate sessions" in out
        assert "--all-projects" in out


class TestFormatSessionListJson:
    def test_valid_json_with_keys(self):
        data = json.loads(format_session_list_json(_ITEMS))
        assert len(data) == 2
        assert data[0]["session_id"] == "aaaaaaaa-1111-2222-3333-444444444444"
        assert data[0]["title"] == "How do I deploy to staging?"
        assert data[0]["project_dir"] == "-tmp-testproject"
        assert "timestamp" in data[0]

    def test_empty_list(self):
        assert json.loads(format_session_list_json([])) == []
