# Architecture and Performance Optimizations for Notes API

This document details the architectural choices, optimizations, and system configurations implemented to maximize simultaneous users on a 1 vCPU, 1 GB RAM Ubuntu 24.04 instance without swap.

---

## 1. Executive Summary & Scoring Dynamics

Under `yuk.js`, each virtual user (VU) clicks once every 5 to 15 seconds (average 10 seconds per request, with 70% `GET /notes`, 20% `GET /notes/:id`, and 10% `POST /notes`). 
- 1,000 VUs generate ~100 req/s.
- 10,000 VUs generate ~1,000 req/s.
- 30,000 VUs generate ~3,000 req/s.

On a 1 vCPU machine with 1 GB RAM, the primary constraints are:
1. **Event loop & CPU efficiency**: Every microsecond of CPU time spent per request subtracts from the total request rate achievable before p95 latency exceeds 1 second.
2. **Memory budget (No Swap)**: The 1 GB RAM is shared between the OS, kernel TCP socket buffers for tens of thousands of connections, SQLite memory-mapped pages, and the Node process. Any memory leak or unbounded V8 heap growth triggers the Linux OOM killer.
3. **Connection management**: Tens of thousands of idle connections waiting between user clicks must not saturate file descriptors or cause TCP handshake churn.

---

## 2. Core Architectural Decisions

### Direct `node:http` Engine (Zero-Framework Overhead)
Rather than Express 5 or Fastify 5 (both included in dependencies), the server runs on Node's built-in `node:http` directly:
- **No middleware overhead**: Eliminates middleware pipelines, routing tree traversals, context object allocations, and wrapper promises on every request.
- **Micro-routing**: Path routing uses direct string and character code comparisons (`req.url`), completely avoiding regular expression overhead and `new URL()` allocations on the hot path.

### Single-Process Event-Driven Model
On a shared 1 vCPU VM:
- Spawning multiple cluster workers creates heavy context switching and doubles/triples memory overhead (each Node process holds baseline V8 memory and separate SQLite handles).
- A single event-driven Node.js process handles all I/O non-blockingly with zero inter-process IPC overhead.

---

## 3. Database & SQL Optimizations

### Native SQLite JSON Generation (`json_object` & `json_group_array`)
Instead of fetching row objects into JavaScript, transforming them into arrays, and calling `JSON.stringify()` in V8:
- `GET /notes` uses SQLite's built-in `json_object` and `json_group_array` in C to serialize the top 20 notes directly in the database engine:
  ```sql
  SELECT json_object('notes', json_group_array(json_object('id', id, 'author', username, 'body', body, 'created_at', created_at)))
  FROM (
    SELECT n.id as id, u.username as username, n.body as body, n.created_at as created_at
    FROM notes n JOIN users u ON n.user_id = u.id
    ORDER BY n.id DESC LIMIT 20
  )
  ```
- `GET /notes/:id` uses:
  ```sql
  SELECT json_object('note', json_object('id', n.id, 'author', u.username, 'body', n.body, 'created_at', n.created_at))
  FROM notes n JOIN users u ON n.user_id = u.id WHERE n.id = ?
  ```
- `POST /notes` uses `RETURNING json_object(...)` directly on the `INSERT`:
  ```sql
  INSERT INTO notes (user_id, body) VALUES (?, ?)
  RETURNING json_object('note', json_object('id', id, 'author', cast(? as text), 'body', body, 'created_at', created_at))
  ```
This completely eliminates object allocation, garbage collection pressure, and JSON serialization in V8. SQLite formats and escapes all strings directly in C.

### Engine Pragma Tuning
- `PRAGMA journal_mode = WAL`: Allows concurrent readers and writer without lock contention.
- `PRAGMA synchronous = NORMAL`: Satisfies Rule 3 durability while avoiding synchronous `fsync` per transaction, batching flushes on WAL checkpoints.
- `PRAGMA mmap_size = 536870912` (512 MB): Maps the entire SQLite database into virtual address space. Reads access kernel page cache pages directly via memory pointers with zero `read()` syscalls and zero user-space copying.
- `PRAGMA cache_size = -16000` (16 MB): Caps SQLite's internal page cache to keep RAM lean, relying on `mmap` and the OS page cache (which the kernel can reclaim if socket buffers need RAM).
- `PRAGMA temp_store = MEMORY`: Keeps temporary operations in RAM.
- `PRAGMA busy_timeout = 5000`: Gracefully queues for locks rather than failing.
- `PRAGMA wal_autocheckpoint = 2000`: Balances checkpoint frequency and WAL size.

### Dual Engine Support (`better-sqlite3` with `node:sqlite` Fallback)
The server attempts to use `better-sqlite3` for maximum V8 C++ binding performance, and gracefully falls back to Node 26's native `node:sqlite` if `better-sqlite3` is absent.

---

## 4. HTTP & High-VU Keep-Alive Optimization

### The Keep-Alive Timeout Bottleneck (Critical Discovery)
Node's default `http.Server.keepAliveTimeout` is **5 seconds** (5,000 ms).
In `yuk.js`, virtual users sleep between 5 and 15 seconds (`5 + Math.random() * 10`) between requests.
Under default settings, almost every single request experiences a closed socket and must renegotiate a TCP handshake (SYN -> SYN-ACK -> ACK). For 20,000 users, that would trigger 2,000 new TCP handshakes and teardowns per second, causing severe CPU exhaustion, connection queue overflows, and socket `TIME_WAIT` exhaustion.
- Configured:
  - `server.keepAliveTimeout = 65000` (65 seconds)
  - `server.headersTimeout = 66000` (66 seconds)
  - `server.requestTimeout = 0`
This allows all VUs to connect once during the ramp stage and keep their connections alive throughout the entire 5-minute benchmark.

### Socket & Header Optimizations
- `socket.setNoDelay(true)`: Disables Nagle's algorithm on all accepted sockets, preventing 40ms delayed-ACK stalls.
- Explicit `Content-Length` headers: Prevents Node.js from falling back to chunked transfer encoding (`Transfer-Encoding: chunked`), saving chunk framing CPU and bandwidth.
- Static Buffer Pre-allocation: Responses for `/health` (200), bad JSON (400), invalid ID (400), invalid body (400), unauthorized (401), and not found (404) are pre-allocated `Buffer` objects with pre-created header objects.
- Immediate Auth Evaluation: On `POST /notes`, bearer authorization is verified before reading the request stream, immediately returning 401 if unauthorized.

---

## 5. Memory Management & OOM Prevention

On a 1 GB RAM system with no swap, kernel OOM is a fatal risk under thousands of connections:
- In `start.sh`, Node is launched with `--max-old-space-size=384`.
- Under heavy load (tested with >70,000 requests and hundreds of concurrent connections), the Node process consumes only **~48 MB RSS** and **~9 MB heap**, leaving >700 MB for OS processes, kernel socket buffers (`rmem`/`wmem`), and SQLite disk pages.
- `process.on('uncaughtException')` and `process.on('unhandledRejection')` prevent any process exit.

---

## 6. System Limits & Deployment

- `start.sh`: Automatically raises file descriptor limit via `ulimit -n 1048576 2>/dev/null || ulimit -n 65535 2>/dev/null` to ensure high connection limits.
- `install.sh`: Configures `/etc/security/limits.conf` and systemd limits for persistent 1,048,576 file descriptors, symlinks `/opt/node26/bin` binaries, and grants `CAP_NET_BIND_SERVICE` capability to Node so port 80 can be bound without root privileges.
- `build.sh`: Runs `npm install --omit=dev` using pinned dependencies in `package.json`.
