#!/bin/sh
# Run once as root on a clean Ubuntu 24.04 host.
set -eu
apt-get update
apt-get install -y --no-install-recommends build-essential python3 ca-certificates
