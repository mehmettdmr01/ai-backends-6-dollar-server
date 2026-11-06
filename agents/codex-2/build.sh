#!/bin/sh
set -eu
NODE_BIN=/opt/node26/bin
"$NODE_BIN/npm" ci --omit=dev --no-audit --no-fund
