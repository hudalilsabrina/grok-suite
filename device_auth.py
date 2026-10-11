#!/usr/bin/env python3
"""Jalankan OAuth device flow xAI (Grok Build) sampai selesai, pakai email tempik.

Pakai: xvfb-run -a .venv/bin/python device_auth.py <verification_uri_complete> <sessionId>
"""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patchright.async_api import async_playwright
from src.tempmail import TempikClient
from src import grok

URL = sys.argv[1]
SID = sys.argv[2] if len(sys.argv) > 2 else ""
G2A = "http://127.0.0.1:8000"
JAR = os.environ.get("G2A_JAR", "/tmp/g2a_dev.jar")
STEPLOG = Path(__file__).resolve().parent / "data" / "device_steps.jsonl"


def log(tag, **kw):
    rec = {"tag": tag, "ts": time.strftime("%H:%M:%S", time.gmtime()), **kw}
    STEPLOG.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{rec['ts']}] {tag} {json.dumps({k: v for k, v in kw.items()}, ensure_ascii=False)[:400]}", flush=True)


async def state(p, tag):
    s = await p.evaluate("""() => ({
        url: location.href,
        buttons: [...document.querySelectorAll('button')].map(b=>({t:(b.innerText||'').trim().slice(0,40), dis:b.disabled})).filter(x=>x.t),
        links: [...document.querySelectorAll('a')].map(a=>(a.innerText||'').trim()).filter(Boolean).slice(0,15),
        inputs: [...document.querySelectorAll('input')].map(i=>({t:i.type, ph:i.placeholder, ac:i.autocomplete})),
        text: document.body.innerText.slice(0, 700)
    })""")
    log(tag, **{k: s[k] for k in ("url", "buttons", "links", "inputs")})
    log(tag + ".text", text=s["text"].replace("\n", " | ")[:500])
    return s


async def click(p, rx, kinds="button,a,div[role=button]"):
    return await p.evaluate("""([rx, kinds]) => {
        const r = new RegExp(rx, 'i');
        for (const el of document.querySelectorAll(kinds)) {
            const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
            if (t && r.test(t)) { el.click(); return t.slice(0, 40); }
        }
        return null;
    }""", [rx, kinds])


async def set_input(p, which, val):
    return await p.evaluate("""([which, val]) => {
        const rx = new RegExp(which, 'i');
        for (const i of [...document.querySelectorAll('input')]) {
            const lbl = ((i.labels && i.labels[0] ? i.labels[0].innerText : '') + ' ' +
                         (i.placeholder||'') + ' ' + (i.name||'') + ' ' + (i.autocomplete||'') + ' ' + (i.type||''));
            if (rx.test(lbl)) {
                const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                s.call(i, val);
                i.dispatchEvent(new Event('input', {bubbles: true}));
                i.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
            }
        }
        return false;
    }""", [which, val])


async def main():
    tc = TempikClient()
    email = tc.create_inbox()
    pwd = grok._rand_password()
    gn, fn = grok.GIVEN[0], grok.FAMILY[0]
    log("inbox", email=email, pwd_len=len(pwd))

    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=False)
        ctx = await b.new_context()
        p = await ctx.new_page()
        try:
            await p.goto(URL, wait_until="domcontentloaded", timeout=60000)
            await p.wait_for_timeout(7000)
            await state(p, "1_awal")

            # 1) kalau ada tombol "Sign up with email", pakai jalur email
            t = await click(p, r"sign up with email")
            if t:
                log("klik_sign_up_email", t=t)
                await p.wait_for_timeout(3500)
            await state(p, "2_form")

            # 2) isi email
            await set_input(p, r"email|e-mail", email)
            await p.wait_for_timeout(700)
            t = await click(p, r"^(continue|next|sign up|submit|register)$")
            log("klik_continue1", t=t)
            await p.wait_for_timeout(7000)
            st = await state(p, "3_setelah_email")

            # 3) ambil kode dari tempik
            code = await asyncio.to_thread(grok.read_code, tc, email, 180)
            log("kode", code=code)
            if not code:
                log("gagal", err="no-code")
                return
            boxes = await p.query_selector_all("input[maxlength='1']")
            if boxes and len(boxes) >= 6:
                for i, ch in enumerate(code[:6]):
                    await boxes[i].fill(ch)
            else:
                await set_input(p, r"code|otp|one-time|verification", code)
            await p.wait_for_timeout(2000)
            t = await click(p, r"continue|verify|next|submit")
            log("klik_verify", t=t)
            await p.wait_for_timeout(7000)
            await state(p, "4_setelah_kode")

            # 4) form lengkapi pendaftaran (nama/kata sandi) bila ada
            await set_input(p, r"first", gn)
            await set_input(p, r"last", fn)
            await set_input(p, r"password", pwd)
            await p.wait_for_timeout(800)
            tok = await grok.solve_turnstile(ctx)
            log("turnstile", n=len(tok or ""))
            if tok:
                await p.evaluate("""(tok) => {
                    const i = document.querySelector('[name=cf-turnstile-response]');
                    if (i) { const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                        s.call(i, tok); i.dispatchEvent(new Event('input',{bubbles:true})); i.dispatchEvent(new Event('change',{bubbles:true})); }
                }""", tok)
            t = await click(p, r"complete|create account|sign up|continue|submit|register")
            log("klik_complete", t=t)
            await p.wait_for_timeout(9000)
            await state(p, "5_setelah_signup")

            # 5) layar otorisasi device
            for i in range(6):
                st = await state(p, f"6_otorisasi_{i}")
                t = await click(p, r"^(authorize|allow|approve|continue|accept|confirm|grant access|yes)")
                log(f"klik_authorize_{i}", t=t)
                if not t:
                    t = await click(p, r"authorize|allow|approve|accept|grant")
                    log(f"klik_authorize_fallback_{i}", t=t)
                await p.wait_for_timeout(6000)
                if "oauth2/device" not in st["url"] or any(
                    x in st["text"].lower() for x in ("success", "you can close", "approved", "authorized")):
                    break

            cookies = await ctx.cookies()
            log("cookies", names=[c["name"] for c in cookies])
            log("final", url=p.url, text=(await p.evaluate("document.body.innerText"))[:300].replace("\n", " | "))
        except Exception as e:
            log("exception", err=str(e)[:300])
        finally:
            try:
                await ctx.close()
                await b.close()
            except Exception:
                pass


asyncio.run(main())
