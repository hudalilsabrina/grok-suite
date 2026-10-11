"""Solver Cloudflare Turnstile untuk xAI (sitekey publik di halaman signup).

Kenapa patchright: Chromium standar bocor sinyal otomasi -> Cloudflare tidak
menerbitkan token. patchright = Chromium yang di-patch -> token 816 char, dan
token itu DITERIMA xAI (bukan `anti-abuse:token-invalid`).

Catatan penting: Camoufox/Firefox TIDAK bisa me-render Turnstile (postMessage
antar-iframe gagal, `window.turnstile` tak pernah terdefinisi). Karena itu
alur harvest: halaman di Camoufox, token di-solve di sini, lalu di-inject.

Pemakaian:
    from src.turnstile import solve
    tok = solve()                      # token / "" kalau gagal
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

SITEKEY = "0x4AAAAAAAhr9JGVDZbrZOo0"          # sitekey Turnstile di accounts.x.ai
SIGNUP_URL = "https://accounts.x.ai/sign-up"

_PAGE = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
         '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async></script>'
         '</head><body><div class="cf-turnstile" data-sitekey="__SITEKEY__"></div></body></html>')


def _needs_xvfb() -> bool:
    """True kalau Linux tanpa DISPLAY (server headless). Windows/macOS: False."""
    return sys.platform.startswith("linux") and not os.environ.get("DISPLAY")


def _run_py() -> list:
    """Command python untuk solver.

    Pakai TS_PYTHON kalau di-set (berguna kalau patchright ada di venv lain),
    kalau tidak pakai python yang menjalankan skrip ini. Di Linux headless
    tambahkan xvfb-run (Turnstile tidak menerbitkan token di mode headless).
    """
    py = os.environ.get("TS_PYTHON") or sys.executable
    script = str(Path(__file__).resolve().parent.parent / "ts_solve_cli.py")
    if _needs_xvfb() and shutil.which("xvfb-run"):
        return ["xvfb-run", "-a", py, script]
    return [py, script]


def solve(sitekey: str = SITEKEY, timeout: int = 120, headless: bool = False) -> str:
    """Ambil token Turnstile. Return "" kalau gagal.

    Dijalankan sebagai subprocess supaya aman dipanggil dari dalam skrip yang
    sudah memakai browser lain (Camoufox) di proses yang sama.
    """
    env = dict(os.environ)
    if headless:
        env["TS_HEADLESS"] = "1"
    try:
        r = subprocess.run(_run_py() + [sitekey], capture_output=True, text=True,
                           timeout=timeout, env=env)
        out = (r.stdout or "").strip().splitlines()
        return out[-1].strip() if out else ""
    except Exception:
        return ""


def inject(page, token: str) -> bool:
    """Tulis token ke input tersembunyi `cf-turnstile-response` di halaman."""
    if not token:
        return False
    page.evaluate("""(tok) => {
        let i = document.querySelector('[name=cf-turnstile-response]');
        if (!i) {
            i = document.createElement('input');
            i.type = 'hidden';
            i.name = 'cf-turnstile-response';
            (document.querySelector('form') || document.body).appendChild(i);
        }
        const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        set.call(i, tok);
        i.dispatchEvent(new Event('input', {bubbles: true}));
        i.dispatchEvent(new Event('change', {bubbles: true}));
    }""", token)
    return True
