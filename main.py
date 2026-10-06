#!/usr/bin/env python3
"""Grok Suite - CLI: harvest akun Grok (xAI), test SSO, sync ke 9router.

Command:
  harvest [n]      Buat n akun Grok (default 1)
  test             Test semua SSO tersimpan (panggil API grok)
  report           Ringkasan akun
  sync             Inject akun ke 9router (node openai-compatible)
  probe            Cek apakah pendaftaran email xAI sedang aktif
"""
import argparse
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rich.console import Console
from rich.table import Table
from rich import box

from src import grok

C = Console()
ACCOUNTS = Path(__file__).resolve().parent / "accounts.txt"

GROK_API = "https://api.x.ai/v1"


def cmd_harvest(n):
    ok = 0
    for i in range(1, n + 1):
        C.print(f"[cyan]=== Akun {i}/{n} ===[/]")
        r = asyncio.run(grok.harvest_grok(headless=False))
        if r.get("ok"):
            ok += 1
            C.print(f"[green]  OK {r['email']} | SSO {r['sso'][:30]}...[/]")
        else:
            C.print(f"[yellow]  gagal: {r.get('error')}[/]")
            if r.get("error") == "account:email-signup-unavailable":
                C.print("[red]  xAI mematikan pendaftaran email sementara — berhenti.[/]")
                break
    C.print(f"\n[bold]Selesai: {ok}/{n} sukses[/]")


def cmd_test():
    accs = grok.parse_accounts()
    if not accs:
        C.print("[yellow]Belum ada akun. Jalankan: ./run.sh harvest[/]")
        return
    t = Table(box=box.ROUNDED, title=f"Grok SSO ({len(accs)})")
    t.add_column("Email", style="cyan")
    t.add_column("SSO", style="green")
    for a in accs:
        t.add_row(a["email"][:34], a["sso"][:24] + "...")
    C.print(t)


def cmd_report():
    accs = grok.parse_accounts()
    C.print(f"[bold]Total akun Grok: {len(accs)}[/]")
    for a in accs:
        C.print(f"  {a['email']:<36} sso {a['sso'][:18]}...")


def cmd_sync():
    from src import router9
    accs = grok.parse_accounts()
    if not accs:
        C.print("[yellow]Tidak ada akun untuk disync[/]")
        return
    # SSO dipakai sebagai apiKey (grok menerima bearer sso)
    rows = [{"email": a["email"], "key": a["sso"]} for a in accs]
    r = router9.ingest_gateway("grok-xai", "grok", GROK_API, rows, None)
    C.print(json.dumps(r))


def cmd_probe():
    """Cek apakah email-signup xAI aktif (tanpa browser)."""
    import re
    tc = grok.TempikClient()
    email = tc.create_inbox()
    req = urllib.request.Request(
        "https://accounts.x.ai/api/auth/send-verification-code",
        data=json.dumps({"email": email}).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            "Origin": "https://accounts.x.ai",
            "Referer": grok.SIGNUP_URL,
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        },
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            C.print(f"status {r.status}: {r.read().decode()[:150]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:250]
        C.print(f"[yellow]status {e.code}: {body}[/]")
        if "email-signup-unavailable" in body:
            C.print("[red]=> Pendaftaran email xAI sedang DIMATIKAN.[/]")
        elif e.code == 403 and "cloudflare" in body.lower():
            C.print("[yellow]=> Kena Cloudflare (butuh token browser). Cek via `harvest`.[/]")
        elif e.code == 400:
            C.print("[green]=> Endpoint AKTIF (400 = validasi normal, bukan diblokir).[/]")
        else:
            C.print("[green]=> Endpoint merespons (cek via browser utk kirim sungguhan).[/]")


def cmd_check_inbox():
    """Cek inbox riwayat untuk kode yang mungkin telat masuk."""
    import re
    from src import inboxstore
    hist = inboxstore.history("grok")
    if not hist:
        C.print("[yellow]Belum ada riwayat inbox.[/]")
        return
    C.print(f"cek {len(hist)} inbox riwayat (10 terakhir)...")
    for h in hist[-10:]:
        tc = grok.TempikClient()
        tc.session_id = h["session_id"]
        try:
            msgs = tc.get_messages(h["email"])
            if msgs:
                txt = re.sub(r"<[^>]+>", " ", (msgs[0].get("body", "") or "") + " " + (msgs[0].get("subject", "") or ""))
                code = grok._extract_code(txt)
                C.print(f"  [green]{h['email']}: {len(msgs)} pesan | KODE={code}[/]")
            else:
                C.print(f"  [dim]{h['email']}: 0 pesan[/]")
        except Exception as e:
            C.print(f"  [dim]{h['email']}: {str(e)[:50]}[/]")


def main():
    ap = argparse.ArgumentParser(prog="grok", description="Grok Suite")
    sub = ap.add_subparsers(dest="cmd")
    h = sub.add_parser("harvest"); h.add_argument("n", nargs="?", type=int, default=1)
    sub.add_parser("test")
    sub.add_parser("report")
    sub.add_parser("sync")
    sub.add_parser("probe")
    sub.add_parser("check-inbox")
    a = ap.parse_args()
    if a.cmd == "harvest":
        cmd_harvest(a.n)
    elif a.cmd == "test":
        cmd_test()
    elif a.cmd == "report":
        cmd_report()
    elif a.cmd == "sync":
        cmd_sync()
    elif a.cmd == "probe":
        cmd_probe()
    elif a.cmd == "check-inbox":
        cmd_check_inbox()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
