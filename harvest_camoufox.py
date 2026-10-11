#!/usr/bin/env python3
"""Engine harvest akun xAI memakai CAMOUFOX (Firefox).

Alur (reverse-engineered, terbukti jalan):
  1. buka accounts.x.ai/sign-up di Camoufox
  2. "Sign up with email" -> isi email temp-mail -> Continue
     (Castle SDK di halaman asli menyertakan `castleRequestToken`; tanpa itu
      server balas 200 {"ok":true} tapi email TIDAK dikirim)
  3. baca kode OTP dari inbox (subject "SpaceXAI confirmation code: NNN-NNN")
  4. POST /api/auth/sign-up/verify-email
  5. form "Complete your sign up": nama + password
  6. Turnstile: Camoufox TIDAK bisa (Firefox) -> solve pakai patchright,
     lalu token di-inject ke halaman Camoufox
  7. POST /api/auth/sign-up/create-account  <-- KUNCI
     {email, password, givenName, familyName, emailValidationCode, turnstileToken}
     (JANGAN klik tombol "Complete sign up": tombol React tidak memicu request
      apa pun saat token di-inject dari luar)
  8. cookie `sso` -> accounts.txt

Jalan di Linux (headless: pakai xvfb-run), macOS, dan Windows.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from camoufox.sync_api import Camoufox
from src import common
from src.mail import make_client
from src.turnstile import solve as solve_turnstile, inject as inject_turnstile

SIGNUP = "https://accounts.x.ai/sign-up?redirect=grok-com"
LOG = ROOT / "data" / "harvest.jsonl"


def log(tag: str, **kw):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"tag": tag, "ts": time.strftime("%H:%M:%S", time.gmtime()), **kw}
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    print(f"[{rec['ts']}] {tag} " + json.dumps(kw, ensure_ascii=False)[:400], flush=True)


def _click(page, rx, kinds="button,a,div[role=button]"):
    return page.evaluate("""([rx, kinds]) => {
        const r = new RegExp(rx, 'i');
        for (const el of document.querySelectorAll(kinds)) {
            const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
            if (t && r.test(t)) { el.click(); return t.slice(0, 40); }
        }
        return null;
    }""", [rx, kinds])


def _set_input(page, which, val):
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


def harvest_one(headless: bool = False, timeout_code: int = 180,
                solve_ts=None, verbose: bool = True) -> dict:
    """Buat 1 akun xAI. Return dict {ok, email, password, sso, error, ...}."""
    out: dict = {"ok": False}
    tc = make_client()
    email = tc.create_inbox()
    common.save_inbox(email, getattr(tc, "session_id", "") or "")
    pwd = common.rand_password()
    gn, fn = common.rand_name()
    out["email"] = email
    if verbose:
        log("inbox", email=email)

    send_api = {"status": None}

    with Camoufox(headless=headless, humanize=True) as browser:
        page = browser.new_page()

        def _on_resp(r):
            if "send-verification-code" in r.url and r.request.method == "POST":
                send_api["status"] = r.status
        page.on("response", _on_resp)

        try:
            page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)
            _click(page, r"sign up with email")
            page.wait_for_timeout(3500)
            _set_input(page, r"email|e-mail", email)
            page.wait_for_timeout(600)
            _click(page, r"^continue$|^(next|sign up|submit)$")
            page.wait_for_timeout(8000)

            body = page.evaluate("document.body.innerText")
            sent = ("emailed a one time" in body.lower()) or ("verify your email" in body.lower())
            if not sent:
                for _ in range(6):
                    page.wait_for_timeout(2500)
                    _click(page, r"^continue$")
                    body = page.evaluate("document.body.innerText")
                    if "emailed a one time" in body.lower() or "verify your email" in body.lower():
                        sent = True
                        break
            out["sent"] = sent
            out["send_api"] = send_api["status"]
            if not sent:
                low = body.lower()
                if "too many" in low:
                    out["error"] = "rate:too-many-code-requests"
                elif "available" in low:
                    out["error"] = "account:email-signup-unavailable"
                else:
                    out["error"] = "no-send"
                if verbose:
                    log("STOP", err=out["error"], api=send_api["status"],
                        ui=body.replace("\n", " | ")[:160])
                return out

            code = common.read_code(tc, email, timeout_code)
            out["code"] = code
            if verbose:
                log("kode", code=code)
            if not code:
                out["error"] = "no-code"
                return out

            boxes = page.query_selector_all("input[maxlength='1']")
            if boxes and len(boxes) >= 6:
                for i, ch in enumerate(code[:6]):
                    boxes[i].fill(ch)
            else:
                _set_input(page, r"code|otp|one-time|verification", code)
            page.wait_for_timeout(1500)
            _click(page, r"^continue$|^(verify|next|submit)$")

            # tunggu form akhir
            form_ok = False
            for _ in range(10):
                page.wait_for_timeout(3000)
                if "complete your sign up" in page.evaluate("document.body.innerText").lower():
                    form_ok = True
                    break
            if verbose:
                log("form", muncul=form_ok)
            if not form_ok:
                out["error"] = "form-tidak-muncul"
                return out

            _set_input(page, r"first", gn)
            _set_input(page, r"last", fn)
            _set_input(page, r"password", pwd)
            page.wait_for_timeout(700)

            # Turnstile: biarkan Camoufox mencoba sebentar (kadang lolos),
            # kalau tidak -> solver patchright + inject.
            tok = ""
            for _ in range(6):
                tok = page.evaluate(
                    "() => (document.querySelector('[name=cf-turnstile-response]')||{}).value || ''")
                if tok:
                    break
                page.wait_for_timeout(2000)
            if not tok:
                solver = solve_ts or solve_turnstile
                tok = solver() or ""
                if tok:
                    inject_turnstile(page, tok)
                    page.wait_for_timeout(2500)
            out["turnstile_len"] = len(tok or "")
            if verbose:
                log("turnstile", n=len(tok or ""))

            # SUBMIT LEWAT API (bukan klik tombol React)
            result = page.evaluate("""async ([email, pwd, gn, fn, code, tok]) => {
                const payload = { email, password: pwd, givenName: gn, familyName: fn,
                                  emailValidationCode: code, turnstileToken: tok };
                try {
                    const r = await fetch('/api/auth/sign-up/create-account', {
                        method: 'POST', credentials: 'include',
                        headers: {'Content-Type': 'application/json', 'Accept': '*/*'},
                        body: JSON.stringify(payload)
                    });
                    return { status: r.status, body: (await r.text()).slice(0, 400) };
                } catch (e) { return { status: 0, body: String(e).slice(0, 200) }; }
            }""", [email, pwd, gn, fn, code, tok])
            out["create_status"] = result["status"]
            if verbose:
                log("create_account", status=result["status"], body=result["body"][:200])

            redirect = ""
            try:
                redirect = json.loads(result["body"]).get("redirectUrl", "")
            except Exception:
                pass
            if redirect:
                page.goto(redirect, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(8000)
            page.wait_for_timeout(2000)

            cookies = page.context.cookies()
            sso = [c["value"] for c in cookies if c["name"] == "sso"]
            if sso:
                out.update(ok=True, password=pwd, sso=sso[0])
                common.append_account(email, pwd, sso[0])
                if verbose:
                    log("SUKSES", email=email, sso=sso[0][:24])
            else:
                out["error"] = "no-sso"
                if verbose:
                    log("STOP", err="no-sso",
                        url=page.url,
                        text=page.evaluate("document.body.innerText")[:200].replace("\n", " | "))
        except Exception as e:
            out["error"] = str(e)[:180]
            if verbose:
                log("ERROR", err=out["error"])
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Harvest 1 akun xAI (Camoufox)")
    ap.add_argument("--headless", action="store_true", help="headless (Linux: pakai xvfb-run)")
    ap.add_argument("--timeout", type=int, default=180, help="timeout tunggu kode OTP (detik)")
    a = ap.parse_args()
    r = harvest_one(headless=a.headless, timeout_code=a.timeout)
    print(json.dumps({k: v for k, v in r.items() if k != "sso"}, ensure_ascii=False))
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
