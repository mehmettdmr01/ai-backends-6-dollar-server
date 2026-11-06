"""arama.py's decisions, no network and no k6."""
import sys; sys.path.insert(0, __file__.rsplit("/", 2)[0])
from arama import search, knee, parse_probe, parse_summary, merge, verdict, generator_load, csv_summary, expected_requests

def box(limit, hold_margin=1.0):
    r = lambda target: int(limit) if target >= limit else None
    h = lambda u: u <= limit * hold_margin
    return r, h
for limit in (900, 5000, 13700, 26000, 64000):
    s, k, h = search(*box(limit), first=20000, cap=120000)
    assert 0.80 * limit <= s <= limit, (limit, s, h)
    assert h[-1][0] == "hold" and h[-1][2], h
    assert len(h) <= 6, (limit, h)                 # each ramp 11 min, each hold 7 min
s, k, h = search(*box(30000, hold_margin=0.7), first=20000, cap=120000)     # the rise looks better than a hold: steps down
assert 0.55 * 30000 <= s <= 0.7 * 30000, (s, h)
s, k, h = search(lambda t: None, lambda u: True, first=20000, cap=120000)   # never breaks: reports the cap region and stops
assert k == 120000 and s == 108000 and [x[1] for x in h if x[0] == "ramp"] == [20000, 40000, 80000], (s, k, h)
s, k, h = search(lambda t: None, lambda u: True)   # the defaults: one 25,000-user ramp, then a hold at 22,500
assert k == 25000 and s == 22500 and [x[1] for x in h if x[0] == "ramp"] == [25000], (s, k, h)
s, k, h = search(lambda t: 5000, lambda u: False, first=20000)  # holds never pass: must end
assert s == 0 and sum(1 for x in h if x[0] == "hold") == 6, h
s, k, h = search(lambda t: 500 if t > 2000 else 480, lambda u: u <= 480, first=20000)   # very slow: looks closer once
assert [x[1] for x in h if x[0] == "ramp"] == [20000, 1500] and 0 < s <= 480, h
s, k, h = search(lambda t: 100, lambda u: False, first=20000)   # hopeless: ends without looping at the floor
assert s == 0 and h[-1][1] == 100, h

good = [(t / 5, 20.0, 200) for t in range(0, 3000)]                   # t0=0, 600 s of 20 ms answers
assert knee(good, 0, 600, 20000) is None
worse = [(t, 1500.0 if t >= 300 else 20.0, 200) for t, _, _ in good]  # slow from the middle
assert knee(worse, 0, 600, 20000) == 10000
down = [(t, 3.0 if t >= 150 else 20.0, 0 if t >= 150 else 200) for t, _, _ in good]    # connection refused
assert knee(down, 0, 600, 20000) == 5000
blip = [(t, 1500.0 if 100 <= t < 110 else 20.0, 200) for t, _, _ in good]              # one bad window is noise
assert knee(blip, 0, 600, 20000) is None
stall = [(t, 2700.0 if 230 <= t < 250 or t >= 530 else 20.0, 200) for t, _, _ in good] # Express: 20 s stall, then the real break
assert knee(stall, 0, 600, 20000) == 17666, knee(stall, 0, 600, 20000)
late = [(t, 2000.0 if t >= 570 else 20.0, 200) for t, _, _ in good]                   # breaks in the last 30 s
assert knee(late, 0, 600, 20000) == 19000, knee(late, 0, 600, 20000)
hung = [(t, 20.0, 200) for t, _, _ in good if t < 200] + [(200 + 5 * i, 5000.0, 0) for i in range(80)]    # hung server, few samples
assert knee(hung, 0, 600, 20000) in (6333, 6666, 6000), knee(hung, 0, 600, 20000)
assert parse_probe("1.5,20.0,200\n\n2.0,5000.0,0\n") == [(1.5, 20.0, 200), (2.0, 5000.0, 0)]

doc = {"metrics": {"http_req_duration": {"p(95)": 120.5, "p(99)": 300.0}, "http_req_failed": {"value": 0.002}, "http_reqs": {"rate": 950.0, "count": 171000}, "notes_created": {"count": 1700}}}
k = parse_summary(doc); assert k == {"p95": 120.5, "p99": 300.0, "err": 0.002, "rps": 950.0, "requests": 171000, "created": 1700}
k2 = parse_summary({"metrics": {**{a: b for a, b in doc["metrics"].items() if a != "notes_created"}, "http_req_failed": {"rate": 0.02}}}); assert k2["err"] == 0.02 and k2["created"] == 0
m = merge([k, k2]); assert m["err"] == 0.02 and m["rps"] == 1900.0 and m["created"] == 1700

assert verdict(k, True, []) is None and verdict(k, True, [], 1700) is None and verdict(k, True, [], 1705) is None
assert verdict(k, True, [], 1699) == "lost-writes"
assert verdict(k, True, ["Out of memory: Killed process 812 (node)"]) == "oom"
assert verdict(k, False, []) == "crash"
assert verdict(k, True, ["nf_conntrack: table full, dropping packet"]) is None
assert verdict({**k, "err": 0.05}, True, ["nf_conntrack: table full, dropping packet"]) == "conntrack"
assert verdict(None, True, []) == "no-result"
assert verdict({**k, "err": 0.01}, True, []) == "errors" and verdict({**k, "p95": 1000.0}, True, []) == "p95"
assert verdict({**k, "p99": 5000.0}, True, []) is None                # p99 is recorded, it does not decide
assert expected_requests(5000, 60, 300) == 165000

row = lambda t, free, idle, cache=2000000: f"{t} 1  0      0 {free} 100000 {cache}    0    0     0     0 100 200 30 10 {idle}  0  0  0\n"
g = generator_load(row(100, 8000000, 60) + row(104, 8000000, 55))
assert g == {"min_free_mb": 9765, "min_idle": 55, "busy_share": 0.0, "limited": False}, g
assert generator_load(row(100, 400000, 60, cache=100000))["limited"]
assert generator_load(row(100, 8000000, 10))["limited"]
spikes = "".join(row(100 + 4 * i, 8000000, 5 if i % 15 == 0 else 60) for i in range(150))     # k6 cleaning up once a minute
assert not generator_load(spikes)["limited"], generator_load(spikes)
busy = "".join(row(100 + 4 * i, 8000000, 5 if i % 3 == 0 else 60) for i in range(150))        # a third of the time: saturated
assert generator_load(busy)["limited"]
after = "".join(row(100 + 4 * i, 8000000, 60 if i < 100 else 3) for i in range(150))          # busy only after the break
assert not generator_load(after, until=100 + 4 * 100)["limited"] and generator_load(after)["limited"]
assert not generator_load(row(96, 8000000, 3) + row(100, 8000000, 70), since=99.5)["limited"]   # k6 preparing its users
assert generator_load(row(96, 8000000, 70), since=99.5)["limited"]                             # no row after the start
assert generator_load("")["limited"] and generator_load("procs ---\n r b swpd\n")["limited"]
c = "t,mem_avail_mb,app_total_mb,app_anon_mb,tcp_inuse,conntrack,cpu_idle,cpu_steal,cpu_iowait\n100,800,50,40,10,,90,0,0\n170,300,600,500,900,,10,5,1\n171,,,,,,,,\n"
b = csv_summary(c, 100); assert b["min_mem_avail_mb"] == 300 and b["peak_app_mb"] == 600 and b["peak_conntrack"] is None and b["mean_steal"] == 5, b
print("ok")
