#!/bin/bash
set -e

# install.sh runs as root, once, on a clean Ubuntu 24.04.
# The server has Node 26 at /opt/node26/bin.

# 1. Ensure /opt/node26/bin is accessible in standard PATH
if [ -d "/opt/node26/bin" ]; then
    ln -sf /opt/node26/bin/node /usr/local/bin/node
    ln -sf /opt/node26/bin/npm /usr/local/bin/npm
    ln -sf /opt/node26/bin/npx /usr/local/bin/npx
fi

# 2. Allow node to bind to privileged ports (like port 80) if run as non-root
if command -v setcap >/dev/null 2>&1; then
    [ -f "/opt/node26/bin/node" ] && setcap 'cap_net_bind_service=+ep' /opt/node26/bin/node || true
    [ -f "/usr/local/bin/node" ] && setcap 'cap_net_bind_service=+ep' /usr/local/bin/node || true
fi

# 3. Configure file descriptor limits (nofile) for high concurrency
if [ -f /etc/security/limits.conf ]; then
    cat >> /etc/security/limits.conf << 'EOF'
* soft nofile 1048576
* hard nofile 1048576
root soft nofile 1048576
root hard nofile 1048576
EOF
fi

if [ -f /etc/systemd/system.conf ]; then
    sed -i 's/^#*DefaultLimitNOFILE=.*/DefaultLimitNOFILE=1048576/' /etc/systemd/system.conf || true
fi

if [ -f /etc/systemd/user.conf ]; then
    sed -i 's/^#*DefaultLimitNOFILE=.*/DefaultLimitNOFILE=1048576/' /etc/systemd/user.conf || true
fi

# 4. Install essential build tools if needed by npm packages
apt-get update -y || true
apt-get install -y --no-install-recommends build-essential python3 libcap2-bin || true

echo "install.sh completed successfully."
