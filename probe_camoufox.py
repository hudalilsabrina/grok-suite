#!/usr/bin/env python3
"""1x test: kirim kode verifikasi xAI lewat CAMOUFOX (Firefox), tanpa proxy."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from camoufox.sync_api import Camoufox
from src.tempmail import TempikClient

SIGNUP = "https://accounts.x.ai/sign-up?redirect=grok-com"

tc = TempikClient()
email = tc.create_inbox()
print("inbox:", email, flush=True)

api = {"status": None, "body": ""}


def on_resp(r):
    if "send-verification-code" in r.url:
        api["status"] = r.status
        try:
            api["body"] = r.text()[:300]
        except Exception:
            api["body"] = "<unreadable>"


with Camoufox(headless=False, humanize=True) as browser:
    page = browser.new_page()
    page.on("response", on_resp)
    page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)
    page.evaluate("""() => { const b=[...document.querySelectorAll('button,a,div[role=button]')].find(x=>/sign up with email/i.test(x.innerText||'')); if(b) b.click(); }""")
    page.wait_for_timeout(4000)
    try:
        page.fill("input[type=email]", email, timeout=8000)
    except Exception as e:
        print("fill gagal:", str(e)[:120], flush=True)
    page.wait_for_timeout(600)
    page.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(x=>/continue|next|sign up|submit/i.test(x.innerText||'')); if(b) b.click(); }""")
    page.wait_for_timeout(9000)

    body = page.evaluate("document.body.innerText")
    msgs = re.findall(r"[^\n]*(?:emailed a one time|isn.t available|too many|invalid|verify your email)[^\n]*", body, re.I)
    print("UI:", [m.strip()[:120] for m in msgs][:3], flush=True)
    print("API:", api["status"], api["body"][:200], flush=True)
    print("URL:", page.url, flush=True)
