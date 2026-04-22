"""Parse Claude Code session JSONL files into typed records.

Reads raw JSONL lines from Claude session transcripts and converts them
into structured ParsedMessage or CompactBoundary objects. All parsing
functions are designed to be fault-tolerant: they never raise exceptions
on malformed or unexpected input.
"""

import json
import re
from typing import Iterator

from search_chat.types import CompactBoundary, ParsedMessage


_SLASH_NAME_RE = re.compile(r"<command-name>([^<]*)</command-name>", re.IGNORECASE)
_SLASH_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.IGNORECASE | re.DOTALL)


def _collapse_slash_command(text: str) -> str | None:
    """If text is a Claude Code slash-command user message, collapse to a single
    informational line. Returns None if the text is not a slash-command invocation.

    Slash-command user messages from Claude Code wrap the invocation in
    <command-message>, <command-name>, and <command-args> tags followed by the
    skill's full prompt text. That prompt text is noise when re-read from an
    archive — it's not user-authored, and re-injecting it pollutes context and
    creates a prompt-injection surface. Keep only what the user actually typed.
    """
    stripped = text.lstrip()
    if not stripped.startswith("<command-"):
        return None
    name_match = _SLASH_NAME_RE.search(stripped)
    if not name_match:
        return None
    name = name_match.group(1).strip()
    args_match = _SLASH_ARGS_RE.search(stripped)
    args = args_match.group(1).strip() if args_match else ""
    if args:
        return f"[SLASH-COMMAND: {name} args={args}]"
    return f"[SLASH-COMMAND: {name}]"


def content_to_text(content) -> str:
    """Convert a message content field to a plain text string.

    Handles string content, lists of typed blocks (text/tool_use),
    None, and any other type via a fallback str() truncation.

    Slash-command user messages are collapsed to a single marker line —
    the expanded skill prompt is not user-authored content.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        collapsed = _collapse_slash_command(content)
        return collapsed if collapsed is not None else content
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
        joined = "\n".join(parts)
        collapsed = _collapse_slash_command(joined)
        return collapsed if collapsed is not None else joined
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
