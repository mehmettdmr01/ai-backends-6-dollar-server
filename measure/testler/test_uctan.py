"""The whole of arama.py end to end with fake k6, vmstat, systemctl, journalctl, sqlite3 and box scripts. No SSH, no network.
This proves the plumbing and the decisions, not how anything behaves on real Linux."""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
R = Path(__file__).resolve().parent.parent

def tool(path, body):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text("#!/usr/bin/env bash\n" + body + "\n"); path.chmod(0o755)

def scenario(limit=13000, oom=False, k6dead=False, idle=70, test_rc=0, nostart=False, gens=1, hidden_rc=0, lost=False, under=False, extra=()):
    t = Path(tempfile.mkdtemp()); root, olcum, bin_, flag = t / "root", t / "olcum", t / "bin", t / "oomflag"
    tool(root / "bench/sec.sh", f'echo "$@" > {t}/sec.args')
    tool(root / "bench/fresh.sh", f"rm -f {flag} {t}/ramp_info; " + ('echo "no healthy"; exit 1' if nostart else "echo healthy"))
    (root / "bench/izle.py").write_text('import sys,time\nf=open(sys.argv[1],"w",buffering=1)\nf.write("t,mem_avail_mb,app_total_mb,app_anon_mb,tcp_inuse,conntrack,cpu_idle,cpu_steal,cpu_iowait\\n")\nf.write(f"{time.time()},700,120,100,50,,40,1,0\\n")\ntime.sleep(1000)\n')
    (root / "bench/gizli_test.py").write_text(f'import sys\nprint("{{}}")\nsys.exit({hidden_rc})\n')
    (root / "bench/test_api.py").write_text(f'import sys\nprint("passed=28 failed=0")\nsys.exit({test_rc})\n')
    # A canary that breaks at limit/target of the way through, on the same clock as the fake k6.
    (olcum / "prob.py").parent.mkdir(parents=True, exist_ok=True)
    (olcum / "prob.py").write_text(f'''import sys,time,os
out=open(sys.argv[2],"w",buffering=1)
while True:
    time.sleep(0.05)
    if os.path.exists("{t}/ramp_info") and os.path.getsize("{t}/ramp_info"): break
t0,target,ramp=open("{t}/ramp_info").read().split()
t0=float(t0);target=int(target);ramp=int(ramp)
for i in range(ramp*5):
    tt=t0+i/5
    users=target*i/5/ramp
    bad=users>={limit}
    out.write(f"{{tt:.3f}},{{1500.0 if bad else 20.0}},200\\n")
time.sleep(1000)
''')
    tool(bin_ / "vmstat", f'sleep 0.3; echo "procs ---"; echo " r b swpd free buff cache si so bi bo in cs us sy id wa st gu"; echo " 1 0 0 8000000 100000 2000000 0 0 0 0 1 1 20 10 {idle} 0 0 0"')
    tool(bin_ / "systemctl", f'[ -f {flag} ] && echo failed || echo active')
    tool(bin_ / "journalctl", f'[ -f {flag} ] && echo "kernel: Out of memory: Killed process 812 (node)"; true')
    tool(bin_ / "sqlite3", f'[ -f {t}/created ] && c=$(cat {t}/created) || c=0; echo $((1000000 + c {"- 5" if lost else ""}))')
    tool(bin_ / "k6", f'''
out=""; vus=0; ramp=0; hold=0; prev=""
for a in "$@"; do [ "$prev" = "--summary-export" ] && out="$a"
  case "$a" in VUS=*) vus="${{a#VUS=}}";; RAMP=*) ramp="${{a#RAMP=}}"; ramp="${{ramp%s}}";; HOLD=*) hold="${{a#HOLD=}}"; hold="${{hold%s}}";; esac; prev="$a"; done
{"exit 1" if k6dead else ""}
now=$(python3 -c 'import time;print(time.time())')
echo "time=x level=info msg=\\"RAMP_START $now\\" source=console" >&2
sleep 1.6
[ "$hold" -le 1 ] && echo "$now $((vus * {gens})) $ramp" > {t}/ramp_info
sleep 0.5
total=$((vus * {gens}))
if [ "$total" -le {limit} ]; then p95=200; else p95=2000; {f"touch {flag};" if oom else ""} fi
req=$(python3 -c "print(int({0.5 if under else 1.0} * $vus / 10 * ($hold + $ramp / 2)))")
echo 500 > {t}/created
echo "{{\\"metrics\\":{{\\"http_req_duration\\":{{\\"p(95)\\":$p95,\\"p(99)\\":$((p95*2))}},\\"http_req_failed\\":{{\\"value\\":0}},\\"http_reqs\\":{{\\"rate\\":500,\\"count\\":$req}},\\"notes_created\\":{{\\"count\\":$((500 / {gens}))}}}}}}" > "$out"
''')
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}")
    argv = [sys.executable, str(R / "arama.py"), "--target", "local", "--target-ip", "127.0.0.1", "--name", "x", "--tier", "t", "--out", str(t / "out"), "--root", str(root), "--olcum", str(olcum),
            "--ramp-seconds", "200", "--hold-seconds", "60", "--first", "20000", "--cap", "120000"] + ["--gen", "local"] * gens + list(extra)
    r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=240)
    res = json.load(open(t / "out/t/x/sonuc.json")); p = t / "out/t/x/kosular.json"; runs = json.load(open(p)) if p.exists() else []
    return r, res, runs, t

r, res, runs, t = scenario()
assert r.returncode == 0, r.stdout + r.stderr
assert res["status"] == "scored" and 9000 <= res["score"] <= 13000 and res["test_passed"] and res["hidden_passed"], res
assert runs[0]["kind"] == "ramp" and runs[0]["knee"] and runs[0]["ramp_start"] and runs[-1]["kind"] == "hold" and runs[-1]["passed"], runs[0]
assert (t / "out/t/x" / (runs[0]["run"] + ".prob.csv")).exists() and (t / "out/t/x" / (runs[-1]["run"] + ".csv")).exists()
assert (t / "sec.args").read_text().split() == ["x"]
print("clean run:", res["score"], "knee", res["knee"], len(runs), "runs")
r, res, runs, _ = scenario(limit=5000, oom=True)
assert res["status"] == "scored" and res["score"] <= 5000 and runs[0]["why"] == "oom" and runs[0]["kernel"], runs[0]
print("oom named in the rise:", res["score"])
r, res, runs, _ = scenario(k6dead=True)
assert r.returncode == 3 and res["status"].startswith("aborted") and res["score"] is None, (r.returncode, res)
print("dead k6 aborts instead of scoring 0")
r, res, runs, _ = scenario(idle=10)
assert r.returncode == 3 and "saturated" in res["status"] and res["score"] is None, res
print("saturated generator aborts")
r, res, runs, _ = scenario(under=True)
assert r.returncode == 3 and "delivered" in res["status"] and res["score"] is None, res
print("a pass with too few requests aborts")
r, res, runs, _ = scenario(lost=True)
assert r.returncode == 0 and any(x["why"] == "lost-writes" for x in runs) and res["score"] == 0, res
print("lost writes fail the hold")
r, res, runs, _ = scenario(extra=["--no-preflight", "--no-db-check"], lost=True)
assert r.returncode == 0 and res["score"] > 0 and "test_passed" not in res, res
print("the calibration server skips the database checks")
r, res, runs, _ = scenario(test_rc=1)
assert r.returncode == 2 and res["status"] == "failed-test" and not runs, res
print("test_api failure stops before load")
r, res, runs, _ = scenario(hidden_rc=1)
assert r.returncode == 0 and res["hidden_passed"] is False and res["score"] > 0, res
print("hidden test failure is recorded, measured anyway")
r, res, runs, _ = scenario(nostart=True)
assert r.returncode == 2 and res["status"] == "no-start" and "no healthy" in res["detail"], (r.returncode, res)
print("a contestant that cannot boot is recorded as that")
r, res, runs, _ = scenario(limit=13000, gens=2)
assert res["status"] == "scored" and 9000 <= res["score"] <= 13000, res
print("two generators split the users:", res["score"])
print("ok")
