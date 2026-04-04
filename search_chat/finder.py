"""Session file discovery and UUID resolution.

Finds JSONL session files on disk, converts project paths to Claude's
encoded format, resolves partial UUIDs, and auto-detects current session.
"""
import os
import re
from pathlib import Path

from search_chat.types import SessionFile

UUID_PATTERN = re.compile(
    r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
)

CLAUDE_PROJECTS_BASE = Path(
    os.environ.get('CLAUDE_PROJECTS_BASE', str(Path.home() / '.claude' / 'projects'))
)


def encode_project_path(path: str) -> str:
    """Convert a filesystem path to Claude's encoded directory name.
    Replaces every '/' with '-'.
    """
    return path.replace('/', '-')


def get_project_dir(project_path: str) -> Path:
    """Get the Claude projects directory for a given project path."""
    return CLAUDE_PROJECTS_BASE / encode_project_path(project_path)


def list_session_files(
    project_dir: Path,
    include_agents: bool = False,
) -> list[SessionFile]:
    """List all session JSONL files in a project directory.
    Returns SessionFile objects sorted by mtime descending (newest first).
    Skips agent-* files unless include_agents is True.
    """
    if not project_dir.is_dir():
        return []

    encoded = project_dir.name
    results = []

    for f in project_dir.iterdir():
        if not f.is_file() or f.suffix != '.jsonl':
            continue
        name = f.stem
        if name.startswith('agent-') and not include_agents:
            continue
        if not include_agents and not UUID_PATTERN.match(name):
            continue

        stat = f.stat()
        results.append(SessionFile(
            session_id=name,
            file_path=str(f),
            project_dir=encoded,
            mtime=stat.st_mtime,
            size=stat.st_size,
        ))

    results.sort(key=lambda s: s.mtime, reverse=True)
    return results


def find_current_session(project_dir: Path) -> str | None:
    """Auto-detect the current session (most recently modified JSONL)."""
    sessions = list_session_files(project_dir)
    return sessions[0].session_id if sessions else None


def resolve_session_id(
    session_id: str,
    project_dir: Path,
) -> tuple[str | None, str]:
    """Resolve a full or partial session ID to a file path.
    Returns (file_path, resolved_session_id) on success.
    Returns (None, error_message) on failure.
    """
    exact = project_dir / f'{session_id}.jsonl'
    if exact.is_file():
        return str(exact), session_id

    if project_dir.is_dir():
        matches = []
        for f in project_dir.iterdir():
            if (f.is_file() and f.suffix == '.jsonl'
                    and f.stem.startswith(session_id)
                    and not f.stem.startswith('agent-')):
                matches.append(f)

        if len(matches) >= 1:
            return str(matches[0]), matches[0].stem

    if CLAUDE_PROJECTS_BASE.is_dir():
        for proj in CLAUDE_PROJECTS_BASE.iterdir():
            if not proj.is_dir():
                continue
            candidate = proj / f'{session_id}.jsonl'
            if candidate.is_file():
                return str(candidate), session_id
            for f in proj.iterdir():
                if (f.is_file() and f.suffix == '.jsonl'
                        and f.stem.startswith(session_id)
                        and not f.stem.startswith('agent-')):
                    return str(f), f.stem

    return None, f'Session not found: {session_id}'
