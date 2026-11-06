Implemented the Node.js backend and deployment scripts.

Key files:

- [server.js](~/.cache/deney-runs/v7/codex-1/server.js)
- [install.sh](~/.cache/deney-runs/v7/codex-1/install.sh)
- [build.sh](~/.cache/deney-runs/v7/codex-1/build.sh)
- [start.sh](~/.cache/deney-runs/v7/codex-1/start.sh)
- [package.json](~/.cache/deney-runs/v7/codex-1/package.json)
- [NOTES.md](~/.cache/deney-runs/v7/codex-1/NOTES.md)

It uses direct HTTP handling, prepared SQLite statements, WAL/NORMAL durability, bounded request buffering, keep-alive, and a 192 MiB V8 heap cap for memory headroom.

Verification: `python3 test_api.py` passes all 28 supplied checks against a fresh database copy.