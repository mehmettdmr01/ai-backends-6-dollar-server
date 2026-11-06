#!/usr/bin/env bash
set -euo pipefail
apt-get -o DPkg::Lock::Timeout=300 update -q; apt-get -o DPkg::Lock::Timeout=300 install -y -q --no-install-recommends ca-certificates curl xz-utils python3 make g++
[ -x /opt/node26/bin/node ] && exit 0
a="$(mktemp)"; trap 'rm -f "$a"' EXIT
curl -fsSL https://nodejs.org/dist/v26.11.1/node-v26.11.1-linux-x64.tar.xz -o "$a"
echo "3883bfc73f9a680ca4eab04b196068aaaab1373ffa77d8fc1a4408222495b651  $a" | sha256sum -c -
mkdir -p /opt/node26; tar -xJf "$a" -C /opt/node26 --strip-components=1
