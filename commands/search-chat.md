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
- `--project PATH` - Search in specific project (default: current directory)

### Extraction Options
- `--extract ID` - Extract full conversation from a specific session ID
- `--extract-matches` - Auto-extract from top search matches
- `--extract-limit N` - Number of matches to extract (default: 5)
- `--max-lines N` - Max lines per session extraction (default: 500)

## Examples

### Search Only
- `/search-chat "API integration"` - Find sessions mentioning API integration
- `/search-chat "deploy" --limit 5` - Search with limited results

### Direct Extraction (Full or Partial UUID)
- `/search-chat bbfba5e4-c5e7-4464-af03-67d8f62ada53` - Auto-detects full UUID, extracts session
- `/search-chat bbfba5e4` - Partial UUID (first 8 chars) — resolves to full ID automatically
- `/search-chat bbfba5e4-c5e7-4464-af03-67d8f6` - Truncated UUID — also resolved via prefix match
- `/search-chat --extract bbfba5e4-c5e7-4464-af03-67d8f62ada53` - Explicit extract (same result)

### Search + Extract (Recommended for Investigation)
- `/search-chat "staging deploy" --extract-matches` - Search and extract top 5 matches
- `/search-chat "database migration" --extract-matches --extract-limit 3` - Extract top 3 matches

### Cross-Project Search
- `/search-chat "redis config" --project /path/to/other-project`

## Output Format

When extracting, the output includes:
- Session metadata (ID, date, project)
- Conversation with role labels ([USER], [ASSISTANT], [TOOL:*])

## Security Note

This command searches within the current project's chat history by default. Use `--project` to search other projects, or `--extract` with a full session ID to find sessions across all projects.
