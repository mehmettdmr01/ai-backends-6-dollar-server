#!/usr/bin/env python3
"""Builds seed/notes.db and seed/tokens.json. Deterministic: the same files on every machine. About 290 MB.
  seed.py <out-dir>"""
import json, random, sqlite3, sys, hashlib
from pathlib import Path
SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, token TEXT NOT NULL UNIQUE);
CREATE TABLE notes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 500),
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE INDEX notes_user_id_idx ON notes (user_id);
"""
USERS, NOTES = 20_000, 1_000_000
WORDS = ("server memory disk cpu kernel request database cache index query latency socket thread process commit "
         "morning coffee project deploy release bug test review branch merge small cheap fast slow simple honest "
         "today tomorrow again never always maybe really just because while after before note idea list").split()
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
db = out / "notes.db"
for f in (db, out / "notes.db-wal", out / "notes.db-shm"):
    f.unlink(missing_ok=True)
r = random.Random(42)
con = sqlite3.connect(db)
con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
users = [(i, f"user{i}", "%032x" % r.getrandbits(128)) for i in range(1, USERS + 1)]
con.executemany("INSERT INTO users VALUES (?,?,?)", users)
def note(i):
    n = r.randint(20, 55)
    body = " ".join(r.choice(WORDS) for _ in range(n))[:500]
    sec = 1735689600 + i * 31                      # spread over about a year, always increasing
    from_ts = "%d-%02d-%02dT%02d:%02d:%02d.%03dZ" % (2025 + sec // 40000000 % 2, 1 + sec % 12, 1 + sec % 28, sec % 24, sec % 60, (sec // 7) % 60, sec % 1000)
    return (i, 1 + int(USERS * r.random() * r.random()), body, from_ts)
con.executemany("INSERT INTO notes VALUES (?,?,?,?)", (note(i) for i in range(1, NOTES + 1)))
con.commit()
con.executescript("ANALYZE; VACUUM; PRAGMA journal_mode=WAL;")
con.execute("PRAGMA wal_checkpoint(TRUNCATE)"); con.close()
(out / "tokens.json").write_text(json.dumps([{"id": i, "username": u, "token": t} for i, u, t in users]))
con = sqlite3.connect(db)
h = hashlib.sha256()
for row in con.execute("SELECT id,user_id,body,created_at FROM notes ORDER BY id"):
    h.update(repr(row).encode())
print(f"{db}: {db.stat().st_size // (1024*1024)} MB, content sha256 {h.hexdigest()}")
