#!/usr/bin/env python3
"""Solve Turnstile xAI pakai patchright (Chromium) -> print token ke stdout.

Dipanggil oleh src/turnstile.py. Jalan di Linux / macOS / Windows.
Set TS_HEADLESS=1 untuk mode headless (di Linux headless: pakai xvfb-run).
"""
import os
import sys

from patchright.sync_api import sync_playwright

SITEKEY = sys.argv[1] if len(sys.argv) > 1 else "0x4AAAAAAAhr9JGVDZbrZOo0"
URL = "https://accounts.x.ai/sign-up"
HEADLESS = os.environ.get("TS_HEADLESS") == "1"

HTML = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async></script>'
        '</head><body><div class="cf-turnstile" data-sitekey="' + SITEKEY + '"></div></body></html>')

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=HEADLESS)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.route(URL + "/", lambda r: r.fulfill(body=HTML, status=200))
    page.goto(URL + "/", wait_until="domcontentloaded", timeout=45000)
    page.evaluate("() => { const e=document.querySelector('.cf-turnstile'); if(e) e.style.width='70px'; }")
    token = ""
    for _ in range(30):
        try:
            token = page.input_value("[name=cf-turnstile-response]", timeout=1500)
        except Exception:
            token = ""
        if token:
            break
        try:
            page.locator("//div[@class='cf-turnstile']").click(timeout=1000)
        except Exception:
            pass
        page.wait_for_timeout(500)
    browser.close()

if not token:
    sys.stderr.write("no-token\n")
print(token)
