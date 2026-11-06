#!/bin/bash

# start.sh runs in the foreground, reads SQLITE_PATH, HOST and PORT.
# The server has Node 26 at /opt/node26/bin.

export PATH="/opt/node26/bin:$PATH"

# Raise file descriptor limit for handling high concurrency connections
ulimit -n 1048576 2>/dev/null || ulimit -n 65535 2>/dev/null || ulimit -n 10240 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export SQLITE_PATH="${SQLITE_PATH:-seed/notes.db}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-80}"

# Run Node in the foreground with bounded heap to fit comfortably within 1 GB RAM
exec node --max-old-space-size=384 server.js
