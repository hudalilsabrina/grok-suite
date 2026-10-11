#!/usr/bin/env python3
"""Probe eligibility domain email di halaman sign-up xAI.

Untuk tiap email: buka sign-up -> Sign up with email -> isi email -> Continue
-> baca pesan UI + respons POST /api/auth/send-verification-code.

Pakai: xvfb-run -a .venv/bin/python probe_domains.py email1@x.com email2@y.com ...
"""
import asyncio
import json
import sys
import re
from patchright.async_api import async_playwright

SIGNUP = "https://accounts.x.ai/sign-up?redirect=grok-com"


async def probe(pw, email, proxy=None):
    kw = {"headless": False}
    if proxy:
        from urllib.parse import urlparse
        u = urlparse(proxy)
        kw["proxy"] = {"server": f"{u.scheme}://{u.hostname}:{u.port}",
                       **({"username": u.username} if u.username else {}),
                       **({"password": u.password} if u.password else {})}
    b = await pw.chromium.launch(**kw)
    ctx = await b.new_context()
    p = await ctx.new_page()
    api = {"status": None, "body": ""}

    async def on_resp(r):
        if "send-verification-code" in r.url:
            api["status"] = r.status
            try:
                api["body"] = (await r.text())[:300]
            except Exception:
                api["body"] = "<unreadable>"

    p.on("response", lambda r: asyncio.ensure_future(on_resp(r)))
    try:
        await p.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        await p.wait_for_timeout(6000)
        await p.evaluate("""() => { const b=[...document.querySelectorAll('button,a,div[role=button]')].find(x=>/sign up with email/i.test(x.innerText||'')); if(b) b.click(); }""")
        await p.wait_for_timeout(3500)
        await p.fill("input[type=email]", email, timeout=8000)
        await p.wait_for_timeout(500)
        await p.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(x=>/continue|next|sign up|submit/i.test(x.innerText||'')); if(b) b.click(); }""")
        await p.wait_for_timeout(8000)
        body = await p.evaluate("document.body.innerText")
        msgs = re.findall(r"[^\n]*(?:invalid|available|wait|wait a|blocked|not allowed|try again|emailed a one time|verify)[^\n]*", body, re.I)
        msgs = [m.strip() for m in msgs if m.strip()][:4]
        return {
            "email": email,
            "api_status": api["status"],
            "api_body": api["body"],
            "ui": msgs,
        }
    except Exception as e:
        return {"email": email, "error": str(e)[:150]}
    finally:
        try:
            await ctx.close()
            await b.close()
        except Exception:
            pass


async def main(emails, proxy=None):
    async with async_playwright() as pw:
        for e in emails:
            r = await probe(pw, e, proxy=proxy)
            print(json.dumps(r, ensure_ascii=False))
            await asyncio.sleep(3)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--proxy=")]
    px = None
    for a in sys.argv[1:]:
        if a.startswith("--proxy="):
            px = a.split("=", 1)[1]
    if not args:
        print("butuh minimal 1 email"); sys.exit(2)
    asyncio.run(main(args, proxy=px))
