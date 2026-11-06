# Notes API

A small notes service: four endpoints, JSON in and out. `test_api.py` checks everything on this page.

## Runtime
The server reads `SQLITE_PATH` (a SQLite file, WAL mode, schema below), `HOST` and `PORT` from the environment, and speaks HTTP/1.1 with keep-alive. On the benchmark box it serves `0.0.0.0:80` directly, with no proxy in front.

## Schema (fixed: do not add or change tables, columns or indexes)
```sql
CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, token TEXT NOT NULL UNIQUE);
CREATE TABLE notes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 500),
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE INDEX notes_user_id_idx ON notes (user_id);
```
Seed: 20,000 users, 1,000,000 notes, about 290 MB (`seed.py`).

## Endpoints
A note is `{"id":<int>,"author":<username>,"body":<string>,"created_at":<string>}`, keys in that order, compact JSON, `Content-Type: application/json`.

| Request | Success | Body |
|---|---|---|
| `GET /health` | 200 | `{"status":"ok"}` |
| `GET /notes` | 200 | `{"notes":[<note> x 20]}`, newest first by id |
| `GET /notes/:id` | 200 | `{"note":<note>}` |
| `POST /notes` with `Authorization: Bearer <users.token>` and `{"body":"..."}` | 201 | `{"note":<note>}`, body trimmed |

## Errors
| Condition | Status | Body |
|---|---|---|
| `:id` is not a positive integer (`0`, `-1`, `abc`, `1.5`) | 400 | `{"error":"invalid id"}` |
| no such note, or unknown path | 404 | `{"error":"not found"}` |
| POST with no bearer token, or one not in `users` (checked first) | 401 | `{"error":"unauthorized"}` |
| request body is not valid JSON | 400 | `{"error":"bad json"}` |
| `body` missing, not a string, empty after trimming, or over 500 characters after trimming | 400 | `{"error":"invalid body"}` |

## Rules
1. **The database is that SQLite file**, used in-process. No other database, cache server or external service.
2. **No caching across requests.** Every request reads its data from SQLite while being served, including the token check. SQLite's own page cache and mmap are fine.
3. **Writes are durable before you respond.** A 201 means the row is committed: WAL with `synchronous=NORMAL` or stronger.
4. No hard-coded responses and no detecting the load test.
5. Nothing on the box gets tuned for you: no kernel settings. Settings inside your own process are fair game.

## What a user does
`yuk.js`: a user clicks once every 5 to 15 seconds, so **10 users = about 1 request per second**. Of the clicks, 70 % list the newest notes, 20 % read one random note, 10 % write a note.

## Passing
A number of users passes if it holds for 5 minutes with p95 under 1 second and under 1 % errors, and the server is still alive at the end.
