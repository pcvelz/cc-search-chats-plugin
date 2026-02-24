#!/bin/bash
# Test harness for search-chat.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$SCRIPT_DIR/commands/search-chat.sh"
PASS=0
FAIL=0
TESTS=()

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

assert_exit_code() {
    local desc="$1" expected="$2" actual="$3"
    if [[ "$actual" -eq "$expected" ]]; then
        PASS=$((PASS + 1))
        echo -e "  ${GREEN}PASS${NC} $desc"
    else
        FAIL=$((FAIL + 1))
        echo -e "  ${RED}FAIL${NC} $desc (expected exit $expected, got $actual)"
        TESTS+=("FAIL: $desc")
    fi
}

assert_output_contains() {
    local desc="$1" expected="$2" output="$3"
    if echo "$output" | grep -qi "$expected"; then
        PASS=$((PASS + 1))
        echo -e "  ${GREEN}PASS${NC} $desc"
    else
        FAIL=$((FAIL + 1))
        echo -e "  ${RED}FAIL${NC} $desc (output missing: '$expected')"
        TESTS+=("FAIL: $desc")
    fi
}

assert_output_not_contains() {
    local desc="$1" unexpected="$2" output="$3"
    if echo "$output" | grep -qi "$unexpected"; then
        FAIL=$((FAIL + 1))
        echo -e "  ${RED}FAIL${NC} $desc (output contains unexpected: '$unexpected')"
        TESTS+=("FAIL: $desc")
    else
        PASS=$((PASS + 1))
        echo -e "  ${GREEN}PASS${NC} $desc"
    fi
}

# ==============================================================================
# Setup mock environment
# ==============================================================================
MOCK_BASE=$(mktemp -d)
trap 'rm -rf "$MOCK_BASE"' EXIT

# Mock project: -Users-peter-Documents-Code-test-project
MOCK_PROJECT="$MOCK_BASE/-Users-peter-Documents-Code-test-project"
mkdir -p "$MOCK_PROJECT"

# Mock second project: -Users-peter-Documents-Code-other-project
MOCK_OTHER="$MOCK_BASE/-Users-peter-Documents-Code-other-project"
mkdir -p "$MOCK_OTHER"

# Create mock session JSONL files
SESSION_UUID="a3d594c8-1ce8-7e25-f100-b9e4d2a73f01"
cat > "$MOCK_PROJECT/$SESSION_UUID.jsonl" << 'EOF'
{"sessionId":"a3d594c8-1ce8-7e25-f100-b9e4d2a73f01","cwd":"/Users/peter/Documents/Code/test-project","timestamp":"2026-02-24T10:00:00Z","message":{"role":"user","content":"nginx returns 502 Bad Gateway on checkout after the last deploy. Error log shows: upstream prematurely closed connection while reading response header from upstream, client: 10.0.1.42, server: shop.example.com, upstream: fastcgi://unix:/run/php/php8.2-fpm.sock"}}
{"sessionId":"a3d594c8-1ce8-7e25-f100-b9e4d2a73f01","cwd":"/Users/peter/Documents/Code/test-project","timestamp":"2026-02-24T10:01:00Z","message":{"role":"assistant","content":"The php-fpm process is crashing under load. The nginx error log confirms the upstream socket is closing before sending headers. Let me check the php-fpm pool config and memory limits."}}
{"sessionId":"a3d594c8-1ce8-7e25-f100-b9e4d2a73f01","cwd":"/Users/peter/Documents/Code/test-project","timestamp":"2026-02-24T10:02:00Z","message":{"role":"user","content":"Also getting redis errors: RedisException: Connection timed out in /var/www/vendor/predis/predis/src/Connection/StreamConnection.php:128. read error on connection to redis-primary:6379"}}
{"sessionId":"a3d594c8-1ce8-7e25-f100-b9e4d2a73f01","cwd":"/Users/peter/Documents/Code/test-project","timestamp":"2026-02-24T10:03:00Z","message":{"role":"assistant","content":"The redis connection pool is exhausted. predis defaults to 5s timeout with no retry. I see the pool has pm.max_children=5 which is too low. Bumping to 20 and setting redis read_timeout to 2.5 should fix both issues."}}
EOF

# Second session in same project
SESSION2_UUID="e7f2b08c-4a91-43d6-8c5e-91d3f7260ab8"
cat > "$MOCK_PROJECT/$SESSION2_UUID.jsonl" << 'EOF'
{"sessionId":"e7f2b08c-4a91-43d6-8c5e-91d3f7260ab8","cwd":"/Users/peter/Documents/Code/test-project","timestamp":"2026-02-24T11:00:00Z","message":{"role":"user","content":"Browser console shows: Access to XMLHttpRequest at https://api.example.com/v1/payments from origin https://shop.example.com has been blocked by CORS policy: Response to preflight request doesn't pass access control check: No Access-Control-Allow-Origin header is present on the requested resource."}}
{"sessionId":"e7f2b08c-4a91-43d6-8c5e-91d3f7260ab8","cwd":"/Users/peter/Documents/Code/test-project","timestamp":"2026-02-24T11:01:00Z","message":{"role":"assistant","content":"The payment API at api.example.com is missing CORS headers. The OPTIONS preflight is returning 403 instead of 204 with the required Access-Control-Allow-Origin, Access-Control-Allow-Methods, and Access-Control-Allow-Headers. Need to add CORS middleware to the API gateway."}}
EOF

# Session in OTHER project (only reachable via --all-projects)
SESSION3_UUID="c49e0f3a-862d-4b17-a5c0-de8743b1f295"
cat > "$MOCK_OTHER/$SESSION3_UUID.jsonl" << 'EOF'
{"sessionId":"c49e0f3a-862d-4b17-a5c0-de8743b1f295","cwd":"/Users/peter/Documents/Code/other-project","timestamp":"2026-02-24T12:00:00Z","message":{"role":"user","content":"After scaling to 4 replicas the /health endpoint returns 502 Bad Gateway intermittently. kubectl logs show: E0224 12:00:01.482910 1 server.go:302] HTTP probe failed with statuscode: 503, output: service unavailable - database pool exhausted"}}
{"sessionId":"c49e0f3a-862d-4b17-a5c0-de8743b1f295","cwd":"/Users/peter/Documents/Code/other-project","timestamp":"2026-02-24T12:01:00Z","message":{"role":"assistant","content":"The database connection pool is shared across replicas but sized for a single instance. Each replica opens max_connections=25, so 4 replicas need 100 connections total. PostgreSQL max_connections is probably still at the default 100. Bump it to 200 or switch to PgBouncer for connection pooling."}}
EOF

# Skip agent files (should be ignored by search)
cat > "$MOCK_PROJECT/agent-d81f3e2a-09b7-4c5d-ae12-f68930b14c77.jsonl" << 'EOF'
{"sessionId":"agent-test","message":{"role":"assistant","content":"502 Bad Gateway — automated health check output from monitoring agent"}}
EOF

# Helper to run script with mock base
run_search() {
    CLAUDE_PROJECTS_BASE="$MOCK_BASE" \
    bash "$SCRIPT" --project /Users/peter/Documents/Code/test-project "$@" 2>&1
}

echo ""
echo "=========================================="
echo " search-chat.sh Test Suite"
echo "=========================================="

# ==============================================================================
# Test: Configurable base path
# ==============================================================================
echo ""
echo -e "${YELLOW}--- Configurable base path ---${NC}"

output=$(run_search "502" 2>&1) || true
assert_output_contains "CLAUDE_PROJECTS_BASE override works" "502" "$output"

# ==============================================================================
# Test: --all-projects flag
# ==============================================================================
echo ""
echo -e "${YELLOW}--- --all-projects flag ---${NC}"

# Default search: only current project
output=$(run_search "502" 2>&1) || true
assert_output_contains "Default search finds 502 in current project" "a3d594c8" "$output"
assert_output_not_contains "Default search does NOT find other project" "c49e0f3a" "$output"

# --all-projects: finds matches across all projects
output=$(CLAUDE_PROJECTS_BASE="$MOCK_BASE" bash "$SCRIPT" --project /Users/peter/Documents/Code/test-project --all-projects "502" 2>&1) || true
assert_output_contains "All-projects finds current project match" "a3d594c8" "$output"
assert_output_contains "All-projects finds other project match" "c49e0f3a" "$output"

# ==============================================================================
# Test: Smart fallback - UUID not found → search
# ==============================================================================
echo ""
echo -e "${YELLOW}--- Smart fallback ---${NC}"

# Input looks like UUID but doesn't match any session → fall back to text search
output=$(run_search "f1b2c3d4" 2>&1) || true
assert_output_not_contains "Fake UUID does NOT hard-error" "Error: Session not found" "$output"
assert_output_contains "Fake UUID shows fallback note" "did not match any session" "$output"

# Explicit --extract with bad UUID should STILL error
output=$(CLAUDE_PROJECTS_BASE="$MOCK_BASE" bash "$SCRIPT" --project /Users/peter/Documents/Code/test-project --extract "deadbeef-0000-0000-0000-000000000000" 2>&1) || true
assert_output_contains "Explicit --extract still errors on not found" "not found" "$output"

# UUID + filter where UUID doesn't exist → fall back to combined search
output=$(run_search 'f1b2c3d4 gateway' 2>&1) || true
assert_output_not_contains "UUID+filter fallback does not error" "Error: Session not found" "$output"
assert_output_contains "UUID+filter fallback shows note" "did not match any session" "$output"

# ==============================================================================
# Test: Instruction-style filter → full session extraction
# ==============================================================================
echo ""
echo -e "${YELLOW}--- Instruction-style filter ---${NC}"

# Short keyword filter still works as grep (≤4 words)
output=$(run_search "a3d594c8 redis connection" 2>&1) || true
assert_output_contains "Short filter (3 words) still greps" "redis" "$output"
assert_output_not_contains "Short filter does NOT trigger instruction mode" "Instruction:" "$output"

# Long instruction-style filter skips grep, extracts full session
output=$(run_search 'a3d594c8 what were the redis connection pool settings' 2>&1) || true
assert_output_contains "Instruction detected (>4 words)" "Instruction:" "$output"
assert_output_contains "Full session extracted despite instruction" "502 Bad Gateway" "$output"

# Instruction with explicit --extract also works
output=$(CLAUDE_PROJECTS_BASE="$MOCK_BASE" bash "$SCRIPT" --project /Users/peter/Documents/Code/test-project --extract "$SESSION_UUID" 2>&1 <<< "") || true
# This has no filter so it extracts full session anyway — just verify it works
assert_output_contains "Explicit extract without filter works" "502 Bad Gateway" "$output"

# ==============================================================================
# Test: Existing features still work (regression)
# ==============================================================================
echo ""
echo -e "${YELLOW}--- Regression: UUID extraction ---${NC}"

# Full UUID extraction
output=$(run_search "$SESSION_UUID" 2>&1) || true
assert_output_contains "Full UUID extracts session" "502 Bad Gateway" "$output"

# Partial UUID (8 chars)
output=$(run_search "a3d594c8" 2>&1) || true
assert_output_contains "Partial UUID resolves" "a3d594c8" "$output"

# UUID + filter
output=$(run_search "a3d594c8 redis" 2>&1) || true
assert_output_contains "UUID + filter shows matching content" "redis" "$output"

echo ""
echo -e "${YELLOW}--- Regression: text search ---${NC}"

# Plain text search
output=$(run_search "502" 2>&1) || true
assert_output_contains "Text search finds matches" "match" "$output"

# Search with --limit
output=$(run_search "502" --limit 1 2>&1) || true
assert_output_contains "Limit shows at least one result" "1." "$output"

echo ""
echo -e "${YELLOW}--- Regression: agent files skipped ---${NC}"

# Agent files should be skipped in search results
output=$(run_search "502" 2>&1) || true
assert_output_not_contains "Agent JSONL files excluded from search results" "agent-d81f3e2a" "$output"

echo ""
echo -e "${YELLOW}--- Help flag ---${NC}"

output=$(bash "$SCRIPT" --help 2>&1) || true
assert_output_contains "Help shows --all-projects" "all-projects" "$output"
assert_output_contains "Help shows --context" "context" "$output"
assert_output_contains "Help shows --tail" "tail" "$output"

# ==============================================================================
# Summary
# ==============================================================================
echo ""
echo "=========================================="
TOTAL=$((PASS + FAIL))
echo -e " Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, $TOTAL total"
echo "=========================================="

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "Failed tests:"
    for t in "${TESTS[@]}"; do
        echo "  - $t"
    done
    exit 1
fi
