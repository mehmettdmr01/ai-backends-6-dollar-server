#!/bin/bash
set -e
cd "$(dirname "$0")"
export PATH=/opt/node26/bin:$PATH
# The server only uses node:sqlite; skip native build scripts so nothing can fail to compile.
npm install --ignore-scripts --no-audit --no-fund || true
