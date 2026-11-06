#!/bin/bash
set -euo pipefail

# Add Node 26 to PATH if present at /opt/node26/bin
if [ -d "/opt/node26/bin" ]; then
  export PATH="/opt/node26/bin:$PATH"
fi

# Set maximum file descriptors for high connection concurrency
ulimit -n 1048576 2>/dev/null || ulimit -n 65535 2>/dev/null || true

# Environment defaults
export SQLITE_PATH="${SQLITE_PATH:-seed/notes.db}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-80}"

# Run server in the foreground with memory limit tuned for 1 GB RAM VM
exec node --max-old-space-size=384 server.js
