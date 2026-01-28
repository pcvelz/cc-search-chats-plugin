# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

cc-search-chats is a Claude Code plugin that provides the `/search-chat` command for searching and extracting chat history from previous Claude Code sessions.

## Structure

```
cc-search-chats-plugin/
├── .claude-plugin/
│   ├── plugin.json        # Plugin metadata
│   └── marketplace.json   # Marketplace configuration
├── commands/
│   ├── search-chat.md     # Command definition
│   └── search-chat.sh     # Implementation script
├── README.md              # User documentation
├── CLAUDE.md              # This file
└── LICENSE
```

## Key Files

| File | Purpose |
|------|---------|
| `.claude-plugin/plugin.json` | Plugin name, version, author |
| `.claude-plugin/marketplace.json` | Marketplace registration |
| `commands/search-chat.md` | Skill definition and instructions |
| `commands/search-chat.sh` | Bash + embedded Python implementation |

## Development

### Testing the Command

After installation, test with:
```bash
/search-chat "test query"
/search-chat --extract <session-id>
```

### Script Architecture

The `search-chat.sh` script:
1. Parses CLI arguments (bash)
2. Converts paths to Claude's directory format
3. Searches JSONL files using grep
4. Extracts content using embedded Python
5. Optionally pipes to llama.cpp analyzer

### Session Storage Format

Claude stores sessions in:
```
~/.claude/projects/-Users-peter-Documents-Code-project-name/
├── <session-uuid>.jsonl    # Session transcripts
└── agent-<uuid>.jsonl      # Agent transcripts (skipped)
```

### JSONL Message Structure

Each line contains:
```json
{
  "sessionId": "uuid",
  "cwd": "/path/to/project",
  "timestamp": "ISO-8601",
  "message": {
    "role": "user|assistant",
    "content": "..." | [{"type": "text", "text": "..."}]
  }
}
```

## Version Management

Bump version in both files when releasing:
1. `.claude-plugin/plugin.json` - `version` field
2. `.claude-plugin/marketplace.json` - plugin `version` field

## Git Commits

Use `/commit` skill for all commits.
