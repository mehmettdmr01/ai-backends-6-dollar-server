Built the Node.js backend and deployment scripts.

Key files:

- [server.js](~/deney-v7/codex-2/server.js)
- [package.json](~/deney-v7/codex-2/package.json)
- [install.sh](~/deney-v7/codex-2/install.sh)
- [build.sh](~/deney-v7/codex-2/build.sh)
- [start.sh](~/deney-v7/codex-2/start.sh)
- [NOTES.md](~/deney-v7/codex-2/NOTES.md)

It uses raw Node HTTP, prepared SQLite statements, WAL + `synchronous=NORMAL`, bounded memory settings, and SQLite-native JSON generation for the read-heavy endpoints.

Verified on a fresh database copy: all 28 supplied API checks pass.