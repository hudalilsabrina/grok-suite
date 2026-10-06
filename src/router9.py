"""Integrasi 9router: daftarkan gateway Gonka sebagai provider OpenAI-compatible.

Alur (dari src/app/api/provider-nodes/route.js + providers/route.js):
  1. POST /api/provider-nodes  {name, prefix, apiType:'chat', baseUrl, type:'openai-compatible'}
     -> node.id (mis. "openai-compatible-chat-xxxx")
  2. POST /api/providers       {provider:<node.id>, apiKey:<gonka key>, name:<email>}
     -> connection.id
  3. POST /api/providers/{id}/test  -> {valid:true}

Provider id node yang dibuat bersifat persisten; kalau node dengan prefix sama
sudah ada, dipakai ulang (409 = sudah ada).
"""
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List

from .config import NINE_ROUTER_URL, NINE_ROUTER_PASS

# base router loopback (hindari reverse proxy utk operasi lokal)
DEFAULT_BASE = "http://127.0.0.1:20127"


def _base() -> str:
    b = NINE_ROUTER_URL or DEFAULT_BASE
    # NINE_ROUTER_URL mungkin berisi /dashboard/... -> ambil origin saja
    m = re.match(r"(https?://[^/]+)", b)
    return m.group(1) if m else DEFAULT_BASE


def login(base: str = None) -> Optional[str]:
    """Login 9router, return cookie 'auth_token=...' atau None."""
    base = base or _base()
    try:
        req = urllib.request.Request(
            f"{base}/api/auth/login",
            data=json.dumps({"password": NINE_ROUTER_PASS}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            sc = resp.headers.get("Set-Cookie") or ""
        for part in sc.split(";"):
            if "auth_token=" in part:
                return part.strip()
    except Exception:
        return None
    return None


def _req(method: str, url: str, cookie: str, payload=None, timeout=20):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}


def ensure_node(cookie: str, name: str, prefix: str, base_url: str,
                base: str = None) -> Optional[str]:
    """Buat/pakai-ulang provider node openai-compatible. Return node id."""
    base = base or _base()
    # cek existing
    st, d = _req("GET", f"{base}/api/provider-nodes", cookie)
    if st == 200:
        for n in d.get("nodes", []):
            if (n.get("prefix", "").lower() == prefix.lower()
                    or n.get("name", "").lower() == name.lower()):
                return n.get("id")
    st, d = _req("POST", f"{base}/api/provider-nodes", cookie, {
        "name": name, "prefix": prefix, "apiType": "chat",
        "baseUrl": base_url, "type": "openai-compatible",
    })
    if st in (200, 201):
        return (d.get("node") or {}).get("id")
    return None


def add_connection(cookie: str, node_id: str, api_key: str, name: str,
                   base: str = None) -> Optional[str]:
    """Tambah koneksi API-key ke node. Return connection id."""
    base = base or _base()
    st, d = _req("POST", f"{base}/api/providers", cookie, {
        "provider": node_id, "apiKey": api_key, "name": name, "priority": 1,
    })
    if st in (200, 201):
        return (d.get("connection") or {}).get("id")
    return None


def test_connection(cookie: str, conn_id: str, base: str = None) -> Optional[bool]:
    base = base or _base()
    st, d = _req("POST", f"{base}/api/providers/{conn_id}/test", cookie, {})
    if st == 200:
        return d.get("valid")
    return None


def ingest_gateway(name: str, prefix: str, base_url: str,
                   accounts: List[Dict[str, str]], base: str = None) -> Dict[str, Any]:
    """Daftarkan gateway + semua akunnya ke 9router. Return ringkasan."""
    cookie = login(base)
    if not cookie:
        return {"ok": False, "error": "login 9router gagal"}
    node = ensure_node(cookie, name, prefix, base_url, base)
    if not node:
        return {"ok": False, "error": "gagal buat provider node"}
    added, tested = [], []
    for a in accounts:
        cid = add_connection(cookie, node, a["key"], a["email"], base)
        if cid:
            added.append(cid)
            v = test_connection(cookie, cid, base)
            tested.append(v)
    return {"ok": True, "node": node, "added": len(added),
            "valid": sum(1 for v in tested if v), "total": len(tested)}
