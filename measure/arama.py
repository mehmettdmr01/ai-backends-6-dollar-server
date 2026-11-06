#!/usr/bin/env python3
"""How many users does a contestant hold? First test_api.py and the hidden test. Then one run with the load rising
for 10 minutes, watched by a canary user, which shows where it starts to hurt. Then a 5-minute hold at 90 % of that,
stepping down 10 % until one passes. Every run restarts the app on a fresh database. Score = users in the passed hold.
So a score can sit up to about 10 % below the true limit.
Pass = p95 < 1 s, errors < 1 %, the kernel killed nothing, the app is alive at the end, and no acknowledged write is
missing from the database. A kernel line such as "conntrack table full" only names the cause of a failure.
The search stops rather than score a run if k6 produced no result, a generator was saturated, or a passing run
delivered far fewer requests than its users should have made.

  arama.py --target root@10.0.0.2 --target-ip 10.0.0.2 --gen local --name node-express-tutorial --tier do-6
Run it inside tmux on a load generator, so a sleeping laptop cannot break a run.
Exit codes: 0 scored, 2 failed before any load, 3 aborted (fix the setup and rerun)."""
import argparse, csv, io, json, re, shlex, subprocess, sys, time
from pathlib import Path

P95, ERR = 1000.0, 0.01
GEN_MIN_IDLE, GEN_MIN_FREE_MB, MAX_USERS_PER_GEN, STEAL_HIGH = 20, 1024, 60000, 3.0
SEED_NOTES, CYCLE_S, RAMP_S, HOLD_RAMP_S, HOLD_S = 1_000_000, 10.0, 600, 60, 300
KERNEL = r"Out of memory|oom-kill|Killed process|nf_conntrack: table full|possible SYN flooding|TCP: out of memory|too many orphaned"
SSH = ["ssh", "-o", "ServerAliveInterval=30", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
       "-o", "ControlPath=/tmp/v7-%C", "-o", "ControlMaster=no"]


class Abort(Exception):
    """The setup is broken, not the contestant. Nothing measured from here on would be true."""


def search(ramp, hold, first=25000, cap=25000, margin=0.9, max_holds=6):
    """ramp(target) -> users where it broke, or None. hold(users) -> bool. Returns (score, knee, history).
    Pure: no I/O of its own, so it can be tested."""
    hist, target, k = [], first, None
    while target <= cap:
        k = ramp(target)
        hist.append(("ramp", target, k))
        if k is not None:
            break
        target *= 2
    if k is None:
        k = cap                              # never broke: one 8 GB generator drives about 25,000 users, so the score is a floor
    elif k < target * 0.1 and k >= 100:      # a very slow contestant: the rise was too steep to read, look closer
        again = ramp(max(k * 3, 300))
        hist.append(("ramp", max(k * 3, 300), again))
        k = again if again is not None else k
    u = max(100, int(round(k * margin, -2)))
    for _ in range(max_holds):
        ok = hold(u)
        hist.append(("hold", u, ok))
        if ok:
            return u, k, hist
        if u <= 100:
            break
        u = max(100, min(u - 100, int(round(u * margin, -2))))
    return 0, k, hist


def knee(rows, t0, ramp_s, target, window=10, span=6, need=4):
    """rows: (t, ms, status) from the canary. Users at the start of the first bad 10-second window after which most of
    the next minute is bad too (need of span windows), or None. A short stall that recovers is not the break: the
    5-minute hold judges those. Near the end of the ramp, two thirds of the windows that are left must be bad."""
    wins = {}
    for t, ms, st in rows:
        if t0 <= t <= t0 + ramp_s:
            wins.setdefault(int((t - t0) // window), []).append((ms, st))
    def bad(w):
        v = wins.get(w)
        if not v:
            return False
        lat = sorted(m for m, _ in v)
        return lat[int(0.95 * (len(lat) - 1))] >= P95 or sum(1 for _, s in v if s == 0 or s >= 400) / len(v) >= ERR
    last = max(wins) if wins else -1
    for w in sorted(wins):
        if not bad(w):
            continue
        ahead = [x for x in range(w, w + span) if x <= last]
        hits = sum(1 for x in ahead if bad(x))
        if (len(ahead) == span and hits >= need) or (len(ahead) < span and len(ahead) >= 3 and hits * 3 >= len(ahead) * 2):
            return int(target * min(1.0, w * window / ramp_s))
    return None


def parse_probe(text):
    rows = []
    for line in text.splitlines():
        p = line.split(",")
        if len(p) == 3:
            rows.append((float(p[0]), float(p[1]), int(p[2])))
    return rows


def parse_summary(doc):
    """Metrics from a k6 --summary-export JSON."""
    m = doc["metrics"]
    d, f, r = m["http_req_duration"], m["http_req_failed"], m["http_reqs"]
    err = f.get("value", f.get("rate"))
    return {"p95": d["p(95)"], "p99": d["p(99)"], "err": err, "rps": r["rate"], "requests": r["count"], "created": m.get("notes_created", {}).get("count", 0)}


def merge(parts):
    """Several generators: a run passes only if it passes on every one."""
    return {"p95": max(p["p95"] for p in parts), "p99": max(p["p99"] for p in parts), "err": max(p["err"] for p in parts),
            "rps": sum(p["rps"] for p in parts), "requests": sum(p["requests"] for p in parts), "created": sum(p["created"] for p in parts)}


def verdict(k, alive, kernel_lines, new_rows=None):
    """Why a run failed, most physical cause first. None means it passed. new_rows None means the check does not apply."""
    text = "\n".join(kernel_lines)
    if re.search(r"Out of memory|oom-kill|Killed process", text):
        return "oom"
    if not alive:
        return "crash"
    if k is None:
        return "no-result"
    if new_rows is not None and new_rows < k["created"]:
        return "lost-writes"
    numeric = "errors" if k["err"] >= ERR else "p95" if k["p95"] >= P95 else None
    if numeric and "nf_conntrack: table full" in text:
        return "conntrack"
    return numeric


def expected_requests(users, ramp_s, hold_s):
    return users / CYCLE_S * (hold_s + ramp_s / 2)


def generator_load(vmstat, since=None, until=None, frac=0.10):
    """A run is only valid if the load generator was not the bottleneck. Lines are '<epoch> <vmstat row>', each row an
    average over the 4 seconds after its epoch. Rows before the load started are skipped (k6 preparing its users), and
    in a ramp so are rows after the break: once the contestant is down, a busy generator changes nothing. A few busy
    seconds are k6 cleaning up its memory; the generator counts as saturated only if more than frac of the rows are."""
    rows = []
    for l in vmstat.splitlines():
        p = l.split()
        if len(p) > 16 and p[0].isdigit() and p[1].isdigit() and (since is None or int(p[0]) >= since) and (until is None or int(p[0]) <= until):
            rows.append(p[1:])
    if not rows:
        return {"min_free_mb": None, "min_idle": None, "busy_share": None, "limited": True}
    free = min((int(r[3]) + int(r[5])) // 1024 for r in rows)
    idles = [int(r[14]) for r in rows]
    busy = sum(1 for i in idles if i < GEN_MIN_IDLE) / len(idles)
    return {"min_free_mb": free, "min_idle": min(idles), "busy_share": round(busy, 3), "limited": free < GEN_MIN_FREE_MB or busy > frac}


def csv_summary(text, t0):
    """What the box did during a run. The mean values skip the first 60 seconds when there is anything after them."""
    rows = list(csv.DictReader(io.StringIO(text)))
    steady = [r for r in rows if r["t"] and float(r["t"]) >= t0 + 60] or rows
    nums = lambda rs, k: [float(r[k]) for r in rs if r.get(k) not in (None, "")]
    mean = lambda v: round(sum(v) / len(v), 1) if v else None
    return {"samples": len(rows), "min_mem_avail_mb": min(nums(rows, "mem_avail_mb"), default=None), "peak_app_mb": max(nums(rows, "app_total_mb"), default=None),
            "peak_app_anon_mb": max(nums(rows, "app_anon_mb"), default=None), "peak_tcp": max(nums(rows, "tcp_inuse"), default=None),
            "peak_conntrack": max(nums(rows, "conntrack"), default=None), "mean_idle": mean(nums(steady, "cpu_idle")),
            "mean_steal": mean(nums(steady, "cpu_steal")), "mean_iowait": mean(nums(steady, "cpu_iowait"))}


def sh(host, cmd, check=True):
    if host == "local":
        r = subprocess.run(["bash", "-c", cmd], text=True, capture_output=True)
    else:
        for _ in range(5):                   # 255 is ssh's own failure, never the contestant's
            r = subprocess.run(SSH + [host, cmd], text=True, capture_output=True)
            if r.returncode != 255:
                break
            time.sleep(10)
        else:
            raise Abort(f"ssh to {host} keeps failing: {r.stderr[:300]}")
    if check and r.returncode:
        raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, r.stderr)
    return r


def open_master(host):
    """One connection opened before any load, so reaching an overloaded box afterwards needs no new handshake.
    Its output goes to /dev/null: a backgrounded master holding our pipe would hang capture_output forever."""
    if host != "local":
        subprocess.run(SSH[:-2] + ["-M", "-N", "-f", "-o", "ControlPersist=yes", host],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def close_master(host):
    if host != "local":
        subprocess.run(SSH[:-2] + ["-O", "exit", host], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--target", required=True); a.add_argument("--target-ip", required=True)
    a.add_argument("--gen", action="append", required=True); a.add_argument("--name", required=True); a.add_argument("--tier", required=True)
    a.add_argument("--out", default="sonuc"); a.add_argument("--root", default="/srv"); a.add_argument("--olcum", default="/srv/olcum")
    a.add_argument("--first", type=int, default=25000); a.add_argument("--cap", type=int, default=25000); a.add_argument("--no-preflight", action="store_true"); a.add_argument("--no-db-check", action="store_true")
    a.add_argument("--ramp-seconds", type=int, default=RAMP_S); a.add_argument("--hold-seconds", type=int, default=HOLD_S)
    o = a.parse_args()
    out = Path(o.out) / o.tier / o.name
    out.mkdir(parents=True, exist_ok=True)
    bench = f"{o.root}/bench"
    log, result = [], dict(name=o.name, tier=o.tier, score=None, status="running")

    def save():
        (out / "kosular.json").write_text(json.dumps(log, indent=1))
        (out / "sonuc.json").write_text(json.dumps(result, indent=1))

    def run(kind, users, ramp_s, hold_s):
        rid = f"{len(log):02d}-{kind}-{users}"
        tmp = f"/tmp/{o.tier}-{o.name}-{rid}"
        share = users // len(o.gen)
        if share >= MAX_USERS_PER_GEN:
            raise Abort(f"{share} users per generator would run out of ports: add generators")
        try:
            sh(o.target, f"{bench}/fresh.sh")
        except subprocess.CalledProcessError as e:
            raise Abort(f"{rid}: fresh.sh failed, the app no longer boots: {(e.stdout or '')[-300:]}")
        sh(o.target, f"nohup python3 {bench}/izle.py {tmp}.csv >/dev/null 2>&1 & echo $! > /tmp/izle.pid")
        canary = o.gen[0]
        sh(canary, f"nohup python3 {o.olcum}/prob.py http://{o.target_ip}/notes {tmp}.prob >/dev/null 2>&1 & echo $! > {tmp}.probpid")
        t0 = time.time()
        procs = []
        for i, g in enumerate(o.gen):
            vus = share + (users - share * len(o.gen) if i == 0 else 0)
            cmd = (f"rm -f {tmp}-{i}.json; (while :; do echo \"$(date +%s) $(vmstat 4 2 | tail -1)\"; done) > {tmp}-{i}.vmstat & VM=$!; ulimit -n 500000; k6 run -q --summary-mode compact --summary-export {tmp}-{i}.json "
                   f"-e BASE_URL=http://{o.target_ip} -e VUS={vus} -e RAMP={ramp_s}s -e HOLD={hold_s}s -e TOKENS={o.olcum}/seed/tokens.json {o.olcum}/yuk.js > {tmp}-{i}.log 2>&1; kill $VM")
            argv = ["bash", "-c", cmd] if g == "local" else SSH + [g, cmd]
            procs.append((g, i, subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))
        for _, _, p in procs:
            p.wait()
        sh(canary, f"kill $(cat {tmp}.probpid) 2>/dev/null; true", check=False)
        sh(o.target, "kill $(cat /tmp/izle.pid) 2>/dev/null; true", check=False)
        alive = sh(o.target, "systemctl is-active yarisma", check=False).stdout.strip() == "active"
        klines = sh(o.target, f"journalctl -k --since @{int(t0) - 1} --no-pager | grep -iE {shlex.quote(KERNEL)} || true", check=False).stdout.splitlines()
        parts = []
        for g, i, _ in procs:
            try:
                parts.append(parse_summary(json.loads(sh(g, f"cat {tmp}-{i}.json", check=False).stdout)))
            except (ValueError, KeyError):
                parts = None
                break
        k = merge(parts) if parts else None
        starts = []
        for g, i, _ in procs:
            m = re.search(r"RAMP_START ([\d.]+)", sh(g, f"cat {tmp}-{i}.log", check=False).stdout)
            starts.append(float(m.group(1)) if m else None)
        vmstats = [sh(g, f"cat {tmp}-{i}.vmstat", check=False).stdout for g, i, _ in procs]
        gens = [generator_load(v, starts[i]) for i, v in enumerate(vmstats)]
        text = sh(o.target, f"cat {tmp}.csv", check=False).stdout
        (out / f"{rid}.csv").write_text(text)
        probe = sh(canary, f"cat {tmp}.prob", check=False).stdout
        (out / f"{rid}.prob.csv").write_text(probe)
        new_rows = None
        if not o.no_db_check:
            n = sh(o.target, f"sqlite3 {o.root}/data/notes.db 'select count(*) from notes'", check=False).stdout.strip()
            new_rows = int(n) - SEED_NOTES if n.isdigit() else None
        box = csv_summary(text, t0)
        why = verdict(k, alive, klines, new_rows)
        row = dict(run=rid, kind=kind, users=users, ramp_s=ramp_s, hold_s=hold_s, passed=why is None, why=why, alive=alive, k6=k, new_rows=new_rows, box=box, generators=gens,
                   steal_high=(box["mean_steal"] or 0) > STEAL_HIGH, kernel=klines[:20], t0=t0, ramp_start=starts[0], seconds=round(time.time() - t0))
        if k is None:
            log.append(row); save()
            raise Abort(f"{rid}: k6 produced no result, see {tmp}-*.log on the generator")
        row["_vmstats"], row["_starts"] = vmstats, starts
        return row, probe

    def check_generators(row, until=None):
        gens = [generator_load(v, row["_starts"][i], until) for i, v in enumerate(row.pop("_vmstats"))]
        row.pop("_starts")
        row["generators"], row["generator_window_end"] = gens, until
        if any(g["limited"] for g in gens):
            log.append(row); save()
            raise Abort(f"{row['run']}: load generator saturated {gens}: add generators, this run says nothing about the contestant")

    def do_ramp(target):
        row, probe = run("ramp", target, o.ramp_seconds, 1)
        start = row["ramp_start"] or row["t0"]
        at = knee(parse_probe(probe), start, o.ramp_seconds, target) if row["k6"] else None
        row["knee"] = at
        check_generators(row, None if at is None else start + at / target * o.ramp_seconds + 30)
        log.append(row); save()
        print(row["run"], "knee", at, row["why"], row["box"], flush=True)
        return at

    def do_hold(users):
        row, _ = run("hold", users, HOLD_RAMP_S, o.hold_seconds)
        check_generators(row)
        k = row["k6"]
        if row["passed"] and k["requests"] < 0.85 * expected_requests(users, HOLD_RAMP_S, o.hold_seconds):
            log.append(row); save()
            raise Abort(f"{row['run']}: passed but delivered {k['requests']} of about {expected_requests(users, HOLD_RAMP_S, o.hold_seconds):.0f} requests: the load is not what it claims")
        log.append(row); save()
        print(row["run"], "PASS" if row["passed"] else f"FAIL {row['why']}", row["k6"], row["box"], flush=True)
        return row["passed"]

    try:
        for h in {o.target, *o.gen}:
            open_master(h)
        sh(o.target, f"{bench}/sec.sh {shlex.quote(o.name)}")
        if not o.no_preflight:
            try:
                sh(o.target, f"{bench}/fresh.sh")
            except subprocess.CalledProcessError as e:   # on the smallest tier this can be the finding itself
                result.update(status="no-start", detail=(e.stdout or "")[-800:])
                save()
                print("did not boot:", (e.stdout or "")[-300:], flush=True)
                sys.exit(2)
            t = sh(o.target, f"python3 {bench}/test_api.py http://127.0.0.1:80 {o.root}/seed/tokens.json", check=False)
            (out / "test.txt").write_text(t.stdout + t.stderr)
            result["test_passed"] = t.returncode == 0
            if t.returncode:
                result["status"] = "failed-test"
                save()
                print("test_api FAILED, not load testing:", t.stdout[-400:], flush=True)
                sys.exit(2)
            sh(o.target, f"{bench}/fresh.sh")
            g = sh(o.target, f"python3 {bench}/gizli_test.py --base http://127.0.0.1:80 --db {o.root}/data/notes.db --tokens {o.root}/seed/tokens.json "
                             "--kill 'systemctl kill -s KILL yarisma' --restart 'systemctl start yarisma'", check=False)
            (out / "gizli.txt").write_text(g.stdout + g.stderr)
            result["hidden_passed"] = g.returncode == 0   # measured anyway, shown next to the score
            save()
        score, at, hist = search(do_ramp, do_hold, first=o.first, cap=o.cap)
        result["capped"] = at is not None and at >= o.cap   # the generator topped out before the contestant did: score is "at least"
        result.update(score=score, knee=at, status="scored", history=hist)
        save()
        print("SCORE", o.name, o.tier, score, flush=True)
    except Abort as e:
        result["status"] = f"aborted: {e}"
        save()
        print("ABORT", e, flush=True)
        sys.exit(3)
    finally:
        for h in {o.target, *o.gen}:
            close_master(h)


if __name__ == "__main__":
    main()
