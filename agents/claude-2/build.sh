#!/bin/sh
set -e
cd "$(dirname "$0")"
export PATH=/opt/node26/bin:$PATH
npm install --omit=dev --no-audit --no-fund
