#!/bin/sh
set -eu
exec /opt/node26/bin/node --max-old-space-size=256 server.js
