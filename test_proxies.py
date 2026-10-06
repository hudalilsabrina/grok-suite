"""Tes proxy: hanya yang portnya terjangkau sandbox (80/443/8080).
Cek: apakah proxy hidup + egress IP + latensi.
"""
import json, socket, time, urllib.request, concurrent.futures as cf

PKG = "/root/.hermes/cache/documents/doc_3705f99552a2_shared_2000_proxies_package.json"
d = json.load(open(PKG))
allp = d["datacenter_proxies"] + d["residential_proxies"]
REACHABLE = {80, 443, 8080}

cands = []
for p in allp:
    port = int(p["proxy"].split(":")[1])
    if port in REACHABLE:
        cands.append(p)
print(f"proxy di port terjangkau (80/443/8080): {len(cands)}")

def test(p):
    host, port = p["proxy"].split(":")
    port = int(port)
    proto = p.get("proto", "http")
    # 1. cek TCP connect
    t0 = time.time()
    try:
        s = socket.create_connection((host, port), timeout=8)
        s.close()
        tcp_ms = round((time.time() - t0) * 1000)
    except Exception as e:
        return {**p, "tcp": False, "err": type(e).__name__}
    # 2. cek bisa dipakai (proxy GET ip)
    try:
        if proto == "http":
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": f"http://{host}:{port}", "https": f"http://{host}:{port}"}))
        else:
            return {**p, "tcp": True, "tcp_ms": tcp_ms, "http": None, "note": "socks-skip"}
        r = opener.open("https://api.ipify.org", timeout=12)
        ip = r.read().decode().strip()
        return {**p, "tcp": True, "tcp_ms": tcp_ms, "http": True, "egress": ip}
    except Exception as e:
        return {**p, "tcp": True, "tcp_ms": tcp_ms, "http": False, "err": str(e)[:50]}

alive = []
with cf.ThreadPoolExecutor(max_workers=30) as ex:
    for r in ex.map(test, cands):
        if r.get("http"):
            alive.append(r)
            print(f"  OK {r['proxy']:<22} {r.get('country','?'):<14} egress={r.get('egress')}")
print(f"\nproxy HIDUP & bisa HTTP: {len(alive)}/{len(cands)}")
json.dump(alive, open("/root/grok-suite/data/_alive_proxies.json", "w"), indent=1)
