#!/bin/bash
set -e
# Node 26 is already at /opt/node26/bin; expose it on PATH.
for b in node npm npx; do ln -sf /opt/node26/bin/$b /usr/local/bin/$b 2>/dev/null || true; done
