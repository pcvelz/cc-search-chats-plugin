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
/search-chat "PayNL integration" --context
```

### Extract Session

```bash
/search-chat --extract <session-id>
/search-chat "staging" --extract-matches
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--limit N` | Maximum sessions to return | 10 |
| `--context` | Show matching text snippets | false |
| `--project PATH` | Search in specific project | current |
| `--extract ID` | Extract specific session | - |
| `--extract-matches` | Auto-extract top matches | false |
| `--extract-limit N` | Number to extract | 5 |
| `--max-lines N` | Max lines per extraction | 500 |
| `--analyze "prompt"` | Analyze via llama.cpp | - |
| `--delete ID` | Delete session (destructive) | - |

### Analysis Templates

When using `--analyze`, these templates are available:
- `summarize` - Summarize key points
- `commands` - Extract all commands mentioned
- `files` - List all file paths discussed
- `errors` - Identify errors and root causes
- `ssh` - Extract SSH connection details

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
