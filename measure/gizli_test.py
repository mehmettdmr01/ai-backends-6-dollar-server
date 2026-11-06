#!/usr/bin/env python3
"""The hidden test. Contestants never see it. It catches the ways to win a load test by breaking the rules:
  no-cache:  a row changed straight in SQLite, behind the server's back, must show up in the very next request.
  tokens:    a token changed in SQLite must take effect at once, both ways (remembered checks, preloaded lists).
  durable:   while writers are running, kill -9 the server. Every note that got a 201 must be in the database.
Standard library only.
  gizli_test.py --base http://127.0.0.1:80 --db /srv/data/notes.db --tokens tokens.json \
                --kill "systemctl kill -s KILL yarisma" --restart "systemctl start yarisma"
Run against a server started on a fresh database, never before a load run."""
import argparse, http.client, json, sqlite3, subprocess, threading, time
from urllib.parse import urlparse


class Client:
    def __init__(self, base):
        u = urlparse(base)
        self.c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=10)

    def req(self, method, path, body=None, token=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        self.c.request(method, path, json.dumps(body) if body is not None else None, h)
        r = self.c.getresponse()
        raw = r.read()
        return r.status, json.loads(raw) if raw else None


def db(path):
    return sqlite3.connect(path, timeout=30)


def no_cache(o):
    fails = []
    c = Client(o.base)
    for _ in range(50):                     # warm whatever a cheater might have warmed
        c.req("GET", "/notes"); c.req("GET", "/notes/1")
    con = db(o.db)
    with con:
        con.execute("UPDATE notes SET body = 'hidden-edit' WHERE id = 1")
    _, d = c.req("GET", "/notes/1")
    if d["note"]["body"] != "hidden-edit":
        fails.append("a direct edit was not seen on /notes/1")
    with con:
        new = con.execute("INSERT INTO notes (user_id, body) VALUES (1, 'hidden-note') RETURNING id").fetchone()[0]
    _, d = c.req("GET", "/notes")
    if d["notes"][0]["id"] != new:
        fails.append(f"a direct insert was not on top of /notes: top is {d['notes'][0]['id']}, want {new}")
    con.close()
    return fails


def tokens_live(o):
    fails = []
    c = Client(o.base)
    con = db(o.db)
    with con:
        con.execute("INSERT INTO users (username, token) VALUES ('hidden-user', 'hidden-token-1')")
    status, _ = c.req("POST", "/notes", {"body": "x"}, "hidden-token-1")
    if status != 201:
        fails.append(f"a token added after startup was refused: {status}")
    for _ in range(20):                     # plenty of chances to remember it
        c.req("POST", "/notes", {"body": "x"}, "hidden-token-1")
    with con:
        con.execute("UPDATE users SET token = 'hidden-token-2' WHERE token = 'hidden-token-1'")
    status, _ = c.req("POST", "/notes", {"body": "x"}, "hidden-token-1")
    if status != 401:
        fails.append(f"a revoked token was still accepted: {status}")
    con.close()
    return fails


def durable(o, tokens, threads=8, seconds=3.0):
    acked, lock, stop = [], threading.Lock(), threading.Event()

    def writer(i):
        c = Client(o.base)
        tok = tokens[i % len(tokens)]["token"]
        n = 0
        while not stop.is_set():
            body = f"durable-{i}-{n}"
            n += 1
            try:
                status, doc = c.req("POST", "/notes", {"body": body}, tok)
            except Exception:
                return                      # the server is gone: whatever got a 201 is what we check
            if status == 201:
                with lock:
                    acked.append((doc["note"]["id"], body))

    ts = [threading.Thread(target=writer, args=(i,)) for i in range(threads)]
    [t.start() for t in ts]
    time.sleep(seconds)
    subprocess.run(o.kill, shell=True)   # systemd can report an error for helper processes even when the kill worked
    time.sleep(0.5)
    stop.set()
    [t.join() for t in ts]
    if not acked:
        return ["no write was acknowledged, so the test proves nothing"], 0, 0
    con = db(o.db)
    missing = [(i, b) for i, b in acked if (con.execute("SELECT body FROM notes WHERE id = ?", (i,)).fetchone() or [None])[0] != b]
    con.close()
    fails = [f"{len(missing)} of {len(acked)} acknowledged notes lost, for example {missing[0]}"] if missing else []
    subprocess.run(o.restart, shell=True, check=True)
    for _ in range(60):
        try:
            if Client(o.base).req("GET", "/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        fails.append("server did not come back healthy after the restart")
    return fails, len(acked), len(missing)


def main():
    a = argparse.ArgumentParser()
    for f in ("base", "db", "tokens", "kill", "restart"):
        a.add_argument("--" + f, required=True)
    o = a.parse_args()
    tokens = json.load(open(o.tokens))
    r = {"no_cache": no_cache(o), "tokens": tokens_live(o)}
    r["durable"], r["acked"], r["lost"] = durable(o, tokens)
    r["passed"] = not r["no_cache"] and not r["tokens"] and not r["durable"]
    print(json.dumps(r, indent=1))
    raise SystemExit(0 if r["passed"] else 1)


if __name__ == "__main__":
    main()
