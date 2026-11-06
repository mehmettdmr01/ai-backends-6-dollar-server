#!/usr/bin/env python3
"""A canary user on the generator: five requests a second on a fixed schedule, each on a NEW connection, as a user
arriving after a pause would. A server that has stopped accepting connections shows up here as slow or failed
(status 0), not only one that answers slowly. One flushed CSV line per request: start time, ms, status.
It finds where a rising load starts to hurt, and it draws the latency curve for the video. It does not produce a score.
  prob.py http://10.0.0.2/notes out.csv"""
import http.client, sys, threading, time
from urllib.parse import urlparse
u = urlparse(sys.argv[1])
out = open(sys.argv[2], "w", buffering=1)
lock = threading.Lock()

def one(t):
    status = 0
    c = None
    try:
        c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=5)
        c.request("GET", u.path)
        r = c.getresponse(); r.read(); status = r.status
    except Exception:
        pass
    finally:
        try:
            c and c.close()
        except Exception:
            pass
    ms = (time.time() - t) * 1000
    with lock:
        out.write(f"{t:.3f},{ms:.1f},{status}\n")

next_t = time.time()
while True:
    threading.Thread(target=one, args=(time.time(),), daemon=True).start()
    next_t += 0.2
    time.sleep(max(0, next_t - time.time()))
