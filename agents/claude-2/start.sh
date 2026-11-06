#!/bin/sh
cd "$(dirname "$0")"
export PATH=/opt/node26/bin:$PATH
ulimit -n 1048576 2>/dev/null || ulimit -n 65536 2>/dev/null || true
export HOST="${HOST:-0.0.0.0}" PORT="${PORT:-80}"
exec node --max-old-space-size=300 server.js
