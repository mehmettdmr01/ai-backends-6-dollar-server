#!/usr/bin/env bash
set -euo pipefail

# Run once as root on a clean Ubuntu 24.04 image. Node itself is supplied at
# /opt/node26/bin by the benchmark image; build.sh installs app dependencies.
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  build-essential python3 make g++ ca-certificates
