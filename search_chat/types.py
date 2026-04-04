"""Data types for search-chat. NamedTuples — immutable and lightweight."""
from typing import NamedTuple


class ParsedMessage(NamedTuple):
    """A parsed user or assistant message from a JSONL line."""
    uuid: str
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    parent_uuid: str | None = None


class CompactBoundary(NamedTuple):
    """A compression boundary event from a JSONL line."""
    uuid: str
    timestamp: str
    trigger_type: str  # 'auto' or 'manual'
    token_count_before: int


class SessionFile(NamedTuple):
    """Metadata about a session JSONL file on disk."""
    session_id: str
    file_path: str
    project_dir: str
    mtime: float
    size: int


class SearchHit(NamedTuple):
    """A session-level search result."""
    session_id: str
    match_count: int
    snippet: str
    timestamp: str
    score: float = 0.0
