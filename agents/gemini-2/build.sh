#!/bin/bash
set -e

# build.sh runs on the server, which has internet, to install dependencies.
# The server has Node 26 at /opt/node26/bin.

export PATH="/opt/node26/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install production dependencies pinned in package.json
npm install --omit=dev

echo "build.sh completed successfully."
