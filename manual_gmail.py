#!/usr/bin/env python3
"""Harvest akun xAI pakai email operator (human-in-loop OTP).

Loop: sniff jendela signup -> kalau terbuka, kirim kode ke email operator lalu
TUNGGU kode ditulis di data/user_code.txt oleh agent (dari chat) -> isi kode
-> form akhir -> turnstile -> submit -> simpan SSO.

Pakai: xvfb-run -a .venv/bin/python manual_gmail.py [email] [max_try]
"""
import asyncio
import os
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import grok

EMAIL = sys.argv[1] if len(sys.argv) > 1 else "arinata308@gmail.com"
MAX = int(sys.argv[2]) if len(sys.argv) > 2 else 40
CODE = str(Path(__file__).resolve().parent / "data" / "user_code.txt")
STATE = str(Path(__file__).resolve().parent / "data" / "manual_state.json")


def state(**kw):
    kw["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(STATE).write_text(json.dumps(kw))


for i in range(1, MAX + 1):
    p = Path(CODE)
    if p.exists():
        p.unlink()  # bersihkan kode basi
    state(attempt=i, phase="sniff", email=EMAIL)
    print(f"--- sniff {i}/{MAX} {time.strftime('%H:%M:%S', time.gmtime())}", flush=True)
    r = asyncio.run(grok.harvest_grok(headless=False, email=EMAIL,
                                      code_file=CODE, timeout_code=480))
    slim = {k: v for k, v in r.items() if k not in ("api_log", "console", "inputs", "buttons")}
    print(json.dumps(slim, default=str)[:1200], flush=True)
    if r.get("ok"):
        state(attempt=i, phase="ok", email=EMAIL, sso=(r.get("sso") or "")[:12])
        print("SUCCESS", r.get("email"), flush=True)
        break
    err = r.get("error") or ""
    if err == "account:email-signup-unavailable":
        state(attempt=i, phase="blocked", email=EMAIL)
        time.sleep(40)
        continue
    # no-code / yang lain: jangan habiskan percobaan
    state(attempt=i, phase="stop", email=EMAIL, error=err)
    print("STOP", err, flush=True)
    break
else:
    state(phase="exhausted", email=EMAIL)
    print("EXHAUSTED", flush=True)
