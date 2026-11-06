# Notes API performance notes

- The server uses `node:http` directly.  It has no framework router or generic
  JSON middleware in the hot path, and it keeps HTTP/1.1 connections alive for
  65 seconds so the click workload normally reuses a socket.
- A single in-process `better-sqlite3` connection holds prepared statements for
  the three read shapes and the insert.  Prepared statements are code caching,
  not result caching: every `/notes`, `/notes/:id`, and POST token check runs a
  SQLite query for that request.
- The list query starts from `notes` in descending rowid order and only joins 20
  users.  A point read starts at the note primary key.  These match the supplied
  schema without changing it.
- SQLite uses WAL, `synchronous=NORMAL`, a small 4 MiB SQLite page cache, and a
  256 MiB mmap window.  NORMAL is permitted by the spec and commits before the
  201 response.  The mmap is virtual address space backed by the kernel page
  cache, not a 256 MiB eager allocation; keeping SQLite's own cache modest is
  friendlier to a 1 GB shared VM.
- Response serialization is compact and only constructs the exact JSON needed.
  Request bodies are bounded and streamed, so slow or oversized uploads do not
  accumulate unbounded JavaScript memory.
- `start.sh` caps V8's old-space heap at 192 MiB.  This leaves headroom for the
  SQLite native allocation, kernel page cache, and many live keep-alive sockets,
  which is more important than a very large heap on the stated machine.
