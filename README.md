# CC Search Chats

A Claude Code plugin for searching and extracting chat history from previous sessions.

## Features

- **Session Search**: Find sessions by keywords with match counting
- **Content Extraction**: Extract full conversation content from session IDs
- **Auto-Extract**: Automatically extract top matching sessions
- **Cross-Project Search**: Search across different project histories
- **Local LLM Analysis**: Pipe extracted content to llama.cpp for analysis
- **Session Deletion**: Remove specific sessions from history

## Installation

### Via Marketplace (Recommended)

```bash
/plugin marketplace add pcvelz/cc-search-chats-plugin
/plugin install search-chats@cc-search-chats-marketplace
```

### Via Direct URL

```bash
/plugin install --source url https://github.com/pcvelz/cc-search-chats-plugin.git
```

## Usage

### Basic Search

```bash
/search-chat "keyword"
/search-chat "API integration" --limit 5
```

### Extract Session

```bash
/search-chat <session-uuid>              # auto-detects UUID, extracts full session
/search-chat bbfba5e4                    # partial UUID (first 8 chars) — resolves automatically
/search-chat bbfba5e4-c5e7-4464-af03    # truncated UUID — also resolved via prefix match
/search-chat bbfba5e4 chrome errors      # UUID + filter — extract session, show matching lines only
/search-chat bbfba5e4 error --context 3  # UUID + filter with 3 messages of context
/search-chat bbfba5e4 --tail 50          # last 50 lines of session
/search-chat --extract <session-id>      # explicit extract (same result)
/search-chat "staging" --extract-matches
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--limit N` | Maximum sessions to return | 10 |
| `--project PATH` | Search in specific project | current |
| `--extract ID` | Extract specific session | - |
| `--extract-matches` | Auto-extract top matches | false |
| `--extract-limit N` | Number to extract | 5 |
| `--max-lines N` | Max lines per extraction | 500 |
| `--context N` | Messages of context around filter matches | 0 |
| `--tail N` | Show only last N lines of extraction | - |

## Release Notes

### [v1.2.1](https://github.com/pcvelz/cc-search-chats-plugin/releases/tag/v1.2.1) - Context, tail flags and tool-result access

- **`--context N` flag** — show N messages of context around filter matches when using UUID + filter. Matches are marked with `>>>` and context blocks separated by `---`
- **`--tail N` flag** — show only the last N lines of a session extraction (complements `--max-lines` which truncates from the front)
- **`--read-result` / `--list-results`** — access tool results stored in session directories for inspection
- **Unknown flag detection** — unknown options like `--bogus` now produce a warning and are ignored, instead of being silently added to the search query
- Removed stale README references to `--analyze` and `--delete` features that were never implemented

### v1.2.0 - Tool-result access modes

- **`--read-result`** — read a specific tool result file from a session directory
- **`--list-results`** — list all tool results stored in a session directory

### [v1.1.1](https://github.com/pcvelz/cc-search-chats-plugin/releases/tag/v1.1.1) - UUID + filter syntax

- UUID + filter syntax: `/search-chat bbfba5e4 chrome errors` extracts session and shows only matching lines
- UUID and filter text are automatically split (comma or space separated)

### [v1.1.0](https://github.com/pcvelz/cc-search-chats-plugin/releases/tag/v1.1.0) - Partial UUID matching

- Partial UUID matching for session extraction (e.g. `cea8f0ed` or `cea8f0ed-533e-493f-a832`)
- 4-level fallback resolution: exact local → exact global → prefix local → prefix global
- Ambiguity detection when partial IDs match multiple sessions

### [v1.0.8](https://github.com/pcvelz/cc-search-chats-plugin/releases/tag/v1.0.8) - Auto-detect UUID

- Auto-detect UUID: passing a session UUID as argument now auto-extracts that session (no `--extract` flag needed)

---

## Tip: Add to your CLAUDE.md

Adding a line to your project's `CLAUDE.md` makes Claude automatically reach for `/search-chat` when you casually reference something from a previous session. Without it, Claude won't know the plugin exists.

```markdown
## Chat History

When I reference a previous conversation, earlier discussion, or ask to continue/revisit a topic from another session, use `/search-chat` to find it.
```

That's it. Now you can say things like *"that staging bug from the other day"* or *"the auth issue we brainstormed about"* and Claude will search your chat history instead of asking you to explain from scratch.

## Requirements

- Claude Code CLI
- Python 3 (for JSONL parsing)
- Optional: llama.cpp server for analysis features

## How It Works

Chat sessions are stored in `~/.claude/projects/` as JSONL files. This plugin:
1. Converts project paths to Claude's directory format
2. Searches session files for keyword matches
3. Parses JSONL to extract conversation content
4. Optionally pipes content to local LLM for analysis

## Updating

```bash
/plugin update search-chats
```

## Uninstall

```bash
/plugin uninstall search-chats
```

## License

MIT
