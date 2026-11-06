#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PATH=/opt/node26/bin:$PATH
# Keep V8 well below the 1 GB machine limit; SQLite and thousands of sockets use
# memory outside the JavaScript heap too.
exec node --max-old-space-size=192 server.js
