# Notes API implementation notes

The server uses Node's built-in HTTP/1.1 server rather than a framework. It
keeps keep-alive connections open for 30 seconds (longer than a user's click
gap), while setting finite header/request timeouts so slow clients cannot grow
memory usage indefinitely.

Every endpoint executes a prepared SQLite statement for the request; no result
or authentication cache is used. The two GET response shapes are constructed
with SQLite JSON functions, which retains the required compact field order and
removes the normal Node object and JSON encoding work from the dominant read
path. Inserts authenticate from SQLite first, validate and trim the JSON body,
then use `INSERT ... RETURNING` so the acknowledged row has already committed.

SQLite is explicitly in WAL mode with `synchronous=NORMAL`, satisfying durable
writes while keeping write latency practical. Its private page cache is limited
to 16 MiB and the 293 MiB database is mmap-enabled, letting the OS page cache
serve hot pages without a second large process-owned cache. `start.sh` caps the
V8 old space at 256 MiB, leaving RAM for SQLite mappings, socket state, and the
shared VM. Request bodies are capped at 64 KiB after authentication; valid API
bodies are far smaller, and this bounds concurrent upload memory.

`install.sh` installs the build prerequisites on Ubuntu, `build.sh` performs a
locked production install with Node 26, and `start.sh` reads `SQLITE_PATH`,
`HOST`, and `PORT` through the server process.

Validation run:

```sh
python3 test_api.py http://127.0.0.1:18982 seed/tokens.json
```

All 28 supplied checks passed against a fresh database copy.
