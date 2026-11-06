# Notes

All 28 checks in test_api.py pass locally on a fresh copy of the database. I could not load-test here (no k6, and not Linux), so I have no measured user count.

## Design
- **One process, plain `node:http`, no framework.** The box has 1 vCPU, so clustering or worker threads would only add context switches and memory. Express and Fastify add per-request overhead that gains nothing here.
- **`node:sqlite` (built in), synchronous.** There is no native build to fail on the server, and a read costs microseconds. With 1 vCPU, sync calls are as fast as async ones and cheaper. The prepared statements are created once.
- **Rule 2 is respected.** Every request, including the token check, queries SQLite. There is no app-level cache.
- **Pragmas:** WAL, `synchronous=NORMAL` (the 201 is committed in the WAL before the response, as Rule 3 requires), a 64 MB page cache, a 256 MB mmap, and a 5 s busy timeout.
- **Reads and writes are single statements.** The list is one indexed query: `notes` joined to `users`, `ORDER BY id DESC LIMIT 20`. A single note is a primary-key lookup. A POST is `INSERT ... RETURNING id, created_at`, and the author comes from the token lookup.
- **Hand-built JSON.** I assemble the strings directly, with `JSON.stringify` only for the string fields. This keeps the key order and compact form the spec asks for and avoids copying objects.
- **Keep-alive is tuned.** Node's default 5 s keep-alive timeout is shorter than the 5–15 s gap between a user's clicks, so every click would pay for a new TCP connection. I set the timeout to 120 s, removed the request timeout, and set the listen backlog to 8192.
- **Memory:** V8's old-space limit is 384 MB, so a leak is bounded and the OS has room. There is a per-request body cap of 64 KB. The SQLite mmap is page cache, not heap.
- **Errors follow the spec:** auth is checked before the JSON is parsed. The `/notes/:id` checks are: not all digits or all zeros gives 400, and a very large id gives 404. Body length is counted in code points, to match SQLite's `length()`.

## Deployment
- `install.sh` symlinks node, npm and npx from `/opt/node26/bin`.
- `build.sh` runs `npm install --ignore-scripts`. Native build scripts are skipped because the server never loads `better-sqlite3`. `package.json` pins the three listed versions exactly.
- `start.sh` runs in the foreground and reads `SQLITE_PATH`, `HOST` and `PORT`.
