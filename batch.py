#!/usr/bin/env python3
"""Batch harvester Grok: buat N akun, log tiap hasil, tangani rate-limit/blokir.

xAI memblokir email-signup sementara setelah ~8-10 percobaan beruntun
(`account:email-signup-unavailable`). Runner ini mendeteksi & berhenti rapi
(progres tersimpan), atau tunggu cooldown.

Pakai: .venv/bin/python batch.py <n> [--cooldown-wait] [--headed]
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import grok

DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)
BLOCK_CODE = "email-signup-unavailable"


def _log(idx, r):
    rec = {"idx": idx, "ts": int(time.time()), "ok": bool(r.get("ok")),
           "email": r.get("email"), "turnstile_len": r.get("turnstile_len"),
           "error": (r.get("error") or "")[:150]}
    with (DATA / "batch_grok.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("--cooldown-wait", action="store_true", help="tunggu 30 menit saat diblokir lalu lanjut")
    ap.add_argument("--headed", action="store_true", help="jalankan browser dengan display (default headed via Xvfb)")
    ap.add_argument("--proxy", default=None, help="satu proxy (http://host:port) untuk semua akun")
    ap.add_argument("--proxy-file", default=None, help="file berisi daftar proxy (satu per baris) — dirotasi")
    a = ap.parse_args()

    proxies = []
    if a.proxy:
        proxies = [a.proxy]
    elif a.proxy_file:
        proxies = [l.strip() for l in Path(a.proxy_file).read_text().splitlines() if l.strip()]
    print(f"[batch] {len(proxies)} proxy" + (f" (rotasi)" if len(proxies) > 1 else ""), flush=True)

    ok = 0
    i = 0
    while i < a.n:
        i += 1
        px = proxies[(i - 1) % len(proxies)] if proxies else None
        r = await grok.harvest_grok(headless=not a.headed, proxy=px)
        rec = _log(i, r)
        if rec["ok"]:
            ok += 1
        print(f"[{i}] {'OK ' if rec['ok'] else 'FAIL'} {rec.get('email')} "
              f"{('via ' + str(px)) if px else ''} {rec.get('error','')}", flush=True)
        if BLOCK_CODE in (r.get("error") or ""):
            print("[batch] xAI memblokir email-signup.", flush=True)
            if a.cooldown_wait:
                print("[batch] menunggu 30 menit...", flush=True)
                await asyncio.sleep(1800)
            else:
                print(f"[batch] berhenti. progres tersimpan. sukses {ok}/{i}", flush=True)
                break
        print(f"=== progress: {i}/{a.n}, sukses {ok} ===", flush=True)
    print(f"SELESAI grok: {ok}/{a.n} sukses", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
