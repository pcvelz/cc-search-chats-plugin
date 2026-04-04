"""Shared test fixtures for cc-search-chats."""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_DIR = Path(__file__).parent / 'fixtures'


@pytest.fixture
def sample_session_path():
    """Path to sample_session.jsonl fixture."""
    return str(FIXTURES_DIR / 'sample_session.jsonl')


@pytest.fixture
def compressed_session_path():
    """Path to compressed_session.jsonl fixture."""
    return str(FIXTURES_DIR / 'compressed_session.jsonl')


@pytest.fixture
def tmp_db(tmp_path):
    """Temporary SQLite database path for test isolation."""
    return tmp_path / 'test-index.db'


@pytest.fixture
def tmp_project(tmp_path):
    """Temporary project directory structure mimicking Claude's layout.

    Creates:
      tmp_path/projects/-tmp-testproject/
        aaaaaaaa-1111-2222-3333-444444444444.jsonl  (copy of sample_session)
        bbbbbbbb-5555-6666-7777-888888888888.jsonl  (copy of compressed_session)
    """
    projects_base = tmp_path / 'projects'
    project_dir = projects_base / '-tmp-testproject'
    project_dir.mkdir(parents=True)

    shutil.copy(
        FIXTURES_DIR / 'sample_session.jsonl',
        project_dir / 'aaaaaaaa-1111-2222-3333-444444444444.jsonl',
    )
    shutil.copy(
        FIXTURES_DIR / 'compressed_session.jsonl',
        project_dir / 'bbbbbbbb-5555-6666-7777-888888888888.jsonl',
    )

    return projects_base, project_dir
