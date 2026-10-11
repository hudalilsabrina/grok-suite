#!/usr/bin/env python3
"""OAuth device flow xAI (Grok Build) — signup baru pakai email tempik, lalu authorize.

Pakai: xvfb-run -a .venv/bin/python device_auth2.py <verification_uri_complete>
"""
import asyncio
import os
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patchright.async_api import async_playwright
from src.tempmail import TempikClient
from src import grok

URL = sys.argv[1]
STEPLOG = Path(__file__).resolve().parent / "data" / "device_steps.jsonl"


def log(tag, **kw):
    rec = {"tag": tag, "ts": time.strftime("%H:%M:%S", time.gmtime()), **kw}
    STEPLOG.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{rec['ts']}] {tag} " + json.dumps({k: v for k, v in kw.items()}, ensure_ascii=False)[:450], flush=True)


async def state(p, tag):
    s = await p.evaluate("""() => ({
        url: location.href,
        buttons: [...document.querySelectorAll('button')].map(b=>({t:(b.innerText||'').trim().slice(0,40), dis:b.disabled})).filter(x=>x.t),
        links: [...document.querySelectorAll('a')].map(a=>(a.innerText||'').trim()).filter(Boolean).slice(0,12),
        inputs: [...document.querySelectorAll('input')].map(i=>({t:i.type, ph:i.placeholder, ac:i.autocomplete})),
        text: document.body.innerText.slice(0, 600)
    })""")
    log(tag, url=s["url"], buttons=s["buttons"], links=s["links"], inputs=s["inputs"])
    log(tag + ".text", text=s["text"].replace("\n", " | ")[:450])
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
    gn, fn = grok.GIVEN[1], grok.FAMILY[1]
    log("inbox", email=email)

    async with async_playwright() as pw:
        import os as _os
        _px = _os.environ.get("GROK_PROXY") or None
        kw = {"headless": False}
        if _px:
            from urllib.parse import urlparse as _up
            _u = _up(_px)
            kw["proxy"] = {"server": f"{_u.scheme}://{_u.hostname}:{_u.port}",
                            **({"username": _u.username} if _u.username else {}),
                            **({"password": _u.password} if _u.password else {})}
            log("proxy", px=_px.split("@")[-1])
        b = await pw.chromium.launch(**kw)
        ctx = await b.new_context()
        p = await ctx.new_page()
        try:
            # 1. halaman device: kode sudah terisi -> Continue
            await p.goto(URL, wait_until="domcontentloaded", timeout=60000)
            await p.wait_for_timeout(6000)
            await state(p, "1_device")
            t = await click(p, r"^continue$")
            log("klik_device_continue", t=t)
            await p.wait_for_timeout(6000)
            st = await state(p, "2_login")

            # 2. kalau bukan di halaman sign-up, ke "Sign up"
            if "sign-up" not in st["url"]:
                t = await click(p, r"^sign up$")
                log("klik_sign_up_link", t=t)
                await p.wait_for_timeout(6000)
                st = await state(p, "3_signup_page")

            # 3. "Sign up with email" bila ada tombol itu
            t = await click(p, r"sign up with email")
            if t:
                log("klik_signup_email_btn", t=t)
                await p.wait_for_timeout(4000)

            await set_input(p, r"email|e-mail", email)
            await p.wait_for_timeout(700)
            t = await click(p, r"^continue$|^(next|sign up|submit)$")
            log("klik_kirim_email", t=t)
            await p.wait_for_timeout(7000)
            st = await state(p, "4_setelah_kirim")

            body = st["text"]
            if "emailed a one time" not in body.lower() and "verify your email" not in body.lower():
                # coba Continue beberapa kali (turnstile mungkin belum siap)
                for i in range(6):
                    await p.wait_for_timeout(2500)
                    await click(p, r"^continue$")
                    st = await state(p, f"4_retry_{i}")
                    if "emailed a one time" in st["text"].lower() or "verify your email" in st["text"].lower():
                        break
                    if "isn" in st["text"].lower() and "available" in st["text"].lower():
                        log("GATE", err="email-signup-unavailable")
                        return
            if "emailed a one time" in st["text"].lower() or "verify your email" in st["text"].lower():
                log("kode_terkirim", email=email)
            else:
                log("kode", err="konfirmasi tidak terlihat")
                return

            # 4. isi kode OTP dari tempik
            code = await asyncio.to_thread(grok.read_code, tc, email, 180)
            log("kode", code=code)
            if not code:
                log("GAGAL", err="no-code")
                return
            boxes = await p.query_selector_all("input[maxlength='1']")
            if boxes and len(boxes) >= 6:
                for i, ch in enumerate(code[:6]):
                    await boxes[i].fill(ch)
            else:
                await set_input(p, r"code|otp|one-time|verification", code)
            await p.wait_for_timeout(2000)
            t = await click(p, r"^continue$|^(verify|next|submit)$")
            log("klik_verify", t=t)

            # tunggu form "Complete your sign up" muncul
            ok_form = False
            for i in range(10):
                await p.wait_for_timeout(3000)
                st = await state(p, f"5_form_{i}")
                if "complete your sign up" in st["text"].lower():
                    ok_form = True
                    break
            if not ok_form:
                log("GAGAL", err="form-complete-tidak-muncul")
                return

            # isi nama + kata sandi + turnstile, lalu "Complete sign up"
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
            t = await click(p, r"^complete sign up$")
            if not t:
                t = await click(p, r"complete sign up|create account|^sign up$|^continue$")
            log("klik_complete_signup", t=t)
            await p.wait_for_timeout(12000)
            st = await state(p, "6_setelah_signup")

            # layar otorisasi device — jangan sentuh tombol cookie banner
            auth_ok = False
            for i in range(8):
                txt_l = st["text"].lower()
                if any(x in txt_l for x in ("you can close", "success", "approved",
                                            "authorized", "device connected")):
                    log("AUTH_SELESAI", url=st["url"])
                    auth_ok = True
                    break
                if "complete your sign up" in txt_l:
                    await set_input(p, r"first", gn)
                    await set_input(p, r"last", fn)
                    await set_input(p, r"password", pwd)
                    t = await click(p, r"^complete sign up$")
                    log(f"klik_complete_lagi_{i}", t=t)
                    await p.wait_for_timeout(9000)
                    st = await state(p, f"7_signup_{i}")
                    continue
                t = await click(p, r"^(continue|authorize|allow|approve|accept|confirm)$",
                                kinds="button,a")
                if t and re.search(r"cookie|privacy|reject|allow all|confirm my choices",
                                   t, re.I):
                    t = None
                log(f"klik_auth_{i}", t=t)
                if not t:
                    t = await click(p, r"^(continue|authorize|allow|approve)$", kinds="button,a")
                    log(f"klik_auth_fb_{i}", t=t)
                await p.wait_for_timeout(7000)
                st = await state(p, f"7_auth_{i}")

            cookies = await ctx.cookies()
            log("cookies", names=[c["name"] for c in cookies])
            if auth_ok:
                Path(__file__).resolve().parent / "data" / "device_done.txt".write_text(
                    json.dumps({"url": p.url, "text": st["text"][:400]}))
            else:
                log("belum_otorisasi", url=p.url)
        except Exception as e:
            log("exception", err=str(e)[:300])
        finally:
            try:
                await ctx.close()
                await b.close()
            except Exception:
                pass


asyncio.run(main())
