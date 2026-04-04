#!/bin/bash
# search-chat.sh - Thin wrapper that launches the Python implementation.
# All logic lives in search_chat/ Python package.
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m search_chat "$@"
