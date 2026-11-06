#!/bin/bash
set -euo pipefail

# Add Node 26 to PATH if present at /opt/node26/bin
if [ -d "/opt/node26/bin" ]; then
  export PATH="/opt/node26/bin:$PATH"
fi

# Install dependencies pinned in package.json
npm install --omit=dev
