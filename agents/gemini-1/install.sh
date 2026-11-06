#!/bin/bash
set -euo pipefail

# install.sh runs as root once on a clean Ubuntu 24.04 machine.

export DEBIAN_FRONTEND=noninteractive

# Install build tools in case native addons need compilation
apt-get update -y
apt-get install -y --no-install-recommends build-essential python3

# Configure high file descriptor limits for high concurrency
cat << 'EOF' >> /etc/security/limits.conf
* soft nofile 1048576
* hard nofile 1048576
root soft nofile 1048576
root hard nofile 1048576
EOF

# Ensure systemd user sessions inherit high file descriptor limits if applicable
if [ -f /etc/systemd/system.conf ]; then
  sed -i 's/#DefaultLimitNOFILE=/DefaultLimitNOFILE=1048576/' /etc/systemd/system.conf || true
fi
