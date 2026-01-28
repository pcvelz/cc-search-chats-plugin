#!/bin/bash
# search-chat.sh - Search through Claude Code chat history for the current project
# Usage: search-chat.sh <query> [--limit N] [--context] [--extract ID] [--extract-matches] [--project PATH]
#
# Features:
# - Search sessions by keywords
# - Extract full conversation content from session IDs
# - Auto-extract from search matches
# - Cross-project search support

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Default values
LIMIT=10
SHOW_CONTEXT=false
EXTRACT_SESSION=""
EXTRACT_MATCHES=false
EXTRACT_LIMIT=5
MAX_LINES=500
PROJECT_PATH=""
QUERY=""
ANALYZE_PROMPT=""
DELETE_SESSION=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --context)
            SHOW_CONTEXT=true
            shift
            ;;
        --extract)
            EXTRACT_SESSION="$2"
            shift 2
            ;;
        --extract-matches)
            EXTRACT_MATCHES=true
            shift
            ;;
        --extract-limit)
            EXTRACT_LIMIT="$2"
            shift 2
            ;;
        --max-lines)
            MAX_LINES="$2"
            shift 2
            ;;
        --project)
            PROJECT_PATH="$2"
            shift 2
            ;;
        --analyze)
            ANALYZE_PROMPT="$2"
            shift 2
            ;;
        --delete)
            DELETE_SESSION="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: search-chat.sh <query> [OPTIONS]"
            echo ""
            echo "Search through Claude Code chat history and extract conversations."
            echo ""
            echo "Search Options:"
            echo "  --limit N          Maximum sessions to return (default: 10)"
            echo "  --context          Show matching text snippets"
            echo "  --project PATH     Search in specific project (default: current directory)"
            echo ""
            echo "Extraction Options:"
            echo "  --extract ID       Extract conversation from specific session ID"
            echo "  --extract-matches  Auto-extract from top search matches"
            echo "  --extract-limit N  Number of matches to extract (default: 5)"
            echo "  --max-lines N      Max lines per session extraction (default: 500)"
            echo ""
            echo "Analysis Options:"
            echo "  --analyze 'prompt' Pipe extracted content to llama.cpp analyzer"
            echo "                     (requires --extract or --extract-matches)"
            echo ""
            echo "Deletion Options:"
            echo "  --delete ID        Delete a specific session file (DESTRUCTIVE)"
            echo ""
            echo "Examples:"
            echo "  search-chat.sh 'staging hypernode'              # Search only"
            echo "  search-chat.sh --extract abc12345-...           # Extract specific session"
            echo "  search-chat.sh 'ssh protest' --extract-matches  # Search + extract top 5"
            echo "  search-chat.sh 'redis' --project /path/to/proj  # Search other project"
            echo "  search-chat.sh --extract ID --analyze 'summarize key points'  # Extract + analyze"
            exit 0
            ;;
        *)
            if [[ -z "$QUERY" ]]; then
                QUERY="$1"
            else
                QUERY="$QUERY $1"
            fi
            shift
            ;;
    esac
done

# Validate: need either query, extract session, or delete session
if [[ -z "$QUERY" ]] && [[ -z "$EXTRACT_SESSION" ]] && [[ -z "$DELETE_SESSION" ]]; then
    echo -e "${RED}Error: No search query, session ID, or delete target provided${NC}"
    echo "Usage: search-chat.sh <query> [--extract ID] [--extract-matches] [--delete ID]"
    exit 1
fi

# Validate: --analyze requires extraction mode
if [[ -n "$ANALYZE_PROMPT" ]] && [[ -z "$EXTRACT_SESSION" ]] && [[ "$EXTRACT_MATCHES" != true ]]; then
    echo -e "${RED}Error: --analyze requires --extract or --extract-matches${NC}"
    exit 1
fi

# Create temp file for results
RESULTS_FILE=$(mktemp)
trap "rm -f $RESULTS_FILE" EXIT

# Determine project path
if [[ -n "$PROJECT_PATH" ]]; then
    TARGET_PATH="$PROJECT_PATH"
else
    TARGET_PATH=$(pwd)
fi

# Convert to Claude projects path format
CLAUDE_PROJECT_DIR=$(echo "$TARGET_PATH" | sed 's|^/|-|' | sed 's|/|-|g')
CLAUDE_PROJECTS_BASE="$HOME/.claude/projects"
PROJECT_HISTORY_DIR="$CLAUDE_PROJECTS_BASE/$CLAUDE_PROJECT_DIR"

# Function to find session file (searches all projects if not found locally)
find_session_file() {
    local session_id="$1"
    local session_file="$PROJECT_HISTORY_DIR/$session_id.jsonl"

    if [[ -f "$session_file" ]]; then
        echo "$session_file"
        return 0
    fi

    # Search all projects
    local found=$(find "$CLAUDE_PROJECTS_BASE" -name "$session_id.jsonl" -type f 2>/dev/null | head -1)
    if [[ -n "$found" ]]; then
        echo "$found"
        return 0
    fi

    return 1
}

# Function to extract conversation from session using Python
extract_session() {
    local session_file="$1"
    local max_lines="$2"
    local query="${3:-}"

    # Export variables to avoid shell injection in heredoc
    export SEARCH_SESSION_FILE="$session_file"
    export SEARCH_MAX_LINES="$max_lines"
    export SEARCH_QUERY="$query"

    python3 << 'PYTHON_SCRIPT'
import json
import sys
import re
import os
from datetime import datetime

session_file = os.environ.get('SEARCH_SESSION_FILE', '')
max_lines = int(os.environ.get('SEARCH_MAX_LINES', '500'))
query = os.environ.get('SEARCH_QUERY', '').lower() or None

def extract_text(content):
    """Extract readable text from message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    texts.append(item.get('text', ''))
                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'Unknown')
                    tool_input = item.get('input', {})
                    if tool_name == 'Bash':
                        cmd = tool_input.get('command', '')[:200]
                        texts.append(f"[TOOL:Bash] {cmd}")
                    elif tool_name == 'Task':
                        desc = tool_input.get('description', '')
                        agent = tool_input.get('subagent_type', '')
                        texts.append(f"[TOOL:Task] {desc} - subagent: {agent}")
                    elif tool_name in ('Read', 'Write', 'Edit'):
                        path = tool_input.get('file_path', '')
                        texts.append(f"[TOOL:{tool_name}] {path}")
                    else:
                        texts.append(f"[TOOL:{tool_name}]")
                elif item.get('type') == 'tool_result':
                    # Skip tool results for brevity
                    pass
        return '\n'.join(texts)
    return str(content)[:500]

# Parse session
messages = []
session_info = {}
commands_found = set()
paths_found = set()

try:
    with open(session_file, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)

                # Extract session metadata
                if 'sessionId' in data:
                    session_info['id'] = data['sessionId']
                if 'cwd' in data:
                    session_info['cwd'] = data['cwd']
                if 'timestamp' in data:
                    session_info['timestamp'] = data['timestamp']

                # Extract messages
                if 'message' in data:
                    msg = data['message']
                    role = msg.get('role', '').upper()
                    content = extract_text(msg.get('content', ''))

                    if role and content:
                        messages.append((role, content))

                        # Extract commands (ssh, rsync, git, etc.)
                        cmd_patterns = [
                            r'(?:^|\s)(/usr/bin/ssh\s+\S+.*?)(?:\n|$)',
                            r'(?:^|\s)(ssh\s+\S+.*?)(?:\n|$)',
                            r'(?:^|\s)(rsync\s+.*?)(?:\n|$)',
                            r'(?:^|\s)(scp\s+.*?)(?:\n|$)',
                            r'(?:^|\s)(git\s+\S+.*?)(?:\n|$)',
                        ]
                        for pattern in cmd_patterns:
                            for match in re.findall(pattern, content, re.MULTILINE):
                                commands_found.add(match.strip()[:150])

                        # Extract paths
                        path_pattern = r'(?:/data/web/\S+|~/\S+\.(?:sh|php|json|md|conf)|/Users/\S+\.(?:sh|php|json|md))'
                        for match in re.findall(path_pattern, content):
                            paths_found.add(match)

            except json.JSONDecodeError:
                continue
except Exception as e:
    print(f"Error reading session: {e}", file=sys.stderr)
    sys.exit(1)

# Output header
print("=" * 80)
print(f"SESSION: {session_info.get('id', 'unknown')}")
if session_info.get('timestamp'):
    try:
        ts = datetime.fromisoformat(session_info['timestamp'].replace('Z', '+00:00'))
        print(f"DATE: {ts.strftime('%Y-%m-%d %H:%M')}")
    except:
        pass
print(f"PROJECT: {session_info.get('cwd', 'unknown')}")
if query:
    print(f"FILTER: {query}")
print("=" * 80)
print()

# Output messages (limited)
line_count = 0
for role, content in messages:
    if max_lines > 0 and line_count >= max_lines:
        print(f"\n... (truncated at {max_lines} lines)")
        break

    # Filter by query if provided
    if query and query not in content.lower():
        continue

    lines = content.split('\n')
    for line in lines:
        if max_lines > 0 and line_count >= max_lines:
            break
        if line.strip():
            prefix = f"[{role}]" if role in ('USER', 'ASSISTANT') else ""
            if prefix:
                print(f"{prefix} {line[:200]}")
            else:
                print(f"  {line[:200]}")
            line_count += 1

# Output extracted commands
if commands_found:
    print()
    print("--- EXTRACTED COMMANDS ---")
    for cmd in sorted(commands_found)[:20]:
        print(cmd)

# Output extracted paths
if paths_found:
    print()
    print("--- EXTRACTED PATHS ---")
    for path in sorted(paths_found)[:20]:
        print(path)

print()
print("=" * 80)
PYTHON_SCRIPT
}

# Function to get session content from JSONL file (for search)
get_session_content() {
    local session_id="$1"
    local session_file=$(find_session_file "$session_id")

    if [[ -n "$session_file" ]] && [[ -f "$session_file" ]]; then
        cat "$session_file"
        return 0
    fi

    return 1
}

# ==============================================================================
# MODE 0: Delete session (--delete <session-id>)
# ==============================================================================
if [[ -n "$DELETE_SESSION" ]]; then
    echo -e "${RED}=== DELETE MODE ===${NC}"
    echo -e "${YELLOW}Session to delete: ${NC}$DELETE_SESSION"
    echo ""

    session_file=$(find_session_file "$DELETE_SESSION")
    if [[ -z "$session_file" ]]; then
        echo -e "${RED}Error: Session not found: $DELETE_SESSION${NC}"
        echo "Searched in: $PROJECT_HISTORY_DIR"
        echo "Also searched: $CLAUDE_PROJECTS_BASE"
        exit 1
    fi

    echo -e "${GREEN}Found: ${NC}$session_file"
    echo ""

    # Show preview of what will be deleted
    echo -e "${CYAN}Session preview (first 10 lines):${NC}"
    head -10 "$session_file" | python3 -c "
import json, sys
for line in sys.stdin:
    try:
        d = json.loads(line)
        if 'message' in d:
            role = d['message'].get('role', '?')
            content = d['message'].get('content', '')
            if isinstance(content, str):
                print(f'[{role}] {content[:100]}...')
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get('type') == 'text':
                        print(f'[{role}] {c.get(\"text\", \"\")[:100]}...')
                        break
    except:
        pass
"
    echo ""

    # Delete the file
    rm -f "$session_file"
    echo -e "${GREEN}✓ Deleted: $session_file${NC}"
    exit 0
fi

# ==============================================================================
# MODE 1: Direct extraction (--extract <session-id>)
# ==============================================================================
if [[ -n "$EXTRACT_SESSION" ]]; then
    echo -e "${CYAN}Extracting session: ${NC}$EXTRACT_SESSION"
    echo ""

    session_file=$(find_session_file "$EXTRACT_SESSION")
    if [[ -z "$session_file" ]]; then
        echo -e "${RED}Error: Session not found: $EXTRACT_SESSION${NC}"
        echo "Searched in: $PROJECT_HISTORY_DIR"
        echo "Also searched: $CLAUDE_PROJECTS_BASE"
        exit 1
    fi

    echo -e "${GREEN}Found: ${NC}$session_file"
    echo ""

    if [[ -n "$ANALYZE_PROMPT" ]]; then
        # Capture extraction output and pipe to analyzer
        # Resolve symlinks to get actual script location
        SCRIPT_PATH="${BASH_SOURCE[0]}"
        if [[ -L "$SCRIPT_PATH" ]]; then
            SCRIPT_PATH="$(readlink "$SCRIPT_PATH")"
            # Handle relative symlinks
            if [[ "$SCRIPT_PATH" != /* ]]; then
                SCRIPT_PATH="$(dirname "${BASH_SOURCE[0]}")/$SCRIPT_PATH"
            fi
        fi
        SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
        ANALYZER="$SCRIPT_DIR/../../../../scripts/llamacpp/analyze.sh"

        if [[ ! -f "$ANALYZER" ]]; then
            echo -e "${RED}Error: Analyzer script not found at: $ANALYZER${NC}" >&2
            exit 1
        fi

        echo -e "${MAGENTA}Analyzing with prompt: ${NC}$ANALYZE_PROMPT"
        echo ""

        extract_session "$session_file" "$MAX_LINES" "$QUERY" | bash "$ANALYZER" --prompt "$ANALYZE_PROMPT"
    else
        extract_session "$session_file" "$MAX_LINES" "$QUERY"
    fi
    exit 0
fi

# ==============================================================================
# MODE 2 & 3: Search (with optional extraction)
# ==============================================================================

# Check if project history directory exists
if [[ ! -d "$PROJECT_HISTORY_DIR" ]]; then
    echo -e "${RED}Error: No chat history found for this project${NC}"
    echo "Looking for: $PROJECT_HISTORY_DIR"
    echo ""
    echo "Available project histories:"
    ls "$CLAUDE_PROJECTS_BASE" 2>/dev/null | grep -E "^-Users-" | head -10
    exit 1
fi

echo -e "${CYAN}Query: ${NC}$QUERY"
echo -e "${CYAN}Searching in: ${NC}$PROJECT_HISTORY_DIR"
echo ""

# Find all session files (UUIDs only, not agent files)
find "$PROJECT_HISTORY_DIR" -maxdepth 1 -name "*.jsonl" -type f ! -name "agent-*" | while read -r session_file; do
    filename=$(basename "$session_file" .jsonl)

    # Skip if not a UUID format (8-4-4-4-12)
    if [[ ! "$filename" =~ ^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$ ]]; then
        continue
    fi

    # Get session content and search
    content=$(get_session_content "$filename" 2>/dev/null || cat "$session_file" 2>/dev/null || true)

    # Count matches (case-insensitive)
    count=$(echo "$content" | grep -ci "$QUERY" 2>/dev/null || true)

    # Only include if we have matches
    if [[ -n "$count" ]] && [[ "$count" -gt 0 ]]; then
        # Get file modification time
        mod_time=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$session_file" 2>/dev/null || date -r "$session_file" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "unknown")

        # Get a snippet if context is requested
        snippet=""
        if [[ "$SHOW_CONTEXT" == true ]]; then
            snippet=$(echo "$content" | grep -i "$QUERY" 2>/dev/null | head -1 | sed 's/.*"text":"//' | cut -c1-150 | tr -d '\n' || true)
        fi

        echo "$count|$filename|$mod_time|$snippet" >> "$RESULTS_FILE"
    fi
done

# Check if we have any results
if [[ ! -s "$RESULTS_FILE" ]]; then
    echo -e "${YELLOW}No matches found for '$QUERY'${NC}"
    exit 0
fi

# Sort by match count (descending), then by date
SORTED_RESULTS=$(sort -t'|' -k1 -rn "$RESULTS_FILE")
total_sessions=$(echo "$SORTED_RESULTS" | wc -l | tr -d ' ')
echo -e "${GREEN}Found $total_sessions session(s) with matches:${NC}"
echo ""

# Display search results
count=0
echo "$SORTED_RESULTS" | head -n "$LIMIT" | while IFS='|' read -r matches session_id mod_time snippet; do
    ((count++)) || true
    short_id="${session_id:0:8}"

    echo -e "${BLUE}$count.${NC} [${GREEN}$short_id${NC}] - ${YELLOW}$matches matches${NC} - $mod_time"
    echo -e "   Full ID: $session_id"
    echo -e "   ${CYAN}Resume:${NC} claude --resume $session_id"

    if [[ "$SHOW_CONTEXT" == true ]] && [[ -n "$snippet" ]]; then
        echo -e "   ${CYAN}Preview:${NC} $snippet..."
    fi
    echo ""
done

# ==============================================================================
# MODE 2b: Extract matches if requested
# ==============================================================================
if [[ "$EXTRACT_MATCHES" == true ]]; then
    echo ""
    echo -e "${MAGENTA}========================================${NC}"
    echo -e "${MAGENTA}EXTRACTING TOP $EXTRACT_LIMIT MATCHES${NC}"
    echo -e "${MAGENTA}========================================${NC}"
    echo ""

    if [[ -n "$ANALYZE_PROMPT" ]]; then
        # Analyze mode: collect all extractions and pipe to analyzer
        # Resolve symlinks to get actual script location
        SCRIPT_PATH="${BASH_SOURCE[0]}"
        if [[ -L "$SCRIPT_PATH" ]]; then
            SCRIPT_PATH="$(readlink "$SCRIPT_PATH")"
            # Handle relative symlinks
            if [[ "$SCRIPT_PATH" != /* ]]; then
                SCRIPT_PATH="$(dirname "${BASH_SOURCE[0]}")/$SCRIPT_PATH"
            fi
        fi
        SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
        ANALYZER="$SCRIPT_DIR/../../../../scripts/llamacpp/analyze.sh"

        if [[ ! -f "$ANALYZER" ]]; then
            echo -e "${RED}Error: Analyzer script not found at: $ANALYZER${NC}" >&2
            exit 1
        fi

        echo -e "${MAGENTA}Analyzing with prompt: ${NC}$ANALYZE_PROMPT"
        echo ""

        # Create temporary file to collect all extractions
        EXTRACTION_FILE=$(mktemp)
        trap "rm -f $EXTRACTION_FILE" EXIT

        extract_count=0
        echo "$SORTED_RESULTS" | head -n "$EXTRACT_LIMIT" | while IFS='|' read -r matches session_id mod_time snippet; do
            ((extract_count++)) || true

            session_file=$(find_session_file "$session_id")
            if [[ -n "$session_file" ]]; then
                echo -e "${CYAN}[$extract_count/$EXTRACT_LIMIT] Extracting: $session_id${NC}"
                extract_session "$session_file" "$MAX_LINES" "$QUERY" >> "$EXTRACTION_FILE"
                echo "" >> "$EXTRACTION_FILE"
            fi
        done

        # Pipe collected extractions to analyzer
        cat "$EXTRACTION_FILE" | bash "$ANALYZER" --prompt "$ANALYZE_PROMPT"
    else
        # Normal extraction mode
        extract_count=0
        echo "$SORTED_RESULTS" | head -n "$EXTRACT_LIMIT" | while IFS='|' read -r matches session_id mod_time snippet; do
            ((extract_count++)) || true

            session_file=$(find_session_file "$session_id")
            if [[ -n "$session_file" ]]; then
                echo -e "${CYAN}[$extract_count/$EXTRACT_LIMIT] Extracting: $session_id${NC}"
                extract_session "$session_file" "$MAX_LINES" "$QUERY"
                echo ""
            fi
        done
    fi
fi

echo -e "${CYAN}Tip:${NC} Use 'claude --resume <session-id>' to resume a session"
echo -e "${CYAN}Tip:${NC} Use '--extract <id>' to extract a specific session"
echo -e "${CYAN}Tip:${NC} Use '--extract-matches' to auto-extract search results"
