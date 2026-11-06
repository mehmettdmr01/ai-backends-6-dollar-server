#!/usr/bin/env bash
# sec.sh <contestant folder under /srv/yarisma>: chooses what the service runs.
set -euo pipefail
NAME="$1"
[ -d "/srv/yarisma/$NAME" ] || { echo "no /srv/yarisma/$NAME"; exit 1; }
ln -sfn "/srv/yarisma/$NAME" /srv/yarisma/current
printf 'SQLITE_PATH=/srv/data/notes.db\nHOST=0.0.0.0\nPORT=80\n' > /etc/yarisma.env
systemctl daemon-reload
