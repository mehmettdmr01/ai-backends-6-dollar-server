"""seed.py, test_api.py and gizli_test.py against the reference server: the honest one must pass, each cheat must be caught."""
import json, os, shutil, signal, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path
R = Path(__file__).resolve().parent.parent; PY = sys.executable
seed = Path(tempfile.mkdtemp()); out = subprocess.run([PY, "-I", str(R / "seed.py"), str(seed)], capture_output=True, text=True, check=True).stdout; print(out.strip())
con = sqlite3.connect(seed / "notes.db")
assert con.execute("select count(*) from notes").fetchone()[0] == 1000000 and con.execute("select count(*) from users").fetchone()[0] == 20000
assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"; con.close()
assert 180 <= (seed / "notes.db").stat().st_size // (1024 * 1024) <= 320, (seed / "notes.db").stat().st_size
other = Path(tempfile.mkdtemp()); out2 = subprocess.run([PY, "-I", str(R / "seed.py"), str(other)], capture_output=True, text=True, check=True).stdout
assert out.split()[-1] == out2.split()[-1], "seed is not deterministic"; shutil.rmtree(other); print("seed deterministic")
def fresh():
    d = Path(tempfile.mkdtemp()); shutil.copy(seed / "notes.db", d / "notes.db"); return d
def serve(mode, d, port):
    return [PY, "-I", str(R / "testler/ref_sunucu.py"), mode, str(d / "notes.db"), str(port)]
def up(port):
    import http.client
    for _ in range(200):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=1); c.request("GET", "/health"); c.getresponse().read(); return
        except OSError: time.sleep(0.1)
    raise SystemExit("server did not start")
def api(mode, port):
    d = fresh(); p = subprocess.Popen(serve(mode, d, port)); up(port)
    r = subprocess.run([PY, "-I", str(R / "test_api.py"), f"http://127.0.0.1:{port}", str(seed / "tokens.json")], capture_output=True, text=True)
    p.kill(); p.wait(); shutil.rmtree(d); return r
def hidden(mode, port):
    d = fresh(); s = serve(mode, d, port); p = subprocess.Popen(s); up(port); pid = d / "pid"; pid.write_text(str(p.pid))
    restart = f"nohup {' '.join(s)} >/dev/null 2>&1 & echo $! > {pid}"
    r = subprocess.run([PY, "-I", str(R / "gizli_test.py"), "--base", f"http://127.0.0.1:{port}", "--db", str(d / "notes.db"), "--tokens", str(seed / "tokens.json"),
                        "--kill", f"kill -9 $(cat {pid})", "--restart", restart], capture_output=True, text=True)
    try: os.kill(int(pid.read_text()), signal.SIGKILL)
    except OSError: pass
    p.wait(); shutil.rmtree(d); return r.returncode, json.loads(r.stdout)
r = api("honest", 39020); assert r.returncode == 0, r.stdout; print(r.stdout.strip().splitlines()[-1])
code, h = hidden("honest", 39021); assert code == 0 and h["acked"] > 20 and h["lost"] == 0, h; print("honest passes the hidden test:", h["acked"], "acked")
code, h = hidden("cache", 39022); assert code == 1 and h["no_cache"] and not h["durable"], h; print("cache caught:", h["no_cache"][0])
code, h = hidden("ackfirst", 39023); assert code == 1 and h["durable"] and 0 < h["lost"] < h["acked"], h; print("ack-before-commit caught:", h["durable"][0])
code, h = hidden("tokenmemo", 39024); assert code == 1 and h["tokens"], h; print("remembered token caught:", h["tokens"][0])
code, h = hidden("tokenlist", 39025); assert code == 1 and h["tokens"], h; print("token list caught:", h["tokens"][0])
shutil.rmtree(seed); print("ok")
