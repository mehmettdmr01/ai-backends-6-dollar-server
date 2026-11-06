"""A reference server for testing the tests, standard library only. mode: honest, cache, ackfirst, tokenmemo, tokenlist.
Every mode except honest breaks one rule of SPEC.md, on purpose."""
import http.server, json, re, sqlite3, sys, threading, time
mode, path, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
con = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
con.execute("PRAGMA journal_mode=WAL"); con.execute("PRAGMA synchronous=NORMAL")
lock = threading.Lock(); pending = []; cache = {}; remembered = {}
known = dict((t, (i, u)) for i, u, t in con.execute("SELECT id, username, token FROM users")) if mode == "tokenlist" else {}
NOTE = "SELECT n.id, u.username, n.body, n.created_at FROM notes n JOIN users u ON u.id = n.user_id "
obj = lambda r: {"id": r[0], "author": r[1], "body": r[2], "created_at": r[3]}
def flusher():
    while True:
        time.sleep(1.0)
        with lock:
            for b in pending: con.execute("INSERT INTO notes (id, user_id, body) VALUES (?,?,?)", b)
            pending.clear()
if mode == "ackfirst": threading.Thread(target=flusher, daemon=True).start()
next_id = [0]
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def out(self, s, d):
        b = json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode()
        self.send_response(s); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/health": return self.out(200, {"status": "ok"})
        if mode == "cache" and self.path in cache: return self.out(200, cache[self.path])
        if self.path == "/notes":
            with lock: d = {"notes": [obj(r) for r in con.execute(NOTE + "ORDER BY n.id DESC LIMIT 20")]}
        elif self.path.startswith("/notes/"):
            raw = self.path[7:]
            if not re.fullmatch(r"[1-9]\d*", raw): return self.out(400, {"error": "invalid id"})
            with lock: r = con.execute(NOTE + "WHERE n.id = ?", (int(raw),)).fetchone()
            if not r: return self.out(404, {"error": "not found"})
            d = {"note": obj(r)}
        else: return self.out(404, {"error": "not found"})
        cache[self.path] = d; self.out(200, d)
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/notes": return self.out(404, {"error": "not found"})
        h = self.headers.get("Authorization", "")
        t = h[7:] if h.startswith("Bearer ") else ""
        with lock:
            if mode == "tokenlist": who = known.get(t)
            elif mode == "tokenmemo" and t in remembered: who = remembered[t]
            else: who = con.execute("SELECT id, username FROM users WHERE token = ?", (t,)).fetchone()
        if not who: return self.out(401, {"error": "unauthorized"})
        remembered[t] = who
        try: doc = json.loads(raw)
        except ValueError: return self.out(400, {"error": "bad json"})
        b = doc.get("body") if isinstance(doc, dict) else None
        b = b.strip() if isinstance(b, str) else ""
        if not b or len(b) > 500: return self.out(400, {"error": "invalid body"})
        with lock:
            if mode == "ackfirst":
                next_id[0] = max(next_id[0], con.execute("SELECT max(id) FROM notes").fetchone()[0]) + 1
                pending.append((next_id[0], who[0], b)); i, at = next_id[0], "2026-11-05T00:00:00.000Z"
            else:
                i, at = con.execute("INSERT INTO notes (user_id, body) VALUES (?,?) RETURNING id, created_at", (who[0], b)).fetchone()
        self.out(201, {"note": {"id": i, "author": who[1], "body": b, "created_at": at}})
http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
