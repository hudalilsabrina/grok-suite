"""Ekstrak proxy dari package JSON -> file proxies.txt (format http://host:port).
Hanya ambil yang portnya terjangkau sandbox (80/443/8080) & proto http.
"""
import os
from pathlib import Path
import json, sys

PKG = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PROXY_PACKAGE", "proxies_package.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent / "proxies.txt")
REACHABLE = {80, 443, 8080}

d = json.load(open(PKG))
allp = d["datacenter_proxies"] + d["residential_proxies"]
lines = []
for p in allp:
    port = int(p["proxy"].split(":")[1])
    if port in REACHABLE and p.get("proto") == "http":
        lines.append(f"http://{p['proxy']}")
open(OUT, "w").write("\n".join(lines) + "\n")
print(f"ditulis {len(lines)} proxy (port 80/443/8080, http) -> {OUT}")

# ringkas per negara
import collections
cc = collections.Counter(p.get("country") for p in allp if int(p["proxy"].split(":")[1]) in REACHABLE)
print("negara (terjangkau):", dict(cc.most_common(10)))
