#!/usr/bin/env bash
# Target box setup (Ubuntu 24.04, root). Nothing here tunes the kernel.
# Usage: kur-hedef.sh <ufw|noufw>. Expects izle.py, fresh.sh, sec.sh, gizli_test.py and test_api.py next to this script.
set -euo pipefail
FW="${1:?ufw or noufw}"; HERE="$(cd "$(dirname "$0")" && pwd)"
cloud-init status --wait >/dev/null 2>&1 || true
[ -z "$(swapon --show)" ] || { echo "box has swap, the rules say none"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -o DPkg::Lock::Timeout=300"
$APT update -q; $APT install -y -q sqlite3 curl python3 sysbench rsync
id deploy >/dev/null 2>&1 || useradd -m -s /bin/bash deploy
mkdir -p /srv/bench /srv/data /srv/seed /srv/yarisma; chown deploy:deploy /srv/data /srv/yarisma
cp "$HERE"/izle.py "$HERE"/fresh.sh "$HERE"/sec.sh "$HERE"/gizli_test.py "$HERE"/test_api.py /srv/bench/; chmod +x /srv/bench/*
cat > /etc/systemd/system/yarisma.service <<'UNIT'
[Unit]
Description=benchmark contestant
[Service]
User=deploy
EnvironmentFile=/etc/yarisma.env
WorkingDirectory=/srv/yarisma/current
ExecStart=/bin/bash /srv/yarisma/current/start.sh
LimitNOFILE=65535
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=no
UNIT
systemctl daemon-reload
if [ "$FW" = ufw ]; then ufw allow 22/tcp; ufw allow 80/tcp; ufw --force enable; else ufw --force disable || true; fi
# Ubuntu's own background jobs: apt-daily-upgrade once took 3.4 min CPU and 695 MB on a 1 GB box mid-ramp (6 Nov,
# Gemini OOM). They are switched off for every contestant alike before any measurement.
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer fwupd-refresh.timer motd-news.timer man-db.timer update-notifier-motd.timer 2>/dev/null || true
systemctl stop apt-daily.service apt-daily-upgrade.service unattended-upgrades.service fwupd.service 2>/dev/null || true
# What the box actually is. Boxes on different tiers must match before their numbers are compared.
modprobe nf_conntrack 2>/dev/null || true
cd /tmp
{ echo "date: $(date -u +%FT%TZ)"; echo "firewall: $FW"; uname -r; lscpu | grep -E 'Model name|^CPU\(s\)|MHz|Hypervisor'
  free -m; df -h / | tail -1
  echo "conntrack_max: $(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null || echo none)"
  echo "tcp_mem: $(cat /proc/sys/net/ipv4/tcp_mem)"; echo "somaxconn: $(cat /proc/sys/net/core/somaxconn)"
  echo "cpu: $(sysbench cpu --threads=1 --time=30 run | grep 'events per second')"
  sysbench fileio --file-total-size=256M --file-num=1 prepare >/dev/null
  echo "disk fsync (what every SQLite commit waits for):"
  sysbench fileio --file-total-size=256M --file-num=1 --file-test-mode=rndwr --file-fsync-freq=1 --time=20 run | grep -E 'writes/s|fsyncs/s'
  sysbench fileio --file-total-size=256M --file-num=1 cleanup >/dev/null; } | tee /srv/bench/box.txt
