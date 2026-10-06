"""Tes: apakah proxy bisa menjangkau accounts.x.ai? + cek residential."""
import json, urllib.request, concurrent.futures as cf, time

PKG = "/root/.hermes/cache/documents/doc_3705f99552a2_shared_2000_proxies_package.json"
d = json.load(open(PKG))

# 3 residential yang portnya terjangkau
res = [p for p in d["residential_proxies"] if int(p["proxy"].split(":")[1]) in (80, 443, 8080)]
print("residential terjangkau:", len(res))
for p in res:
    print("  ", p["proxy"], p.get("country"), p.get("isp","")[:30])

# alive datacenter dari tes sebelumnya
try:
    alive = json.load(open("/root/grok-suite/data/_alive_proxies.json"))
except Exception:
    alive = []
print(f"\ndatacenter alive: {len(alive)}")

def can_reach_xai(p):
    host, port = p["proxy"].split(":")
    if p.get("proto") != "http":
        return None
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler(
            {"http": f"http://{host}:{port}", "https": f"http://{host}:{port}"}))
        req = urllib.request.Request("https://accounts.x.ai/sign-up?redirect=grok-com",
                                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"})
        r = op.open(req, timeout=15)
        return {"proxy": p["proxy"], "country": p.get("country"), "status": r.status}
    except urllib.error.HTTPError as e:
        return {"proxy": p["proxy"], "country": p.get("country"), "status": e.code, "note": "http-err"}
    except Exception as e:
        return {"proxy": p["proxy"], "country": p.get("country"), "err": str(e)[:40]}

cands = [p for p in (res + alive) if p.get("proto") == "http"]
print(f"\n=== tes {len(cands)} proxy -> accounts.x.ai ===")
ok = []
with cf.ThreadPoolExecutor(max_workers=20) as ex:
    for r in ex.map(can_reach_xai, cands):
        if r and r.get("status") in (200, 403):  # 403 = CF tapi sampai
            ok.append(r)
            print(f"  {r['proxy']:<22} {str(r.get('country')):<16} status={r['status']}")
print(f"\nbisa capai accounts.x.ai: {len(ok)}")
json.dump(ok, open("/root/grok-suite/data/_proxies_xai.json", "w"), indent=1)
