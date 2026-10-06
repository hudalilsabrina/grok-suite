"""Inbox store: simpan inbox per-situs supaya tidak tertimpa.

Menyimpan juga riwayat inbox (list) agar bisa dicek telak-belakangan
(email xAI kadang telat masuk / perlu cek ulang).
"""
import json
import os
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent / "data" / "inboxes.json"


def _load() -> dict:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text())
        except Exception:
            return {}
    return {}


def save(site: str, email: str, session_id: str, password: str = ""):
    d = _load()
    d[site] = {"email": email, "session_id": session_id, "password": password}
    # riwayat (maks 500 terakhir)
    hist = d.setdefault("_history", [])
    hist.append({"site": site, "email": email, "session_id": session_id})
    d["_history"] = hist[-500:]
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=2))
    return d[site]


def get(site: str):
    return _load().get(site)


def history(site: str = None) -> list:
    h = _load().get("_history", [])
    return [x for x in h if site is None or x.get("site") == site]

