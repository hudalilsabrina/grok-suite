#!/usr/bin/env python3
"""Solve Turnstile xAI pakai patchright (Chromium) -> print token ke stdout.
Dipanggil sebagai subprocess dari harvest_camoufox.py (venv terpisah)."""
import sys
from patchright.sync_api import sync_playwright

SITEKEY = sys.argv[1] if len(sys.argv) > 1 else "0x4AAAAAAAhr9JGVDZbrZOo0"
URL = "https://accounts.x.ai/sign-up"

HTML = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async></script>'
        '</head><body><div class="cf-turnstile" data-sitekey="' + SITEKEY + '"></div></body></html>')

with sync_playwright() as pw:
    # headless=False: token Turnstile tidak terbit di mode headless (per riset suite)
    b = pw.chromium.launch(headless=False)
    ctx = b.new_context()
    p = ctx.new_page()
    p.route(URL + "/", lambda r: r.fulfill(body=HTML, status=200))
    p.goto(URL + "/", wait_until="domcontentloaded", timeout=45000)
    p.evaluate("() => { const e=document.querySelector('.cf-turnstile'); if(e) e.style.width='70px'; }")
    tok = ""
    for _ in range(30):
        try:
            tok = p.input_value("[name=cf-turnstile-response]", timeout=1500)
        except Exception:
            tok = ""
        if tok:
            break
        try:
            p.locator("//div[@class='cf-turnstile']").click(timeout=1000)
        except Exception:
            pass
        p.wait_for_timeout(500)
    b.close()

if not tok:
    # diagnosa kalau kosong
    sys.stderr.write("no-token\n")
print(tok)
