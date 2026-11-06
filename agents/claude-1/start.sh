#!/bin/bash
cd "$(dirname "$0")"
export PATH=/opt/node26/bin:$PATH
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-80}"
exec node --max-old-space-size=384 server.js
