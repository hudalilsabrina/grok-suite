"""Helper bersama: password, nama, kode OTP, simpan inbox & akun.

Semua path relatif ke root suite -> jalan di Linux, macOS, dan Windows.
"""
import json
import os
import random
import re
import string
import time
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ACCOUNTS = ROOT / "accounts.txt"
INBOXES = DATA / "inboxes.json"

GIVEN = ["Mason", "Leo", "Ryan", "Kai", "Evan", "Nolan", "Owen", "Adam"]
FAMILY = ["Chen", "Lin", "Wang", "Yang", "Liu", "Zhao", "Wu", "Xu"]


def rand_password() -> str:
    return "Xq9#" + "".join(random.choices(string.ascii_letters + string.digits, k=12)) + "aZ"


def rand_name():
    return random.choice(GIVEN), random.choice(FAMILY)


def extract_code(text: str) -> Optional[str]:
    """Ambil kode OTP: format xAI "NNN-NNN" atau 6 digit polos."""
    m = re.search(r"\b(\d{3})-(\d{3})\b", text) or re.search(r"\b(\d{6})\b", text)
    if not m:
        return None
    return "".join(m.groups()) if m.lastindex == 2 else m.group(0)


def read_code(tc, email: str, timeout: int = 300, poll: int = 5) -> Optional[str]:
    """Poll inbox sampai kode OTP muncul."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            for m in tc.get_messages(email):
                body = re.sub(r"<[^>]+>", " ", (m.get("body") or "") + " " + (m.get("subject") or ""))
                code = extract_code(body)
                if code:
                    return code
        except Exception:
            pass
        time.sleep(poll)
    return None


def read_code_file(path: str, timeout: int = 900, poll: int = 2) -> Optional[str]:
    """Human-in-loop: baca kode yang ditulis operator ke file."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if os.path.exists(path):
                code = extract_code(open(path, encoding="utf-8", errors="ignore").read())
                if code:
                    return code
        except Exception:
            pass
        time.sleep(poll)
    return None


def save_inbox(email: str, session_id: str = "", site: str = "grok"):
    """Simpan inbox + riwayat (maks 500) supaya tidak tertimpa."""
    DATA.mkdir(parents=True, exist_ok=True)
    d: Dict = {}
    if INBOXES.exists():
        try:
            d = json.loads(INBOXES.read_text())
        except Exception:
            d = {}
    d[site] = {"email": email, "session_id": session_id}
    hist = d.setdefault("_history", [])
    hist.append({"site": site, "email": email, "session_id": session_id})
    d["_history"] = hist[-500:]
    INBOXES.write_text(json.dumps(d, indent=2), encoding="utf-8")


def append_account(email: str, password: str, sso: str) -> bool:
    """Tulis email:password:sso, dedup per email. Return True kalau baru."""
    ROOT.mkdir(parents=True, exist_ok=True)
    existing = set()
    if ACCOUNTS.exists():
        for ln in ACCOUNTS.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                existing.add(ln.split(":", 1)[0].strip())
    if email in existing:
        return False
    with ACCOUNTS.open("a", encoding="utf-8") as f:
        f.write(f"{email}:{password}:{sso}\n")
    return True


def parse_accounts(path: Path = None) -> List[Dict[str, str]]:
    """Parse accounts.txt -> [{email, password, sso}]. split(':', 2) aman
    karena password bisa mengandung ':'. Format lama (email:password) tetap dibaca."""
    path = path or ACCOUNTS
    out = []
    if not path.exists():
        return out
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split(":")
        if len(parts) < 2:
            continue
        email = parts[0]
        if len(parts) == 2:
            out.append({"email": email, "password": parts[1], "sso": ""})
        else:
            out.append({"email": email, "password": parts[1], "sso": ":".join(parts[2:])})
    return out
