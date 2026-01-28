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
/search-chat "API integration" --context
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

## Tip: Add to your CLAUDE.md

Adding a line to your project's `CLAUDE.md` makes Claude automatically reach for `/search-chat` when you casually reference something from a previous session. Without it, Claude won't know the plugin exists.

```markdown
## Chat History

When I reference a previous conversation, earlier discussion, or ask to continue/revisit a topic from another session, use `/search-chat` to find it.
```

That's it. Now you can say things like *"that staging bug from the other day"* or *"the auth issue we brainstormed about"* and Claude will search your chat history instead of asking you to explain from scratch.

### Leveraging the Max 20x plan

If you're on a Claude Max plan with 20x usage, you can add a few extra lines to your `CLAUDE.md` to unlock a more powerful workflow. Instead of spending your own time maintaining context documents, Claude will send out an opus subagent per chat match to search through old session logs and summarize the gist of each one. It's token-heavy — but on an unlimited plan you can afford to be lavish with Claude's budget instead of your own time. You can just tell Claude *"that issue related to album recovery, I want to brainstorm some more about it"* and it'll dig through your history, summarize what happened, and pick up where you left off.

Add these lines to the Chat History section in your `CLAUDE.md`:

```markdown
When I want to brainstorm or continue a previous discussion, go beyond basic search:

1. Run `/search-chat "<topic>" --extract-matches --extract-limit 5` to find and extract relevant sessions
2. For each extracted session, spawn an opus subagent (Task tool, model: opus) to summarize:
   - What was discussed and decided
   - What was left unresolved
   - Key code changes or commands run
3. Synthesize all summaries into a brief overview before continuing the conversation

Previous chats ARE the documentation — no need to maintain separate notes.
```

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
