#!/usr/bin/env python3
"""Recon: daftar endpoint auth yang dipakai halaman sign-up xAI."""
import asyncio, json, re, sys
from patchright.async_api import async_playwright

URL = "https://accounts.x.ai/sign-up?redirect=grok-com"

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        ctx = await b.new_context()
        p = await ctx.new_page()
        srcs = set()
        p.on("response", lambda r: srcs.add(r.url) if r.url.endswith(".js") or ".js?" in r.url else None)
        await p.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await p.wait_for_timeout(8000)
        html = await p.content()
        for m in re.findall(r'src="([^"]+\.js[^"]*)"', html):
            srcs.add(m)
        print(f"{len(srcs)} script(s)")
        found = set()
        for u in sorted(srcs):
            try:
                txt = await p.evaluate("""async (u) => (await (await fetch(u)).text())""", u)
            except Exception as e:
                print("  fail", u[:80], str(e)[:60]); continue
            for m in re.findall(r'["\'`](/?api/auth/[a-z0-9\-_/]+)["\'`]', txt):
                found.add(m)
            for m in re.findall(r'["\'`](/[a-z0-9\-_/]*(?:sign-?up|verify|register|otp)[a-z0-9\-_/]*)["\'`]', txt, re.I):
                found.add(m)
        for f in sorted(found):
            print(" ENDPOINT", f)
        # simpan bundle utk grep manual
        import pathlib
        d = pathlib.Path("data/recon"); d.mkdir(parents=True, exist_ok=True)
        for u in sorted(srcs):
            try:
                txt = await p.evaluate("""async (u) => (await (await fetch(u)).text())""", u)
                (d / (re.sub(r'\W+', '_', u)[-80:] + ".js")).write_text(txt)
            except Exception:
                pass
        await b.close()

asyncio.run(main())
