#!/usr/bin/env python3
"""One-second sampler for the target box. Standard library only, one flushed CSV line per second, so the
last second before a crash is still on disk. Usage: izle.py out.csv"""
import csv, sys, time
SVC = "/sys/fs/cgroup/system.slice/yarisma.service"
NGX = "/sys/fs/cgroup/system.slice/nginx.service"
MB = 1024 * 1024

def read(p):
    try:
        with open(p) as f:
            return f.read()
    except OSError:
        return None

def cg(path):
    stat = {}
    for line in (read(path + "/memory.stat") or "").splitlines():
        k, v = line.split()
        stat[k] = int(v)
    cur = read(path + "/memory.current")
    return stat, int(cur) if cur else None

def cpu():
    a = (read("/proc/stat") or "").splitlines()[0].split()[1:9]
    return [int(x) for x in a]

def meminfo():
    m = {}
    for line in read("/proc/meminfo").splitlines():
        k, v = line.split(":")
        m[k] = int(v.split()[0]) // 1024
    return m

def tcp():
    for line in read("/proc/net/sockstat").splitlines():
        if line.startswith("TCP:"):
            f = line.split()
            return int(f[2]), int(f[10])  # inuse, mem pages
    return None, None

FIELDS = ["t", "mem_avail_mb", "mem_free_mb", "cached_mb", "cpu_user", "cpu_sys", "cpu_idle", "cpu_iowait", "cpu_steal",
          "app_anon_mb", "app_file_mb", "app_sock_mb", "app_total_mb", "nginx_total_mb", "tcp_inuse", "tcp_mem_pages", "conntrack", "load1"]
out = open(sys.argv[1], "w", newline="", buffering=1)
w = csv.writer(out, lineterminator="\n")
w.writerow(FIELDS)
prev = cpu()
while True:
    time.sleep(1)
    now = cpu()
    d = [b - a for a, b in zip(prev, now)]
    prev = now
    total = sum(d) or 1
    pct = lambda i: round(100 * d[i] / total, 1)  # user nice system idle iowait irq softirq steal
    m = meminfo()
    s, cur = cg(SVC)
    _, ngx = cg(NGX)
    inuse, pages = tcp()
    ct = read("/proc/sys/net/netfilter/nf_conntrack_count")
    w.writerow([round(time.time(), 1), m["MemAvailable"], m["MemFree"], m["Cached"],
                round(pct(0) + pct(1), 1), round(pct(2) + pct(5) + pct(6), 1), pct(3), pct(4), pct(7),
                round(s.get("anon", 0) / MB) if s else "", round(s.get("file", 0) / MB) if s else "", round(s.get("sock", 0) / MB) if s else "",
                round(cur / MB) if cur is not None else "", round(ngx / MB) if ngx is not None else "",
                inuse, pages, ct.strip() if ct else "", read("/proc/loadavg").split()[0]])
