#!/usr/bin/env python3
"""Uji hipotesis User-Agent/header: tangkap request ASLI dari Camoufox, lalu
replay dengan header persis sama untuk email lain (tanpa browser).

Hasil: status asli (browser) vs status replay (HTTP murni + header identik).
"""
import json
import re
from pathlib import Path
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent))
from camoufox.sync_api import Camoufox
from src.tempmail import TempikClient

SIGNUP = "https://accounts.x.ai/sign-up?redirect=grok-com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 "
      "Firefox/131.0")


def log(tag, **kw):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {tag} "
          + json.dumps(kw, ensure_ascii=False)[:400], flush=True)


captured = {}


def on_request(r):
    if "send-verification-code" in r.url and r.method == "POST":
        try:
            captured["url"] = r.url
            captured["headers"] = dict(r.headers)
            captured["post"] = r.post_data
        except Exception as e:
            log("capture_err", err=str(e)[:120])


resp = {"status": None, "body": ""}


def on_response(r):
    if "send-verification-code" in r.url:
        resp["status"] = r.status
        try:
            resp["body"] = r.text()[:250]
        except Exception:
            pass


tc_a = TempikClient()
email_a = tc_a.create_inbox()
log("inbox_A", email=email_a)

with Camoufox(headless=False, humanize=True) as browser:
    page = browser.new_page()
    page.on("request", on_request)
    page.on("response", on_response)
    page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(7000)
    page.evaluate("""() => { const b=[...document.querySelectorAll('button,a,div[role=button]')].find(x=>/sign up with email/i.test(x.innerText||'')); if(b) b.click(); }""")
    page.wait_for_timeout(3500)
    page.fill("input[type=email]", email_a, timeout=8000)
    page.wait_for_timeout(500)
    page.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(x=>/continue|next|sign up|submit/i.test(x.innerText||'')); if(b) b.click(); }""")
    page.wait_for_timeout(9000)
    body = page.evaluate("document.body.innerText")
    log("browser_result", api=resp["status"],
        konfirmasi=("emailed a one time" in body.lower()),
        blocked=("isn" in body.lower() and "available" in body.lower()),
        ui=body.replace("\n", " | ")[:180])

if not captured:
    log("STOP", err="request-tidak-tercapture")
    sys.exit(1)
log("captured", url=captured["url"], headers=len(captured["headers"]),
    ua=captured["headers"].get("User-Agent") or captured["headers"].get("user-agent"),
    post_len=len(captured.get("post") or ""))

# ---- replay untuk email B, header identik ----
tc_b = TempikClient()
email_b = tc_b.create_inbox()
log("inbox_B", email=email_b)

post = captured.get("post") or "{}"
try:
    j = json.loads(post)
    if "email" in j:
        j["email"] = email_b
    body2 = json.dumps(j)
except Exception:
    body2 = re.sub(r'"email"\s*:\s*"[^"]*"', f'"email":"{email_b}"', post)

hdrs = {k: v for k, v in captured["headers"].items()
        if k.lower() not in ("content-length", "host", "connection", "accept-encoding")}
hdrs.setdefault("User-Agent", UA)
req = urllib.request.Request(captured["url"], data=body2.encode(), headers=hdrs, method="POST")
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        log("replay_result", status=r.status, body=r.read().decode()[:200])
except urllib.error.HTTPError as e:
    log("replay_result", status=e.code, body=e.read().decode()[:250])
except Exception as e:
    log("replay_result", err=str(e)[:200])
