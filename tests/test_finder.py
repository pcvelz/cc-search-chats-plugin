"""Tests for session file discovery and UUID resolution."""
import time
from pathlib import Path

from search_chat.finder import (
    encode_project_path,
    find_current_session,
    list_session_files,
    resolve_session_id,
)
from search_chat.types import SessionFile


class TestEncodeProjectPath:
    def test_basic_path(self):
        assert encode_project_path('/Users/peter/project') == '-Users-peter-project'

    def test_root(self):
        assert encode_project_path('/') == '-'

    def test_nested_path(self):
        assert encode_project_path('/home/user/code/my-app') == '-home-user-code-my-app'


class TestListSessionFiles:
    def test_finds_uuid_files(self, tmp_project):
        _, project_dir = tmp_project
        sessions = list_session_files(project_dir)
        assert len(sessions) == 2
        ids = {s.session_id for s in sessions}
        assert 'aaaaaaaa-1111-2222-3333-444444444444' in ids
        assert 'bbbbbbbb-5555-6666-7777-888888888888' in ids

    def test_sorted_by_mtime_descending(self, tmp_project):
        _, project_dir = tmp_project
        newer = project_dir / 'aaaaaaaa-1111-2222-3333-444444444444.jsonl'
        newer.touch()
        time.sleep(0.01)
        sessions = list_session_files(project_dir)
        assert sessions[0].session_id == 'aaaaaaaa-1111-2222-3333-444444444444'

    def test_skips_agent_files(self, tmp_project):
        _, project_dir = tmp_project
        (project_dir / 'agent-12345678-1234-1234-1234-123456789abc.jsonl').write_text('{}')
        sessions = list_session_files(project_dir)
        ids = {s.session_id for s in sessions}
        assert not any(i.startswith('agent-') for i in ids)

    def test_includes_agent_files_when_requested(self, tmp_project):
        _, project_dir = tmp_project
        (project_dir / 'agent-12345678-1234-1234-1234-123456789abc.jsonl').write_text('{}')
        sessions = list_session_files(project_dir, include_agents=True)
        assert len(sessions) == 3

    def test_nonexistent_directory(self, tmp_path):
        sessions = list_session_files(tmp_path / 'nonexistent')
        assert sessions == []

    def test_skips_non_uuid_files(self, tmp_project):
        _, project_dir = tmp_project
        (project_dir / 'notes.jsonl').write_text('{}')
        (project_dir / 'random.txt').write_text('hello')
        sessions = list_session_files(project_dir)
        assert len(sessions) == 2


class TestResolveSessionId:
    def test_exact_match(self, tmp_project):
        _, project_dir = tmp_project
        path, sid = resolve_session_id('aaaaaaaa-1111-2222-3333-444444444444', project_dir)
        assert path is not None
        assert sid == 'aaaaaaaa-1111-2222-3333-444444444444'

    def test_partial_match(self, tmp_project):
        _, project_dir = tmp_project
        path, sid = resolve_session_id('aaaaaaaa', project_dir)
        assert path is not None
        assert sid == 'aaaaaaaa-1111-2222-3333-444444444444'

    def test_not_found(self, tmp_project):
        _, project_dir = tmp_project
        path, error = resolve_session_id('cccccccc-9999-9999-9999-999999999999', project_dir)
        assert path is None
        assert 'not found' in error.lower()


class TestFindCurrentSession:
    def test_returns_newest(self, tmp_project):
        _, project_dir = tmp_project
        (project_dir / 'aaaaaaaa-1111-2222-3333-444444444444.jsonl').touch()
        time.sleep(0.01)
        current = find_current_session(project_dir)
        assert current == 'aaaaaaaa-1111-2222-3333-444444444444'

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / 'empty'
        empty.mkdir()
        assert find_current_session(empty) is None
