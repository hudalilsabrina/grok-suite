#!/usr/bin/env python3
"""grok-suite CLI — harvest akun xAI, sinkron ke gateway, cek status.

Jalan di Linux / macOS / Windows:

    python grok.py harvest                 # 1 akun
    python grok.py harvest -n 3            # 3 akun (jeda)
    python grok.py harvest -n 3 --delay 300 --stop-on-gate
    python grok.py list                    # daftar akun tersimpan
    python grok.py probe                   # cek apakah email-signup xAI terbuka
    python grok.py sync                    # import ke grok2api
    python grok.py test                    # uji SSO ke grok2api (chat)

Di Linux headless tambahkan `xvfb-run -a` di depan (browser butuh display).
Di Windows tidak perlu apa-apa — Camoufox jalan headed.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import common
from src.mail import make_client


# ---------------- harvest ----------------

def cmd_harvest(a):
    from harvest_camoufox import harvest_one
    done, fail = 0, 0
    i = 0
    while True:
        i += 1
        print(f"\n=== akun {i} (sukses {done}, gagal {fail}) ===", flush=True)
        r = harvest_one(headless=a.headless, timeout_code=a.timeout_code)
        if r.get("ok"):
            done += 1
            print(f"  OK {r['email']}  sso {r['sso'][:24]}...")
        else:
            fail += 1
            err = r.get("error") or "?"
            print(f"  gagal: {err}")
            if a.stop_on_gate and err in ("account:email-signup-unavailable",
                                          "rate:too-many-code-requests"):
                print("  -> gate/rate-limit, berhenti (coba lagi nanti).")
                break
        if a.count and done >= a.count:
            break
        if a.count and done + fail >= a.count * a.max_attempts:
            break
        if i > 1 or a.count > 1:
            print(f"  jeda {a.delay}s...")
            time.sleep(a.delay)
        if a.count == 1:
            break
    print(f"\nSelesai: {done} akun dibuat, {fail} gagal. File: {common.ACCOUNTS}")


# ---------------- list ----------------

def cmd_list(a):
    accs = common.parse_accounts()
    if not accs:
        print(f"Belum ada akun ({common.ACCOUNTS}).")
        return
    print(f"{len(accs)} akun di {common.ACCOUNTS}:")
    for x in accs:
        sso = x["sso"]
        print(f"  {x['email']:<40} sso {sso[:20]}... ({len(sso)} char)")


# ---------------- probe ----------------

def cmd_probe(a):
    """Cek apakah endpoint email-signup xAI sedang menerima (tanpa browser)."""
    import urllib.request
    import urllib.error
    tc = make_client()
    email = tc.create_inbox()
    body = json.dumps({"email": email}).encode()
    req = urllib.request.Request(
        "https://accounts.x.ai/api/auth/send-verification-code", data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            "Origin": "https://accounts.x.ai",
            "Referer": "https://accounts.x.ai/sign-up?redirect=grok-com",
        }, method="POST")
    print(f"probe email: {email}")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            print(f"status {r.status}: {r.read().decode()[:150]}")
            print("=> endpoint merespons (kirim sungguhan tetap perlu browser: castle token).")
    except urllib.error.HTTPError as e:
        b = e.read().decode()[:250]
        print(f"status {e.code}: {b}")
        if "email-signup-unavailable" in b:
            print("=> GATE TERTUTUP: xAI mematikan pendaftaran email sementara.")
        else:
            print("=> endpoint aktif (kode error = validasi, bukan blokir).")


# ---------------- sync ----------------

def _g2a():
    import os
    return (os.environ.get("G2A") or "http://127.0.0.1:8000").rstrip("/")


def cmd_sync(a):
    """Import accounts.txt (SSO) ke pool Grok Web grok2api."""
    import http.cookiejar
    import os
    import urllib.request
    import urllib.error

    accs = common.parse_accounts()
    if not accs:
        print("Tidak ada akun untuk disync.")
        return
    base = _g2a()
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    H = {"Content-Type": "application/json", "Origin": base, "Referer": base + "/"}

    user = a.admin_user or os.environ.get("G2A_ADMIN_USER", "admin")
    pw = a.admin_pass or os.environ.get("G2A_ADMIN_PASS")
    if not pw:
        f = Path(os.environ.get("G2A_ADMIN_FILE", "~/.grok2api-admin.txt")).expanduser()
        if f.exists():
            for ln in f.read_text(encoding="utf-8").splitlines():
                if ln.lower().startswith("admin pass"):
                    pw = ln.split(":", 1)[-1].strip()
                elif ln.lower().startswith("admin user"):
                    user = ln.split(":", 1)[-1].strip()
    if not pw:
        print("Butuh password admin: set G2A_ADMIN_PASS atau --admin-pass, "
              "atau taruh file di ~/.grok2api-admin.txt")
        return

    def req(path, obj=None, method=None, timeout=120):
        data = json.dumps(obj).encode() if obj is not None else None
        r = urllib.request.Request(base + path, data=data, headers=H,
                                   method=method or ("POST" if obj is not None else "GET"))
        try:
            with op.open(r, timeout=timeout) as x:
                return x.status, x.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    s, b = req("/api/admin/v1/auth/login", {"username": user, "password": pw})
    if s != 200:
        print(f"login gagal ({s}): {b[:200]}")
        return
    print("login OK")

    doc = {"provider": "grok_web",
           "accounts": [{"name": f"Grok {x['email'].split('@')[0][:14]}",
                         "email": x["email"], "sso_token": x["sso"], "tier": "auto"}
                        for x in accs if x["sso"]]}
    boundary = "----groksync7f3a"
    payload = (f"--{boundary}\r\n"
               'Content-Disposition: form-data; name="files"; filename="accounts.json"\r\n'
               "Content-Type: application/json\r\n\r\n"
               + json.dumps(doc, indent=2) + f"\r\n--{boundary}--\r\n").encode()
    r = urllib.request.Request(base + "/api/admin/v1/accounts/web/import", data=payload,
                               headers={**H,
                                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                                        "Accept": "text/event-stream"}, method="POST")
    try:
        with op.open(r, timeout=300) as x:
            stream = x.read().decode(errors="replace")
        last = None
        for line in stream.splitlines():
            if line.startswith("data:"):
                try:
                    last = json.loads(line[5:].strip())
                except Exception:
                    pass
        print("import:", json.dumps(last) if last else stream[-200:])
    except Exception as e:
        print("import gagal:", str(e)[:200])
        return

    s, b = req("/api/admin/v1/accounts")
    try:
        d = json.loads(b).get("data", {})
        print(f"pool grok2api: {d.get('total', len(d.get('items', [])))} akun")
    except Exception:
        print("pool:", b[:200])


# ---------------- test ----------------

def cmd_test(a):
    """Uji akun: panggil chat lewat grok2api (butuh egress residensial untuk grok.com)."""
    import os
    import urllib.request
    import urllib.error
    base = _g2a()
    key = a.key or os.environ.get("G2A_CLIENT_KEY")
    if not key:
        f = Path(os.environ.get("G2A_CLIENTKEY_FILE", "~/.grok2api-clientkey.txt")).expanduser()
        if f.exists():
            key = f.read_text(encoding="utf-8").strip()
    if not key:
        print("Butuh client key: --key / G2A_CLIENT_KEY / ~/.grok2api-clientkey.txt")
        return
    body = json.dumps({"model": a.model,
                       "messages": [{"role": "user", "content": a.prompt}],
                       "max_tokens": 32}).encode()
    r = urllib.request.Request(base + "/v1/chat/completions", data=body,
                               headers={"Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            d = json.loads(x.read().decode())
        print("balasan:", d["choices"][0]["message"]["content"])
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:300]}")
        print("catatan: grok.com menolak IP datacenter (403). Pasang egress residensial "
              "di grok2api lalu assign akun ke node itu.")
    except Exception as e:
        print("gagal:", str(e)[:200])


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser(prog="grok", description="grok-suite — harvest akun xAI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("harvest", help="buat akun xAI")
    h.add_argument("-n", "--count", type=int, default=1, help="jumlah akun (default 1)")
    h.add_argument("--delay", type=int, default=120, help="jeda antar akun (detik)")
    h.add_argument("--timeout", dest="timeout_code", type=int, default=180,
                   help="timeout tunggu kode OTP (detik)")
    h.add_argument("--headless", action="store_true", help="headless (Linux: pakai xvfb-run)")
    h.add_argument("--stop-on-gate", action="store_true",
                   help="berhenti kalau gate email-signup tertutup")
    h.add_argument("--max-attempts", type=int, default=3, help="maks percobaan per akun")
    h.set_defaults(func=cmd_harvest)

    sub.add_parser("list", help="daftar akun tersimpan").set_defaults(func=cmd_list)
    sub.add_parser("probe", help="cek apakah email-signup xAI terbuka").set_defaults(func=cmd_probe)

    s = sub.add_parser("sync", help="import SSO ke grok2api")
    s.add_argument("--admin-user", default=None)
    s.add_argument("--admin-pass", default=None)
    s.set_defaults(func=cmd_sync)

    t = sub.add_parser("test", help="uji chat lewat grok2api")
    t.add_argument("--key", default=None, help="client key grok2api")
    t.add_argument("--model", default="grok-chat-fast")
    t.add_argument("--prompt", default="Reply with exactly: OK")
    t.set_defaults(func=cmd_test)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
