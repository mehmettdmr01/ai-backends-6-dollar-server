#!/usr/bin/env python3
"""Does a server follow SPEC.md? Run it on a fresh database. Contestants see this one.
  test_api.py http://127.0.0.1:80 seed/tokens.json"""
import http.client, json, re, sys
from urllib.parse import urlparse
BASE, TOKENS = sys.argv[1], json.load(open(sys.argv[2]))
u = urlparse(BASE); conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=15)
T, NAME = TOKENS[0]["token"], TOKENS[0]["username"]
passed = failed = 0

def req(method, path, raw=None, token=None):
    h = {}
    if raw is not None: h["Content-Type"] = "application/json"
    if token: h["Authorization"] = token
    conn.request(method, path, raw, h)
    r = conn.getresponse(); body = r.read().decode()
    return r.status, body, r.getheader("Content-Type") or ""

def ok(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1; print("  ok  ", name)
    else: failed += 1; print("  FAIL", name, detail)

def want(name, got, status, body):
    ok(name, got[0] == status and got[1].strip() == body, f"want {status} {body}, got {got[0]} {got[1][:200]}")

NOTE = re.compile(r'^\{"id":\d+,"author":"[^"]+","body":".*","created_at":"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z"\}$')
want("health", req("GET", "/health"), 200, '{"status":"ok"}')
s, b, c = req("GET", "/notes")
ok("list is 200 JSON", s == 200 and c.startswith("application/json"), f"{s} {c}")
d = json.loads(b); ids = [n["id"] for n in d["notes"]]
ok("list has 20 notes", len(ids) == 20, len(ids))
ok("list is newest first", ids == sorted(ids, reverse=True) and ids[0] == 1000000, ids[:3])
ok("list is compact with keys in order", b.strip().startswith('{"notes":[{"id":') and NOTE.match(json.dumps(d["notes"][0], separators=(",", ":"), ensure_ascii=False)) is not None and '", "' not in b[:200])
s, b, c = req("GET", "/notes/1")
ok("one note", s == 200 and NOTE.match(json.dumps(json.loads(b)["note"], separators=(",", ":"), ensure_ascii=False)) is not None and b.strip().startswith('{"note":{"id":1,"author":'), b[:200])
ok("one note has its bytes as stored", json.loads(b)["note"]["created_at"].endswith("Z"))
for bad in ("0", "-1", "abc", "1.5"):
    want(f"GET /notes/{bad}", req("GET", f"/notes/{bad}"), 400, '{"error":"invalid id"}')
want("missing note", req("GET", "/notes/999999999"), 404, '{"error":"not found"}')
want("unknown path", req("GET", "/nope"), 404, '{"error":"not found"}')
A = "Bearer " + T
want("no token", req("POST", "/notes", '{"body":"x"}'), 401, '{"error":"unauthorized"}')
want("not bearer", req("POST", "/notes", '{"body":"x"}', "Basic abc"), 401, '{"error":"unauthorized"}')
want("unknown token", req("POST", "/notes", '{"body":"x"}', "Bearer nosuchtoken"), 401, '{"error":"unauthorized"}')
want("auth before body", req("POST", "/notes", "{bad", "Bearer nosuchtoken"), 401, '{"error":"unauthorized"}')
want("bad json", req("POST", "/notes", "{bad", A), 400, '{"error":"bad json"}')
for name, raw in (("empty", '{"body":""}'), ("spaces", '{"body":"   "}'), ("number", '{"body":123}'), ("missing", "{}"), ("501 chars", json.dumps({"body": "a" * 501}))):
    want(f"body {name}", req("POST", "/notes", raw, A), 400, '{"error":"invalid body"}')
s, b, c = req("POST", "/notes", json.dumps({"body": "  " + "b" * 500 + " "}), A)
n = json.loads(b).get("note", {}) if s == 201 else {}
ok("500 chars accepted and trimmed", s == 201 and n.get("body") == "b" * 500 and n.get("author") == NAME, f"{s} {b[:200]}")
ok("created_at is in the stored format", re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$", n.get("created_at", "")) is not None, n)
s, b2, _ = req("GET", f"/notes/{n.get('id')}")
ok("read back", s == 200 and json.loads(b2)["note"] == n, b2[:200])
s, b3, _ = req("GET", "/notes")
ok("new note on top of the list", json.loads(b3)["notes"][0] == n, b3[:200])
s, b4, _ = req("POST", "/notes", json.dumps({"body": 'caf\u00e9 "quoted" <b> \u2713'}), A)
ok("special characters round-trip", s == 201 and json.loads(b4)["note"]["body"] == 'caf\u00e9 "quoted" <b> \u2713', b4[:200])
print(f"passed={passed} failed={failed}")
sys.exit(1 if failed else 0)
