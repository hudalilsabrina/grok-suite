#!/usr/bin/env python3
"""1x harvest akun xAI penuh memakai CAMOUFOX (Firefox), tanpa proxy.

Alur: sign-up → email tempik → kode OTP → Complete your sign up → Turnstile
(sendiri, Camoufox fingerprint) → submit → cookie `sso` → accounts.txt.

Pakai: xvfb-run -a /root/grok-recon/cf-venv/bin/python harvest_camoufox.py
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from camoufox.sync_api import Camoufox
from src.tempmail import TempikClient
from src import grok

SIGNUP = "https://accounts.x.ai/sign-up?redirect=grok-com"
ACCOUNTS = Path(__file__).resolve().parent / "accounts.txt"
LOG = Path(__file__).resolve().parent / "data" / "camo_harvest.jsonl"


def log(tag, **kw):
    rec = {"tag": tag, "ts": time.strftime("%H:%M:%S", time.gmtime()), **kw}
    LOG.open("a").write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{rec['ts']}] {tag} " + json.dumps({k: v for k, v in kw.items()}, ensure_ascii=False)[:400], flush=True)


def click(page, rx, kinds="button,a,div[role=button]"):
    return page.evaluate("""([rx, kinds]) => {
        const r = new RegExp(rx, 'i');
        for (const el of document.querySelectorAll(kinds)) {
            const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
            if (t && r.test(t)) { el.click(); return t.slice(0, 40); }
        }
        return null;
    }""", [rx, kinds])


def set_input(page, which, val):
    return page.evaluate("""([which, val]) => {
        const rx = new RegExp(which, 'i');
        for (const i of [...document.querySelectorAll('input')]) {
            const lbl = ((i.labels && i.labels[0] ? i.labels[0].innerText : '') + ' ' +
                         (i.placeholder||'') + ' ' + (i.name||'') + ' ' + (i.autocomplete||'') + ' ' + (i.type||''));
            if (rx.test(lbl)) {
                const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                s.call(i, val);
                i.dispatchEvent(new Event('input', {bubbles:true}));
                i.dispatchEvent(new Event('change', {bubbles:true}));
                return true;
            }
        }
        return false;
    }""", [which, val])


def solve_ts_patchright(sitekey="0x4AAAAAAAhr9JGVDZbrZOo0", timeout=120):
    """Solve Turnstile pakai patchright (Chromium) via subprocess (venv grok-suite)."""
    import subprocess
    py = os.environ.get("TS_PYTHON", sys.executable)
    try:
        r = subprocess.run([py, str(Path(__file__).resolve().parent / "ts_solve_cli.py"), sitekey],
                           capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
    except Exception as e:
        log("ts_patchright_err", err=str(e)[:150])
        return ""


def main():
    tc = TempikClient()
    email = tc.create_inbox()
    pwd = grok._rand_password()
    gn, fn = grok.GIVEN[2], grok.FAMILY[2]
    save_inbox = __import__("src.inboxstore", fromlist=["save"]).save
    save_inbox("grok", email, tc.session_id or "", "")
    log("inbox", email=email)

    api = {"status": None, "body": ""}

    with Camoufox(headless=False, humanize=True) as browser:
        page = browser.new_page()
        page.on("response", lambda r: (api.update({"status": r.status,
                                                   "body": (r.text()[:300] if r.request.method == "POST" else "")})
                                       if "send-verification-code" in r.url else None))
        create_api = {"status": None, "body": ""}
        api_posts = []

        def _cap_api(r):
            if "/api/" in r.url and r.request.method == "POST":
                try:
                    body = r.text()[:250]
                except Exception:
                    body = "<stream>"
                api_posts.append({"u": r.url.split("/api/")[-1][:60], "s": r.status, "b": body})
        page.on("response", _cap_api)
        page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        click(page, r"sign up with email")
        page.wait_for_timeout(3500)
        set_input(page, r"email|e-mail", email)
        page.wait_for_timeout(600)
        click(page, r"^continue$|^(next|sign up|submit)$")
        page.wait_for_timeout(8000)

        body = page.evaluate("document.body.innerText")
        if "emailed a one time" not in body.lower() and "verify your email" not in body.lower():
            for _ in range(6):
                page.wait_for_timeout(2500)
                click(page, r"^continue$")
                body = page.evaluate("document.body.innerText")
                if "emailed a one time" in body.lower() or "verify your email" in body.lower():
                    break
        log("kirim", api=api["status"], konfirmasi=("emailed a one time" in body.lower()),
            ui=body.replace("\n", " | ")[:200])
        if "emailed a one time" not in body.lower() and "verify your email" not in body.lower():
            log("STOP", err="gate-tutup")
            return

        code = grok.read_code(tc, email, 180)
        log("kode", code=code)
        if not code:
            log("STOP", err="no-code")
            return
        boxes = page.query_selector_all("input[maxlength='1']")
        if boxes and len(boxes) >= 6:
            for i, ch in enumerate(code[:6]):
                boxes[i].fill(ch)
        else:
            set_input(page, r"code|otp|one-time|verification", code)
        page.wait_for_timeout(1500)
        click(page, r"^continue$|^(verify|next|submit)$")

        # tunggu form Complete your sign up
        ok = False
        for _ in range(10):
            page.wait_for_timeout(3000)
            t = page.evaluate("document.body.innerText")
            if "complete your sign up" in t.lower():
                ok = True
                break
        log("form", muncul=ok)
        if not ok:
            log("STOP", err="form-tidak-muncul")
            return

        set_input(page, r"first", gn)
        set_input(page, r"last", fn)
        set_input(page, r"password", pwd)
        page.wait_for_timeout(700)

        # Turnstile: coba paksa widget (manusia-like) + tunggu self-pass
        tok = ""
        diag = {}
        for i in range(45):
            tok = page.evaluate("""() => (document.querySelector('[name=cf-turnstile-response]')||{}).value || ''""")
            if tok:
                break
            if i % 4 == 3:
                diag = page.evaluate("""() => ({
                    hasTurnstile: typeof window.turnstile,
                    hasRespInput: !!document.querySelector('[name=cf-turnstile-response]'),
                    hasWidgetDiv: !!document.querySelector('.cf-turnstile'),
                    tsScripts: [...document.querySelectorAll('script')].map(s=>s.src||'').filter(s=>/turnstile|challenges/.test(s)),
                    iframes: [...document.querySelectorAll('iframe')].map(f=>(f.src||'').slice(0,80)),
                    widgetText: (document.querySelector('.cf-turnstile')||{}).innerText || '',
                    respLen: ((document.querySelector('[name=cf-turnstile-response]')||{}).value||'').length
                })""")
                log("ts_diag", **diag)
                # klik elemen widget dengan mouse (bukan JS click)
                try:
                    box = page.evaluate("""() => {
                        const w = document.querySelector('.cf-turnstile') ||
                                  document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                        if (!w) return null;
                        const r = w.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height};
                    }""")
                    if box and box["w"] > 0:
                        page.mouse.move(box["x"] - 60, box["y"] - 40, steps=8)
                        page.wait_for_timeout(250)
                        page.mouse.move(box["x"], box["y"], steps=12)
                        page.wait_for_timeout(250)
                        page.mouse.click(box["x"], box["y"])
                        log("ts_click", x=int(box["x"]), y=int(box["y"]))
                except Exception as e:
                    log("ts_click_err", err=str(e)[:120])
            page.wait_for_timeout(2000)
        log("turnstile", n=len(tok), percobaan="forced")

        # fallback: kalau Camoufox tak menerbitkan token, solve pakai patchright + inject
        if not tok:
            log("ts_fallback", msg="solve via patchright")
            tok = solve_ts_patchright()
            log("ts_patchright", n=len(tok))
            if tok:
                page.evaluate("""(tok) => {
                    let i = document.querySelector('[name=cf-turnstile-response]');
                    if (!i) {
                        i = document.createElement('input');
                        i.type = 'hidden'; i.name = 'cf-turnstile-response';
                        (document.querySelector('form') || document.body).appendChild(i);
                    }
                    const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                    s.call(i, tok);
                    i.dispatchEvent(new Event('input', {bubbles:true}));
                    i.dispatchEvent(new Event('change', {bubbles:true}));
                }""", tok)
                page.wait_for_timeout(2500)

        # --- submit via API langsung (dari konteks halaman Camoufox, bawa cookie sesi) ---
        pre = page.evaluate("""() => ({
            inputs: [...document.querySelectorAll('input')].map(i=>({t:i.type, n:(i.name||'').slice(0,24), len:(i.value||'').length, valid:i.checkValidity(), msg:(i.validationMessage||'').slice(0,60)})),
            respToken: ((document.querySelector('[name=cf-turnstile-response]')||{}).value||'').length
        })""")
        log("pre_submit", inputs=pre["inputs"][:6], respToken=pre["respToken"])

        result = page.evaluate("""async ([email, pwd, gn, fn, code, tok]) => {
            const payload = { email, password: pwd, givenName: gn, familyName: fn,
                              emailValidationCode: code, turnstileToken: tok };
            try {
                const r = await fetch('/api/auth/sign-up/create-account', {
                    method: 'POST', credentials: 'include',
                    headers: {'Content-Type': 'application/json', 'Accept': '*/*'},
                    body: JSON.stringify(payload)
                });
                const txt = await r.text();
                return { status: r.status, body: txt.slice(0, 400) };
            } catch (e) { return { status: 0, body: String(e).slice(0, 200) }; }
        }""", [email, pwd, gn, fn, code, tok])
        log("create_account", status=result["status"], body=result["body"])

        redirect = ""
        try:
            redirect = json.loads(result["body"]).get("redirectUrl", "")
        except Exception:
            pass
        if redirect:
            log("redirect", url=redirect[:120])
            page.goto(redirect, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(8000)

        page.wait_for_timeout(3000)
        log("api_posts", posts=api_posts[-6:])

        cookies = page.context.cookies()
        names = [c["name"] for c in cookies]
        sso = [c["value"] for c in cookies if c["name"] == "sso"]
        final_text = page.evaluate("document.body.innerText")[:300].replace("\n", " | ")
        log("akhir", url=page.url, cookies=names[:20], text=final_text)
        if sso:
            with ACCOUNTS.open("a") as f:
                f.write(f"{email}:{pwd}:{sso[0]}\n")
            log("SUKSES", email=email, sso=sso[0][:24])
        else:
            log("STOP", err="no-sso")


main()
