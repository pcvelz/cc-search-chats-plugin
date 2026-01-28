---
description: "Search previous sessions, chat history, last session, earlier conversation, before I made, what we discussed, find where we talked about, previous chat, old session, yesterday's session"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/commands/search-chat.sh:*)"]
---

# Search Chat History

Search through previous Claude Code chat sessions and extract conversation content.

**Arguments provided:** $ARGUMENTS

## CRITICAL: This Skill is Script-Only

**The bash script does ALL the work. You must NOT:**
- Run additional `grep`, `ls`, `head`, or `cat` commands on `~/.claude/projects/`
- Spawn Task agents to do additional searching
- Do your own investigation of chat history files

**You must ONLY:**
1. Run the script below
2. Present its output to the user
3. Stop

## Exact Command to Run

```bash
bash ${CLAUDE_PLUGIN_ROOT}/commands/search-chat.sh $ARGUMENTS
```

## Instructions

1. If no arguments provided, ask the user what they want to search for.

2. Run the EXACT command shown above with the user's query.

3. Present the script's output directly to the user. Do NOT run additional bash commands.

4. If the user wants more details, suggest they run with `--extract-matches` or `--extract <session-id>`.

## Available Options

### Search Options
- `--limit N` - Maximum sessions to return (default: 10)
- `--context` - Show matching text snippets
- `--project PATH` - Search in specific project (default: current directory)

### Extraction Options
- `--extract ID` - Extract full conversation from a specific session ID
- `--extract-matches` - Auto-extract from top search matches
- `--extract-limit N` - Number of matches to extract (default: 5)
- `--max-lines N` - Max lines per session extraction (default: 500)

### Analysis Options (Local LLM via llama.cpp)

Requires llama-server running at localhost:8080. See `skills/local-llm-integration.md`.

- `--analyze "prompt"` - Analyze extracted content locally via llama.cpp
- `--analyze summarize` - Use pre-defined "summarize" prompt template
- `--analyze commands` - Extract all commands mentioned
- `--analyze files` - List all file paths discussed
- `--analyze errors` - Identify errors and root causes
- `--analyze ssh` - Extract SSH connection details

Environment variables:
- `LLAMACPP_URL` - Server URL (default: http://localhost:8080)
- `LLAMACPP_MODEL` - Model name (default: default)
- `MAX_TOKENS` - Max response tokens (default: 500)

## Examples

### Search Only
- `/search-chat PayNL` - Find sessions mentioning PayNL
- `/search-chat "exchange URL" --context` - Search with context snippets

### Direct Extraction
- `/search-chat --extract bbfba5e4-c5e7-4464-af03-67d8f62ada53` - Extract specific session

### Search + Extract (Recommended for Investigation)
- `/search-chat "staging hypernode" --extract-matches` - Search and extract top 5 matches
- `/search-chat "ssh protest" --extract-matches --extract-limit 3` - Extract top 3 matches

### Cross-Project Search
- `/search-chat "redis config" --project /Users/peter/Documents/Code/other-project`

## Output Format

When extracting, the output includes:
- Session metadata (ID, date, project)
- Conversation with role labels ([USER], [ASSISTANT], [TOOL:*])
- Extracted commands (SSH, rsync, git, etc.)
- Extracted paths (/data/web/*, ~/.*, etc.)

## SSH Commands

If searching for commands run on external servers, also check `.claude/logs/ssh-commands.log` which logs all SSH commands with timestamps, session IDs, and server aliases.

## Security Note

This command searches within the current project's chat history by default. Use `--project` to search other projects, or `--extract` with a full session ID to find sessions across all projects.
