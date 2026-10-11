#!/usr/bin/env python3
"""Sinkron accounts.txt grok-suite -> grok2api (pool Grok Web) + smoke test.

Pakai:
  python3 sync_grok2api.py            # import + verifikasi
  python3 sync_grok2api.py --key-only  # cuma ambil/buat client key

Format accounts.txt: email:password:sso  (SSO = cookie 'sso' hasil harvest)
"""
import json
import os
import http.cookiejar
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8000"
ADMIN = f"{BASE}/api/admin/v1"
ACCOUNTS = Path(os.environ.get("GROK_ACCOUNTS", str(Path(__file__).resolve().parent / "accounts.txt")))
SECRET = Path(os.environ.get("G2A_ADMIN_FILE", "~/.grok2api-admin.txt")).expanduser()

# grok2api mengirim token admin sebagai HttpOnly cookie (Path=/api/admin/v1);
# nilai accessToken di JSON sengaja dipotong ("eyJhbG...LB80"), jadi wajib cookie jar.
_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))


def _req(path, data=None, token=None, method=None, raw=False, headers=None):
    if path.startswith("http"):
        url = path
    elif path.startswith("/api"):
        url = BASE + path
    else:
        url = ADMIN + path
    body = None
    h = {"Accept": "application/json", "User-Agent": "grok2api-sync/1.0"}
    if data is not None and not raw:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = f"Bearer {token}"
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method=method or ("POST" if data is not None else "GET"))
    with _OPENER.open(req, timeout=300) as r:
        return r.status, r.read().decode(errors="replace")


def login():
    creds = dict(l.split(": ", 1) for l in SECRET.read_text().splitlines() if ": " in l)
    status, out = _req("/api/admin/v1/auth/login",
                       {"username": creds["admin user"], "password": creds["admin pass"]})
    tok = json.loads(out)["data"]["tokens"]["accessToken"]
    return tok, creds


def load_accounts():
    rows = []
    if not ACCOUNTS.exists():
        return rows
    for ln in ACCOUNTS.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.count(":") < 2:
            continue
        email, pwd, sso = ln.split(":", 2)
        rows.append((email, pwd, sso))
    return rows


def import_web(rows, tok):
    doc = {"provider": "grok_web",
           "accounts": [{"name": f"Grok {e.split('@')[0][:14]}", "email": e,
                         "sso_token": s, "tier": "auto"} for e, p, s in rows]}
    boundary = "----groksync7f3a"
    payload = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="accounts.json"\r\n'
        "Content-Type: application/json\r\n\r\n"
        + json.dumps(doc, indent=2) + "\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    h = {"Content-Type": f"multipart/form-data; boundary={boundary}",
         "Authorization": f"Bearer {tok}", "Accept": "text/event-stream"}
    req = urllib.request.Request(f"{ADMIN}/accounts/web/import", data=payload, headers=h, method="POST")
    with _OPENER.open(req, timeout=300) as r:
        stream = r.read().decode(errors="replace")
    # SSE: "event: complete\ndata: {...}\n\n"
    last = None
    for line in stream.splitlines():
        if line.startswith("data:"):
            try:
                last = json.loads(line[5:].strip())
            except Exception:
                pass
    return last, stream[-400:]


def main():
    tok, creds = login()
    rows = load_accounts()
    print(f"login OK | accounts.txt: {len(rows)} akun")

    if rows:
        result, tail = import_web(rows, tok)
        print("import:", json.dumps(result) if result else f"(stream tail: {tail[:200]})")

    status, out = _req("/accounts", token=tok)
    try:
        d = json.loads(out)
        data = d.get("data", d)
        items = data.get("items") or data.get("accounts") or []
        print(f"pool di grok2api: {len(items)} akun")
    except Exception:
        print("pool:", out[:200])

    # client key untuk /v1
    status, out = _req("/client-keys", token=tok)
    keys = json.loads(out).get("data", [])
    if isinstance(keys, dict):
        keys = keys.get("items", [])
    if keys:
        kid = keys[0].get("id")
        _, sec = _req(f"/client-keys/{kid}/secret", token=tok)
        secret = json.loads(sec).get("data", {})
        val = secret.get("key") or secret.get("secret") or ""
        if val:
            Path(os.environ.get("G2A_CLIENTKEY_FILE", "~/.grok2api-clientkey.txt")).expanduser().write_text(val + "\n")
        print("client key:", val[:16] + "..." if val else str(secret)[:80])
    else:
        _, created = _req("/client-keys", {"name": "grok-suite", "note": "auto"}, token=tok)
        cid = json.loads(created).get("data", {}).get("id")
        _, sec = _req(f"/client-keys/{cid}/secret", token=tok)
        secret = json.loads(sec).get("data", {})
        Path(os.environ.get("G2A_CLIENTKEY_FILE", "~/.grok2api-clientkey.txt")).expanduser().write_text(
            (secret.get("key") or secret.get("secret") or "") + "\n")
        print("client key dibuat ->", str(secret.get("key") or secret.get("secret"))[:12] + "...")


if __name__ == "__main__":
    sys.exit(main())
