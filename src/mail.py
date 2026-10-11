"""Klien temp-mail. Dua backend:

  - TempikClient  : API tempik (self-hosted, default). Terbukti tidak diblokir xAI.
  - MailTmClient  : mail.tm (alternatif). PERHATIAN: xAI memblokir domain mail.tm
                    dengan `form-invalid:disposable-email`.

Base URL dibaca dari config.toml [api] tempmail_base atau env TEMPIK_BASE.
"""
import json
import os
import random
import string
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36")


def _cfg(section: str, key: str, default: str = "") -> str:
    """Baca config.toml kalau ada (tanpa dependensi eksternal)."""
    f = ROOT / "config.toml"
    if not f.exists():
        return default
    try:
        try:
            import tomllib as toml
            data = toml.loads(f.read_text(encoding="utf-8"))
        except ImportError:
            import tomli as toml
            data = toml.loads(f.read_text(encoding="utf-8"))
        return str(data.get(section, {}).get(key, default))
    except Exception:
        return default


def tempmail_base() -> str:
    return (os.environ.get("TEMPIK_BASE")
            or _cfg("api", "tempmail_base", "http://localhost:8080/api")).rstrip("/")


class TempikClient:
    """Klien API tempik: session -> inbox -> messages."""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or tempmail_base()).rstrip("/")
        self.session_id: Optional[str] = None
        self._email: Optional[str] = None
        self._domains: List[str] = []

    # ---- HTTP ----
    def _req(self, path: str, method: str = "GET", body: dict = None,
             session: bool = True, timeout: int = 15):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", _UA)
        req.add_header("Accept-Language", "en-US,en;q=0.9")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if session and self.session_id:
            req.add_header("x-session-id", self.session_id)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode()
        return json.loads(txt) if txt.strip() else {}

    # ---- domain ----
    def domains(self) -> List[str]:
        if self._domains:
            return self._domains
        try:
            d = self._req("/config")
            self._domains = d.get("mailDomains") or [d.get("mailDomain", "")]
            self._domains = [x for x in self._domains if x]
        except Exception:
            self._domains = []
        return self._domains

    # ---- session / inbox ----
    def init_session(self) -> str:
        if self.session_id:
            return self.session_id
        d = self._req("/session")
        self.session_id = d.get("sessionId") or d.get("id") or d.get("session_id")
        return self.session_id

    def create_inbox(self, local_part: str = None, domain: str = None) -> str:
        self.init_session()
        if not domain:
            doms = self.domains()
            domain = os.environ.get("GROK_DOMAIN") or (random.choice(doms) if doms else None)
        body: Dict[str, Any] = {}
        if domain:
            body["domain"] = domain
        if local_part:
            body["localPart"] = local_part
        d = self._req("/inboxes", method="POST", body=body)
        self._email = d.get("address") or d.get("email")
        return self._email

    def get_messages(self, address: str = None) -> List[Dict[str, Any]]:
        addr = address or self._email
        if not addr:
            raise ValueError("alamat inbox kosong")
        d = self._req(f"/inboxes/{addr}/messages")
        return d if isinstance(d, list) else []

    @property
    def email(self):
        return self._email


class MailTmClient:
    """Klien mail.tm (alternatif). Sering ditolak xAI — pakai hanya kalau perlu."""

    BASE = "https://api.mail.tm"

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or self.BASE).rstrip("/")
        self.address: Optional[str] = None
        self.password: Optional[str] = None
        self.token: Optional[str] = None
        self.domain: Optional[str] = None

    def _req(self, path: str, method: str = "GET", body: dict = None, auth: bool = True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("User-Agent", _UA)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if auth and self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                txt = r.read().decode()
            return json.loads(txt) if txt.strip() else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} {path}: {e.read().decode(errors='ignore')[:200]}")

    def domains(self) -> List[str]:
        d = self._req("/domains", auth=False)
        items = d if isinstance(d, list) else d.get("hydra:member", [])
        return [x["domain"] for x in items if x.get("isActive", True)]

    def create_inbox(self, local_part: str = None, domain: str = None) -> str:
        doms = self.domains()
        com = [x for x in doms if x.endswith(".com")]
        self.domain = domain or (com[0] if com else (doms[0] if doms else None))
        if not self.domain:
            raise RuntimeError("mail.tm tidak punya domain aktif")
        user = local_part or ("grok" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8)))
        self.address = f"{user}@{self.domain}".lower()
        self.password = "Mtm!" + "".join(random.choices(string.ascii_letters + string.digits, k=10)) + "#"
        self._req("/accounts", method="POST", body={"address": self.address, "password": self.password}, auth=False)
        tok = self._req("/token", method="POST", body={"address": self.address, "password": self.password}, auth=False)
        self.token = tok.get("token")
        return self.address

    def get_messages(self, address: str = None) -> List[Dict[str, Any]]:
        d = self._req("/messages")
        items = d if isinstance(d, list) else d.get("hydra:member", [])
        out = []
        for m in items:
            try:
                det = self._req(f"/messages/{m['id']}")
            except Exception:
                det = m
            html = det.get("html") or []
            out.append({
                "subject": det.get("subject", "") or "",
                "body": (det.get("text", "") or "") + " " + " ".join(html if isinstance(html, list) else [html]),
            })
        return out


def make_client(provider: str = None):
    """provider: 'tempik' (default) | 'mailtm'."""
    p = (provider or os.environ.get("GROK_MAIL") or "tempik").strip().lower()
    return MailTmClient() if p == "mailtm" else TempikClient()
