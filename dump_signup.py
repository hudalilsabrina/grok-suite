#!/usr/bin/env python3
"""Dump semua tombol/link di halaman sign-up xAI (cek jalur alternatif)."""
import asyncio, json
from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=("--headless" not in __import__("sys").argv))
        p = await (await b.new_context()).new_page()
        await p.goto("https://accounts.x.ai/sign-up?redirect=grok-com",
                     wait_until="domcontentloaded", timeout=60000)
        await p.wait_for_timeout(7000)
        out = await p.evaluate("""() => ({
            buttons: [...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim()).filter(Boolean),
            links: [...document.querySelectorAll('a')].map(a=>({t:(a.innerText||'').trim(), h:a.getAttribute('href')})).filter(x=>x.t),
            inputs: [...document.querySelectorAll('input')].map(i=>({t:i.type, ph:i.placeholder})),
            text: document.body.innerText.slice(0,600)
        })""")
        print(json.dumps(out, indent=1, ensure_ascii=False))
        await b.close()

asyncio.run(main())
