#!/usr/bin/env bash
# Load generator setup (Ubuntu 24.04, root). Tuned on purpose: this box must never be the bottleneck. It also builds
# the contestants, because a 1 GB box with no swap can run out of memory just compiling them.
# Usage: kur-uretici.sh <k6 version, e.g. v1.4.0>
set -euo pipefail
V="${1:?k6 version}"
cloud-init status --wait >/dev/null 2>&1 || true
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -o DPkg::Lock::Timeout=300"
$APT update -q; $APT install -y -q sqlite3 curl python3 rsync tmux build-essential
id deploy >/dev/null 2>&1 || useradd -m -s /bin/bash deploy
mkdir -p /srv/yarisma; chown deploy:deploy /srv/yarisma
cd /tmp; curl -fsSL "https://github.com/grafana/k6/releases/download/$V/k6-$V-linux-amd64.tar.gz" | tar xz
install "k6-$V-linux-amd64/k6" /usr/local/bin/k6; k6 version
cat > /etc/sysctl.d/90-load.conf <<'CONF'
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
fs.file-max = 1000000
CONF
sysctl --system >/dev/null
[ -f /root/.ssh/id_ed25519 ] || ssh-keygen -q -t ed25519 -N "" -f /root/.ssh/id_ed25519 -C v7-generator
