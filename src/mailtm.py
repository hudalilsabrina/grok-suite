"""Mail.tm / Mail.gw Client - Disposable Temp-Mail dengan domain .com (e.g. @maxxspace.com).

Mendukung mode Synchronous & Asynchronous:
- Auto domain discovery (mengambil domain aktif .com dari api.mail.tm)
- Pembuatan akun otomatis (random/custom username + auto token)
- Polling pesan real-time (lengkap dengan body text & HTML)
- Ekstraksi kode OTP & link verifikasi otomatis via regex
"""

import asyncio
import json
import random
import re
import string
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List, Tuple

BASE_URL = "https://api.mail.tm"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"


class MailTmClient:
    """Client Synchronous untuk Mail.tm."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.address: Optional[str] = None
        self.password: Optional[str] = None
        self.token: Optional[str] = None
        self.account_id: Optional[str] = None
        self.domain: Optional[str] = None

    def _req(self, endpoint: str, method: str = "GET", data: dict = None, auth: bool = True) -> Any:
        url = f"{self.base_url}{endpoint}"
        payload = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("User-Agent", UA)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if auth and self.token:
            req.add_header("Authorization", f"Bearer {self.token}")

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                res_body = resp.read().decode("utf-8")
                return json.loads(res_body) if res_body.strip() else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {e.code} on {endpoint}: {err_body}")

    def get_domains(self) -> List[str]:
        """Ambil semua domain aktif yang tersedia."""
        res = self._req("/domains", auth=False)
        members = res if isinstance(res, list) else res.get("hydra:member", [])
        return [m["domain"] for m in members if m.get("isActive", True)]

    def create_inbox(self, username: str = None, domain: str = None) -> str:
        """Buat inbox baru dengan domain .com (default: @maxxspace.com)."""
        domains = self.get_domains()
        if not domains:
            raise RuntimeError("Tidak ada domain yang tersedia di Mail.tm saat ini.")

        # Prioritaskan domain .com bila ada
        com_domains = [d for d in domains if d.endswith(".com")]
        self.domain = domain or (com_domains[0] if com_domains else domains[0])

        if not username:
            prefix = "".join(random.choices(string.ascii_lowercase, k=7))
            suffix = str(random.randint(100, 999))
            username = f"{prefix}{suffix}"

        self.address = f"{username}@{self.domain}".lower()
        self.password = "Mtm!" + "".join(random.choices(string.ascii_letters + string.digits, k=10)) + "#"

        # 1. Register account
        acc = self._req("/accounts", method="POST", data={
            "address": self.address,
            "password": self.password
        }, auth=False)
        self.account_id = acc.get("id")

        # 2. Obtain JWT token
        tok_res = self._req("/token", method="POST", data={
            "address": self.address,
            "password": self.password
        }, auth=False)
        self.token = tok_res.get("token")

        return self.address

    def get_messages(self) -> List[Dict[str, Any]]:
        """Ambil ringkasan daftar email di inbox."""
        if not self.token:
            raise RuntimeError("Inbox belum diinisialisasi.")
        res = self._req("/messages", auth=True)
        return res if isinstance(res, list) else res.get("hydra:member", [])

    def get_message_detail(self, message_id: str) -> Dict[str, Any]:
        """Ambil konten lengkap email (HTML & Text)."""
        return self._req(f"/messages/{message_id}", auth=True)

    def wait_for_message(self, timeout: int = 60, interval: int = 3) -> Optional[Dict[str, Any]]:
        """Polling sampai ada email masuk."""
        start = time.time()
        while time.time() - start < timeout:
            msgs = self.get_messages()
            if msgs:
                # Ambil pesan terbaru
                latest_id = msgs[0]["id"]
                return self.get_message_detail(latest_id)
            time.sleep(interval)
        return None

    def wait_for_code(self, pattern: str = r"\b([0-9]{6}|[a-zA-Z0-9]{10})\b", timeout: int = 60) -> Optional[str]:
        """Tunggu email masuk dan ekstrak kode OTP."""
        msg = self.wait_for_message(timeout=timeout)
        if not msg:
            return None

        # Gabungkan teks & HTML
        content = " ".join([
            msg.get("subject", ""),
            msg.get("text", "") or "",
            " ".join(msg.get("html", []) or [])
        ])
        # Bersihkan tag HTML
        clean_text = re.sub(r"<[^>]+>", " ", content)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        match = re.search(pattern, clean_text)
        return match.group(1) if match else None

    def wait_for_link(self, pattern: str = r"https?://[^\s\"'<>]+", timeout: int = 60) -> Optional[str]:
        """Tunggu email masuk dan ekstrak link verifikasi."""
        msg = self.wait_for_message(timeout=timeout)
        if not msg:
            return None

        content = " ".join([
            msg.get("text", "") or "",
            " ".join(msg.get("html", []) or [])
        ])
        match = re.search(pattern, content)
        return match.group(0) if match else None


class AsyncMailTmClient:
    """Client Asynchronous (untuk pipeline Patchright/Playwright)."""

    def __init__(self, base_url: str = BASE_URL):
        self._sync = MailTmClient(base_url)

    async def create_inbox(self, username: str = None, domain: str = None) -> str:
        return await asyncio.to_thread(self._sync.create_inbox, username, domain)

    @property
    def address(self) -> Optional[str]:
        return self._sync.address

    @property
    def password(self) -> Optional[str]:
        return self._sync.password

    async def get_messages(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync.get_messages)

    async def get_message_detail(self, message_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync.get_message_detail, message_id)

    async def wait_for_message(self, timeout: int = 60, interval: int = 3) -> Optional[Dict[str, Any]]:
        start = time.time()
        while time.time() - start < timeout:
            msgs = await self.get_messages()
            if msgs:
                latest_id = msgs[0]["id"]
                return await self.get_message_detail(latest_id)
            await asyncio.sleep(interval)
        return None

    async def wait_for_code(self, pattern: str = r"\b([0-9]{6}|[a-zA-Z0-9]{10})\b", timeout: int = 60) -> Optional[str]:
        msg = await self.wait_for_message(timeout=timeout)
        if not msg:
            return None

        content = " ".join([
            msg.get("subject", ""),
            msg.get("text", "") or "",
            " ".join(msg.get("html", []) or [])
        ])
        clean_text = re.sub(r"<[^>]+>", " ", content)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        match = re.search(pattern, clean_text)
        return match.group(1) if match else None

    async def wait_for_link(self, pattern: str = r"https?://[^\s\"'<>]+", timeout: int = 60) -> Optional[str]:
        msg = await self.wait_for_message(timeout=timeout)
        if not msg:
            return None

        content = " ".join([
            msg.get("text", "") or "",
            " ".join(msg.get("html", []) or [])
        ])
        match = re.search(pattern, content)
        return match.group(0) if match else None
