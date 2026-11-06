#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"; export PATH="/opt/node26/bin:$PATH"
npm install --no-audit --no-fund
