#!/usr/bin/env bash
# Puts the box in the same state before every run: app stopped, fresh seed copy, app healthy. The copy leaves the
# database in the page cache, which is what a server that has been up for a while looks like.
set -euo pipefail
systemctl stop yarisma 2>/dev/null || true
# With the firewall on, connections from the previous run linger in the conntrack table for up to 120 s. Wait, or a
# failed run could fake a wall in the next one. The file does not exist with the firewall off.
CT=/proc/sys/net/netfilter/nf_conntrack_count
if [ -r "$CT" ]; then
  for _ in $(seq 130); do [ "$(cat "$CT")" -lt 1000 ] && break; sleep 1; done
fi
rm -f /srv/data/notes.db /srv/data/notes.db-wal /srv/data/notes.db-shm
cp /srv/seed/notes.db /srv/data/notes.db
chown deploy:deploy /srv/data/notes.db
systemctl reset-failed yarisma 2>/dev/null || true
systemctl start yarisma
for _ in $(seq 60); do curl -sf "http://127.0.0.1:80/health" >/dev/null && { echo healthy; exit 0; }; sleep 1; done
echo "no healthy /health after 60 s"; journalctl -u yarisma -n 30 --no-pager; exit 1
