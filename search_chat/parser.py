"""Parse Claude Code session JSONL files into typed records.

Reads raw JSONL lines from Claude session transcripts and converts them
into structured ParsedMessage or CompactBoundary objects. All parsing
functions are designed to be fault-tolerant: they never raise exceptions
on malformed or unexpected input.
"""

import json
from typing import Iterator

from search_chat.types import CompactBoundary, ParsedMessage


def content_to_text(content) -> str:
    """Convert a message content field to a plain text string.

    Handles string content, lists of typed blocks (text/tool_use),
    None, and any other type via a fallback str() truncation.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                text = item.get("text", "")
                if text:
                    parts.append(text)
            elif item_type == "tool_use":
                name = item.get("name", "")
                parts.append(f"[TOOL:{name}]")
        return "\n".join(parts)
    return str(content)[:500]


def parse_line(line: str) -> "ParsedMessage | CompactBoundary | None":
    """Parse a single JSONL line into a typed record, or return None.

    Returns None for blank lines, JSON parse failures, non-dict payloads,
    system records that are not compact boundaries, and message records
    with unrecognised roles. Never raises.
    """
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    record_type = data.get("type")

    if record_type == "system":
        if data.get("subtype") != "compact_boundary":
            return None
        metadata = data.get("compactMetadata") or {}
        trigger = metadata.get("trigger", "")
        try:
            token_count = int(metadata.get("preTokens", 0))
        except (TypeError, ValueError):
            token_count = 0
        return CompactBoundary(
            uuid=data.get("uuid", ""),
            timestamp=data.get("timestamp", ""),
            trigger_type=trigger,
            token_count_before=token_count,
        )

    message = data.get("message")
    if not isinstance(message, dict):
        return None

    role = message.get("role")
    if role not in ("user", "assistant"):
        return None

    return ParsedMessage(
        uuid=data.get("uuid", ""),
        role=role,
        content=content_to_text(message.get("content")),
        timestamp=data.get("timestamp", ""),
        parent_uuid=data.get("parentUuid"),
    )


def parse_session(file_path: str) -> Iterator["ParsedMessage | CompactBoundary"]:
    """Yield parsed records from a JSONL session file line by line.

    Skips blank lines and lines that parse_line cannot interpret.
    Returns an empty iterator if the file does not exist or cannot be opened.
    Uses errors='replace' so corrupt bytes never abort iteration.
    """
    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                result = parse_line(line)
                if result is not None:
                    yield result
    except (FileNotFoundError, OSError):
        return
