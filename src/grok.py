"""Grok Suite - factory akun + harvest SSO/API key Grok (xAI).

Engine: **patchright** (Playwright yang di-patch anti-deteksi) — satu-satunya
cara lolos Cloudflare Turnstile dari IP datacenter (playwright standar bocor
sinyal otomasi -> 0 token; camoufox/Firefox tak bisa init Turnstile sama sekali).

Alur (semua lewat halaman ASLI accounts.x.ai agar Castle SDK aktif):
  1. Buka https://accounts.x.ai/sign-up (patchright, headed + Xvfb)
  2. "Sign up with email" -> isi email tempik -> Continue
     (Castle SDK otomatis menyertakan castleRequestToken — WAJIB, tanpa itu
      server balas 200 {"ok":true} tapi email TIDAK dikirim)
  3. Kode verifikasi masuk ke tempik (subject "SpaceXAI confirmation code: NNN-NNN")
  4. Isi kode -> Continue
  5. Form "Complete your sign up": First/Last name + Password
  6. Turnstile di form akhir -> token dari solver (halaman minimal, patchright)
  7. Submit -> akun dibuat -> cookie SSO

PENTING: xAI kadang mematikan pendaftaran email sementara
(`account:email-signup-unavailable`) — bukan bug kita, tunggu & coba lagi.
"""
import asyncio
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from .config import DATA_DIR
from .inboxstore import save as save_inbox
from .tempmail import TempikClient

C = Console()

SIGNUP_URL = "https://accounts.x.ai/sign-up?redirect=grok-com"
SITEKEY = "0x4AAAAAAAhr9JGVDZbrZOo0"
GIVEN = ["Mason", "Leo", "Ryan", "Kai", "Evan", "Nolan", "Owen", "Adam"]
FAMILY = ["Chen", "Lin", "Wang", "Yang", "Liu", "Zhao", "Wu", "Xu"]
ACCOUNTS = Path(DATA_DIR).parent / "accounts.txt"

# halaman minimal untuk farming token Turnstile
_TS_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>ts</title>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async></script>
</head><body><!-- cf turnstile --></body></html>"""


def _rand_password() -> str:
    import string
    return "Xq9#" + "".join(random.choices(string.ascii_letters + string.digits, k=12)) + "aZ"


def _extract_code(text: str) -> Optional[str]:
    m = re.search(r"\b(\d{3})-(\d{3})\b", text) or re.search(r"\b(\d{6})\b", text)
    return "".join(m.groups()) if m else None


async def solve_turnstile(ctx, sitekey: str = SITEKEY, url: str = SIGNUP_URL,
                          max_attempts: int = 14) -> Optional[str]:
    """Dapatkan token Turnstile via halaman minimal (patchright, async).

    Memakai context yang sama supaya cookie cf_clearance ikut.
    """
    page = await ctx.new_page()
    try:
        u = url + "/" if not url.endswith("/") else url
        div = f'<div class="cf-turnstile" data-sitekey="{sitekey}"></div>'
        html = _TS_PAGE.replace("<!-- cf turnstile -->", div)
        await page.route(u, lambda r: r.fulfill(body=html, status=200))
        await page.goto(u, wait_until="domcontentloaded", timeout=45000)
        await page.evaluate("() => { const e=document.querySelector('.cf-turnstile'); if(e) e.style.width='70px'; }")
        for _ in range(max_attempts):
            try:
                v = await page.input_value("[name=cf-turnstile-response]", timeout=2000)
                if v:
                    return v
                try:
                    await page.locator("//div[@class='cf-turnstile']").click(timeout=1000)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            except Exception:
                pass
        return None
    finally:
        try:
            await page.close()
        except Exception:
            pass


def read_code(tc: TempikClient, email: str, timeout: int = 300) -> Optional[str]:
    """Poll inbox tempik untuk kode verifikasi."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            for m in tc.get_messages(email):
                body = re.sub(r"<[^>]+>", " ",
                              (m.get("body", "") or "") + " " + (m.get("subject", "") or ""))
                code = _extract_code(body)
                if code:
                    return code
        except Exception:
            pass
        time.sleep(5)
    return None


def _parse_proxy(proxy: str) -> Dict[str, Any]:
    """Parse URL proxy jadi format playwright, dukung kredensial.

    "http://user:pass@host:port" -> {"server":"http://host:port","username":..,"password":..}
    "http://host:port"           -> {"server":"http://host:port"}
    """
    from urllib.parse import urlparse
    u = urlparse(proxy)
    scheme = u.scheme or "http"
    server = f"{scheme}://{u.hostname}:{u.port}"
    d: Dict[str, Any] = {"server": server}
    if u.username:
        d["username"] = u.username
    if u.password:
        d["password"] = u.password
    return d


async def harvest_grok(headless: bool = False, timeout_code: int = 300,
                       verbose: bool = True, proxy: str = None,
                       email: str = None, code_file: str = None) -> Dict[str, Any]:
    """Buat 1 akun Grok. Return dict {ok, email, password, sso, error, ...}.

    proxy: opsional, mis. "http://host:port" — untuk rotasi IP (hindari
    rate-limit per-IP). Turnstile tetap lolos tanpa proxy (patchright).

    email     : pakai alamat ini (mis. gmail milik operator) alih-alih buat inbox.
    code_file : baca kode OTP dari file ini (human-in-loop) alih-alih dari inbox.
    """
    from patchright.async_api import async_playwright

    out: Dict[str, Any] = {"site": "grok", "ok": False}
    # Pilih penyedia mail: tempik (default) atau mailtm (GROK_MAIL=mailtm).
    # GROK_DOMAIN memaksa satu domain tertentu (untuk uji eligibility domain).
    mail_provider = (os.environ.get("GROK_MAIL") or "tempik").strip().lower()
    if email:
        # alamat manual (mis. gmail operator) — tidak perlu inbox temp-mail
        tc = None
        mail_provider = "manual"
    elif mail_provider == "mailtm":
        from .mailtm import MailTmClient

        class _MtAdapter:
            """Buka interface tempik (create_inbox/get_messages) untuk mail.tm."""
            def __init__(self):
                self._c = MailTmClient()
                self.session_id = None

            def create_inbox(self, local_part=None, domain=None):
                addr = self._c.create_inbox(username=local_part, domain=domain)
                self.session_id = self._c.token
                return addr

            def get_messages(self, address=None):
                out_m = []
                for m in self._c.get_messages():
                    try:
                        d = self._c.get_message_detail(m["id"])
                    except Exception:
                        d = m
                    out_m.append({
                        "subject": d.get("subject", "") or "",
                        "body": (d.get("text", "") or "") + " " + " ".join(d.get("html") or []),
                    })
                return out_m

        tc = _MtAdapter()
        email = tc.create_inbox()
    else:
        tc = TempikClient()
        email = tc.create_inbox(domain=os.environ.get("GROK_DOMAIN") or None)
    out["domain"] = email.rsplit("@", 1)[-1]
    out["mail_provider"] = mail_provider
    save_inbox("grok", email, (tc.session_id if tc else "") or "", "")
    pwd = _rand_password()
    gn, fn = random.choice(GIVEN), random.choice(FAMILY)
    out["email"] = email
    out["proxy"] = proxy
    if verbose:
        C.print(f"[cyan]grok[/] inbox: {email}" + (f" [dim](proxy {proxy})[/]" if proxy else ""))

    async with async_playwright() as pw:
        launch_kw = {"headless": headless}
        if proxy:
            launch_kw["proxy"] = _parse_proxy(proxy)
        browser = await pw.chromium.launch(**launch_kw)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        logs: List[str] = []
        api_log: List[str] = []
        def _cap(r):
            try:
                api_log.append(f"{r.request.method} {r.url.replace('https://accounts.x.ai','')} -> {r.status}")
            except Exception:
                pass
        page.on("response", _cap)
        page.on("pageerror", lambda e: logs.append("PAGEERR " + str(e)[:200]))
        page.on("console", lambda m: logs.append(f"CONSOLE[{m.type}] {m.text[:200]}") if m.type in ("error", "warning") else None)
        try:
            # timeout lebih pendek saat pakai proxy (biar cepat ganti proxy kalau lambat)
            nav_to = 35000 if proxy else 60000
            await page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=nav_to)
            await page.wait_for_timeout(7000)
            # klik "Sign up with email"
            await page.evaluate("""() => { const b=[...document.querySelectorAll('button,a,div[role=button]')].find(x=>/sign up with email/i.test(x.innerText||'')); if(b) b.click(); }""")
            await page.wait_for_timeout(4000)
            await page.fill("input[type=email]", email, timeout=8000)
            await page.wait_for_timeout(600)
            await page.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(x=>/continue|next|sign up|submit/i.test(x.innerText||'')); if(b) b.click(); }""")
            await page.wait_for_timeout(6000)

            # deteksi email-signup-unavailable (AI vs straight quote!)
            body = await page.evaluate("document.body.innerText")
            if re.search(r"email[- ]sign[- ]?up isn[’']t available|not available right now|isn[’']t available", body, re.I):
                out["error"] = "account:email-signup-unavailable"
                out["hint"] = "xAI menonaktifkan pendaftaran email sementara"
                return out
            # konfirmasi pengiriman (server bilang "We've emailed a one time security code")
            out["sent_confirm"] = "emailed a one time" in body.lower() or "verify your email" in body.lower()
            if verbose:
                C.print(f"[dim]  server konfirmasi kirim: {out['sent_confirm']}[/]")
            if not out["sent_confirm"]:
                out["body_snapshot"] = body[:250]
                if verbose:
                    C.print(f"[dim]  body: {body[:200]}[/]")
                # coba klik Continue lagi (mungkin turnstile belum siap)
                for _ in range(6):
                    await page.wait_for_timeout(2000)
                    await page.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(x=>/continue|next|sign up|submit/i.test(x.innerText||'')); if(b) b.click(); }""")
                    await page.wait_for_timeout(2000)
                    body = await page.evaluate("document.body.innerText")
                    if "emailed a one time" in body.lower() or "verify your email" in body.lower():
                        out["sent_confirm"] = True
                        break
            if not out["sent_confirm"]:
                # jangan buang 300 s polling kode yang tak akan datang
                if re.search(r"too many code requests", body, re.I):
                    out["error"] = "rate:too-many-code-requests"
                    out["hint"] = "limit kirim kode per-IP — tunggu beberapa menit"
                elif re.search(r"isn[’']t available|not available", body, re.I):
                    out["error"] = "account:email-signup-unavailable"
                else:
                    out["error"] = "no-send"
                out["body_snapshot"] = body[:300]
                if verbose:
                    C.print(f"[red]  tidak terkirim: {out['error']}[/]")
                return out

            if code_file:
                if verbose:
                    C.print(f"[cyan]  menunggu kode OTP di {code_file} (human-in-loop)...[/]")
                code = await asyncio.to_thread(_read_code_file, code_file, timeout_code)
            else:
                code = await _read_code_async(tc, email, timeout_code)
            out["code"] = code
            if verbose:
                C.print(f"[dim]  kode: {code}[/]")
            if not code:
                out["error"] = "no-code"
                return out

            # isi kode
            await page.wait_for_timeout(1500)
            boxes = await page.query_selector_all("input[maxlength='1']")
            if boxes and len(boxes) >= 6:
                for i, ch in enumerate(code[:6]):
                    await boxes[i].fill(ch)
            else:
                try:
                    await page.fill("input[autocomplete=one-time-code]", code, timeout=4000)
                except Exception:
                    await page.fill("input[type=text]", code, timeout=4000)
            await page.wait_for_timeout(2500)
            await page.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(x=>/continue|verify|next|submit/i.test(x.innerText||'')); if(b) b.click(); }""")
            await page.wait_for_timeout(7000)

            # isi field form akhir
            async def fill_by(rx, val):
                return await page.evaluate("""([re,val]) => {
                    const rx=new RegExp(re,'i');
                    for (const i of [...document.querySelectorAll('input')]) {
                        const lbl=(i.labels&&i.labels[0]?i.labels[0].innerText:'')+' '+(i.placeholder||'')+' '+(i.name||'')+' '+(i.autocomplete||'');
                        if (rx.test(lbl)) { const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                            s.call(i,val); i.dispatchEvent(new Event('input',{bubbles:true})); i.dispatchEvent(new Event('change',{bubbles:true})); return true; }
                    } return false;
                }""", [rx, val])
            await fill_by(r"first", gn)
            await fill_by(r"last", fn)
            await fill_by(r"password", pwd)

            # turnstile: coba widget asli dulu, lalu solver
            tok = ""
            for _ in range(16):
                tok = await page.evaluate("() => (document.querySelector('[name=cf-turnstile-response]')||{}).value || ''")
                if tok:
                    break
                try:
                    fr = await page.query_selector("iframe[src*=challenges]")
                    if fr:
                        await fr.click(timeout=1500)
                except Exception:
                    pass
                await page.wait_for_timeout(1500)
            if not tok:
                tok = await solve_turnstile(ctx)
                if tok:
                    await page.evaluate("""(tok) => {
                        const i=document.querySelector('[name=cf-turnstile-response]');
                        if(i){ const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                            s.call(i,tok); i.dispatchEvent(new Event('input',{bubbles:true})); i.dispatchEvent(new Event('change',{bubbles:true})); }
                    }""", tok)
            out["turnstile_len"] = len(tok or "")
            if verbose:
                C.print(f"[dim]  turnstile: {len(tok or '')} char[/]")

            # --- diagnisa form akhir ---
            out["inputs"] = await page.evaluate("""() => [...document.querySelectorAll('input')].map(i=>({t:i.type,n:i.name,c:i.autocomplete,v:(i.type==='password'?'*'.repeat((i.value||'').length):(i.value||'').slice(0,40)),valid:i.checkValidity(),msg:i.validationMessage}))""")
            out["buttons"] = await page.evaluate("""() => [...document.querySelectorAll('button')].map(b=>({t:(b.innerText||'').trim().slice(0,40),dis:b.disabled,ty:b.type}))""")
            if verbose:
                C.print(f"[dim]  inputs: {out['inputs']}[/]")
                C.print(f"[dim]  buttons: {out['buttons']}[/]")

            # dengarkan semua respons API saat submit
            api_hits: List[Dict[str, Any]] = []

            def _on_resp(r):
                if "/api/" in r.url:
                    api_hits.append({"url": r.url, "status": r.status})
            page.on("response", _on_resp)

            # submit — pilih tombol yang benar (bukan nav "Sign up"/"Log in")
            def _pick_and_click():
                return page.evaluate("""() => {
                    const bs=[...document.querySelectorAll('button')].filter(b=>!b.disabled);
                    const rx=/complete|create account|sign ?up|continue|submit/i;
                    const bad=/log ?in|sign in|google|apple/i;
                    let b = bs.find(x=>rx.test(x.innerText||'') && !bad.test(x.innerText||'')) || null;
                    if(!b) b = bs.find(x=>x.type==='submit') || null;
                    if(b){ b.click(); return (b.innerText||'').trim().slice(0,40); }
                    return null;
                }""")

            clicked = None
            for sa in range(3):
                clicked = await _pick_and_click()
                out["clicked"] = clicked
                try:
                    await page.wait_for_timeout(12000)
                except Exception:
                    pass
                out.setdefault("submit_tries", []).append({"i": sa, "clicked": clicked, "hits": len(api_hits)})
                if api_hits:
                    break
                # belum ada request sama sekali -> kemungkinan token Turnstile
                # di-re-render / tombol masih disabled -> solve ulang + inject
                if verbose:
                    C.print(f"[dim]  submit#{sa} belum memicu API, ulangi + token ulang[/]")
                tok2 = await solve_turnstile(ctx)
                if tok2:
                    await page.evaluate("""(tok) => {
                        const i=document.querySelector('[name=cf-turnstile-response]');
                        if(i){ const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                            s.call(i,tok); i.dispatchEvent(new Event('input',{bubbles:true})); i.dispatchEvent(new Event('change',{bubbles:true})); }
                    }""", tok2)
                    out["turnstile_len"] = len(tok2)
                await page.wait_for_timeout(2500)
            out["api_hits"] = api_hits
            out["final_url"] = page.url
            out["console"] = logs[-12:]
            if verbose:
                C.print(f"[dim]  clicked={clicked!r} url={out['final_url']} api={api_hits}[/]")
            cookies = await ctx.cookies()
            out["cookie_names"] = [c["name"] for c in cookies]
            sso = [c["value"] for c in cookies if c["name"] == "sso"]
            if sso:
                out["ok"] = True
                out["sso"] = sso[0]
                out["password"] = pwd
                out["name"] = f"{gn} {fn}"
                _append_account(email, pwd, sso[0])
            else:
                out["error"] = "no-sso"
                body = await page.evaluate("document.body.innerText")
                out["body_tail"] = body[:300]
                # kumpulkan error elemen
                err = await page.evaluate("""() => [...document.querySelectorAll('[class*=error],[role=alert],[class*=Error],[class*=alert]')].map(e=>e.innerText).filter(Boolean).join(' | ')""")
                out["ui_error"] = (err or "")[:200]
                if verbose:
                    C.print(f"[dim]  body: {body[:150]}[/]")
                    if err:
                        C.print(f"[dim]  err: {err[:150]}[/]")
        except Exception as e:
            out["error"] = str(e)[:180]
        finally:
            out["api_log"] = api_log[-30:]
            out["console"] = logs[-12:]
            try:
                await ctx.close()
                await browser.close()
            except Exception:
                pass
    return out


def _read_code_file(path: str, timeout: int = 900) -> Optional[str]:
    """Baca kode OTP human-in-loop dari file (ditulis operator saat kode sampai)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if os.path.exists(path):
                txt = open(path, encoding="utf-8", errors="ignore").read()
                m = re.search(r"\b(\d{3})-(\d{3})\b", txt) or re.search(r"\b(\d{6})\b", txt)
                if m:
                    return "".join(m.groups()) if m.lastindex == 2 else m.group(0)
        except Exception:
            pass
        time.sleep(2)
    return None


async def _read_code_async(tc, email, timeout):
    import asyncio
    return await asyncio.to_thread(read_code, tc, email, timeout)


def _append_account(email: str, password: str, sso: str):
    ACCOUNTS.open("a").write(f"{email}:{password}:{sso}\n")


def parse_accounts(path: Path = None) -> List[Dict[str, str]]:
    """Parse accounts.txt: email:password:sso."""
    path = path or ACCOUNTS
    out = []
    if not path.exists():
        return out
    for ln in path.read_text().strip().splitlines():
        ln = ln.strip()
        if ln.count(":") < 2:
            continue
        try:
            email, password, sso = ln.split(":", 2)
            out.append({"email": email, "password": password, "sso": sso})
        except ValueError:
            continue
    return out
