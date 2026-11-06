# Notes

- **Single process, raw `node:http`.** One vCPU means clustering/workers only add context switches and memory. No framework: no router or middleware overhead, and the few routes are matched by hand.
- **better-sqlite3, synchronous, prepared statements** created once. Each query is microseconds (PK lookup, `ORDER BY id DESC LIMIT 20` on the rowid, token lookup via its UNIQUE index), so doing them inline on the event loop is cheaper than any thread hand-off. Nothing is cached across requests; every request hits SQLite (including token check).
- **Writes:** WAL + `synchronous=NORMAL` (no fsync per commit, still committed before the 201). `INSERT ... RETURNING` then one read-back for the stored `created_at`.
- **Memory:** `cache_size` 16 MB, `mmap_size` 256 MB (file-backed, reclaimable by the kernel, so it does not cause OOM), `--max-old-space-size=300`. Per-connection cost is a few KB, so thousands of keep-alive connections fit.
- **Connections:** keep-alive with a long timeout (k6 reuses connections), `TCP_NODELAY`, backlog 4096, `ulimit -n` raised in start.sh, request body capped at 64 KB, `requestTimeout` disabled so idle keep-alive users aren't dropped.
- **Rules/validation:** 401 checked before body parsing, code-point length for the 500-char limit (matches SQLite `length`), exact id validation, JSON built with `JSON.stringify` in the specified key order.
- Build: `build.sh` runs `npm install --omit=dev` (only better-sqlite3 13.0.3 pinned; install.sh provides a compiler toolchain in case no prebuilt binary is available).
- Not load-tested here (no k6, not Linux); only `test_api.py` (28/28) was run.
