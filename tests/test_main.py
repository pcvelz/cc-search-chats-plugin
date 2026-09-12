"""Tests for the CLI orchestration in search_chat.__main__."""
import search_chat.finder as finder
from search_chat.__main__ import _handle_extract, _handle_search, _session_files_to_index
from search_chat.args import Args
from search_chat.database import close_db, index_session, open_db, prune_missing
from search_chat.finder import list_session_files


class TestGracePeriodSessions:
    """A session whose transcript is gone but still indexed must neither crash
    nor mislead: search flags it, extraction serves it from the index."""

    def _gone_session(self, tmp_project, tmp_db, monkeypatch):
        projects_base, project_dir = tmp_project
        monkeypatch.setattr(finder, 'CLAUDE_PROJECTS_BASE', projects_base)
        conn = open_db(tmp_db)
        files = list_session_files(project_dir)
        for sf in files:
            index_session(conn, sf)
        gone = 'aaaaaaaa-1111-2222-3333-444444444444'
        (project_dir / f'{gone}.jsonl').unlink()
        prune_missing(conn, list_session_files(project_dir), {project_dir.name}, now=1_800_000_000.0)
        return conn, project_dir, gone

    def test_search_flags_missing_transcript(self, tmp_project, tmp_db, monkeypatch, capsys):
        conn, project_dir, gone = self._gone_session(tmp_project, tmp_db, monkeypatch)
        _handle_search(Args(query='redis'), conn, project_dir, project_dir.name)
        out = capsys.readouterr().out
        assert gone in out
        assert 'Transcript deleted' in out
        assert f'claude --resume {gone}' not in out
        close_db(conn)

    def test_search_json_flags_missing_transcript(self, tmp_project, tmp_db, monkeypatch, capsys):
        import json
        conn, project_dir, gone = self._gone_session(tmp_project, tmp_db, monkeypatch)
        _handle_search(Args(query='redis', json=True), conn, project_dir, project_dir.name)
        items = json.loads(capsys.readouterr().out)
        flagged = [it for it in items if it['session_id'] == gone]
        assert flagged and flagged[0]['transcript_missing'] is True
        assert 'index_retained_until' in flagged[0]
        close_db(conn)

    def test_extract_serves_from_index(self, tmp_project, tmp_db, monkeypatch, capsys):
        conn, project_dir, gone = self._gone_session(tmp_project, tmp_db, monkeypatch)
        _handle_extract(Args(extract_session=gone[:8]), conn, project_dir, project_dir.name)
        captured = capsys.readouterr()
        assert 'serving from the search index' in captured.err
        assert f'SESSION: {gone}' in captured.out
        assert '[USER] How do I deploy to staging?' in captured.out
        close_db(conn)


class TestSessionFilesToIndex:
    def _second_project(self, tmp_project):
        projects_base, project_dir = tmp_project
        other = projects_base / '-tmp-otherproject'
        other.mkdir()
        (other / 'cccccccc-1111-2222-3333-444444444444.jsonl').write_text(
            (project_dir / 'aaaaaaaa-1111-2222-3333-444444444444.jsonl').read_text()
        )
        return other

    def test_default_scope_is_current_project(self, tmp_project, monkeypatch):
        projects_base, project_dir = tmp_project
        self._second_project(tmp_project)
        monkeypatch.setattr(finder, 'CLAUDE_PROJECTS_BASE', projects_base)
        files = _session_files_to_index(Args(query='redis'), project_dir)
        assert {f.project_dir for f in files} == {project_dir.name}

    def test_all_projects_search_indexes_every_project(self, tmp_project, monkeypatch):
        projects_base, project_dir = tmp_project
        other = self._second_project(tmp_project)
        monkeypatch.setattr(finder, 'CLAUDE_PROJECTS_BASE', projects_base)
        files = _session_files_to_index(Args(query='redis', all_projects=True), project_dir)
        assert {f.project_dir for f in files} == {project_dir.name, other.name}

    def test_extract_stays_project_scoped(self, tmp_project, monkeypatch):
        projects_base, project_dir = tmp_project
        self._second_project(tmp_project)
        monkeypatch.setattr(finder, 'CLAUDE_PROJECTS_BASE', projects_base)
        args = Args(extract_session='cccccccc', all_projects=True)
        files = _session_files_to_index(args, project_dir)
        assert {f.project_dir for f in files} == {project_dir.name}
