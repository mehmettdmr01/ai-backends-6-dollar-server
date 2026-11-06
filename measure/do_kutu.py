#!/usr/bin/env python3
"""DigitalOcean boxes for V7, standard library only. Every box carries the tag v7-olcum, so 'sil' removes all of them
and nothing else. The token comes from the DO_TOKEN environment variable and is never written anywhere.
  do_kutu.py fiyat                    what the tiers cost right now, from the API
  do_kutu.py ac do-6 hedef6           create a box (do-4, do-6, do-12, gen) and print its addresses
  do_kutu.py liste                    every v7-olcum box, its CPU-independent details and what it has cost so far
  do_kutu.py sil --evet               destroy every v7-olcum box"""
import datetime, json, os, sys, time, urllib.request
from pathlib import Path
API, TAG, REGION, IMAGE = "https://api.digitalocean.com/v2", "v7-olcum", "ams3", "ubuntu-24-04-x64"
SIZES = {"do-4": "s-1vcpu-512mb-10gb", "do-6": "s-1vcpu-1gb", "do-12": "s-1vcpu-2gb", "gen": "s-4vcpu-8gb"}
MAX_BOXES = 3
PUB = Path(__file__).resolve().parent / ".anahtar/v7.pub"


def call(method, path, body=None):
    r = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                               headers={"Authorization": "Bearer " + os.environ["DO_TOKEN"], "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as f:
        raw = f.read()
    return json.loads(raw) if raw else {}


def boxes():
    return call("GET", f"/droplets?tag_name={TAG}&per_page=100")["droplets"]


def key_id():
    """The key list can come back empty for a key the account already has, so look it up by fingerprint."""
    import base64, hashlib, urllib.error
    pub = PUB.read_text().strip()
    fp = ":".join(f"{b:02x}" for b in hashlib.md5(base64.b64decode(pub.split()[1])).digest())
    try:
        return call("GET", f"/account/keys/{fp}")["ssh_key"]["id"]
    except urllib.error.HTTPError:
        return call("POST", "/account/keys", {"name": "v7-olcum", "public_key": pub})["ssh_key"]["id"]


def addr(d, kind):
    return next((n["ip_address"] for n in d["networks"]["v4"] if n["type"] == kind), None)


def main():
    cmd = sys.argv[1]
    if cmd == "fiyat":
        table = {s["slug"]: s for s in call("GET", "/sizes?per_page=200")["sizes"]}
        for name, slug in SIZES.items():
            s = table[slug]
            print(f"{name:6} {slug:22} {s['vcpus']} vCPU {s['memory']:>6} MB {s['disk']:>4} GB ${s['price_monthly']}/mo ${s['price_hourly']}/h")
    elif cmd == "ac":
        tier, name = sys.argv[2], sys.argv[3]
        if len(boxes()) >= MAX_BOXES:
            raise SystemExit(f"already {MAX_BOXES} boxes: delete some first")
        d = call("POST", "/droplets", {"name": name, "region": REGION, "size": SIZES[tier], "image": IMAGE, "ssh_keys": [key_id()], "tags": [TAG, tier]})["droplet"]
        for _ in range(60):
            time.sleep(5)
            d = call("GET", f"/droplets/{d['id']}")["droplet"]
            if d["status"] == "active" and addr(d, "public"):
                break
        print(json.dumps({"name": name, "tier": tier, "public": addr(d, "public"), "private": addr(d, "private"), "id": d["id"]}))
    elif cmd == "liste":
        now = datetime.datetime.now(datetime.timezone.utc)
        total = 0.0
        for d in boxes():
            hours = (now - datetime.datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))).total_seconds() / 3600
            cost = hours * d["size"]["price_hourly"]
            total += cost
            print(f"{d['name']:12} {d['size_slug']:22} {addr(d, 'public')} {addr(d, 'private')} {hours:6.1f} h ${cost:.2f}")
        print(f"total so far ${total:.2f}, {len(boxes())} boxes still billing")
    elif cmd == "sil":
        if "--evet" not in sys.argv:
            raise SystemExit("add --evet to destroy every v7-olcum box")
        call("DELETE", f"/droplets?tag_name={TAG}")
        time.sleep(5)
        print("left:", [d["name"] for d in boxes()])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
