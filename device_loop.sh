#!/usr/bin/env bash
# Loop device-flow Grok Build: buat sesi device baru -> signup tempik -> authorize.
# Berhenti saat akun masuk pool grok2api (atau habis percobaan).
#   ./device_loop.sh [max_try] [sleep_seconds]
cd "$(dirname "$0")"
N=${1:-60}
SLEEP=${2:-60}
JAR="${G2A_JAR:-/tmp/g2a_dev.jar}"
PASS="${G2A_PASS:?set G2A_PASS (admin password grok2api)}"
mkdir -p data

for i in $(seq 1 "$N"); do
  NOW=$(date -u +%H:%M:%S)
  echo "=== device attempt $i/$NOW ===" >> data/device_loop.log

  # 1) sesi device baru
  rm -f "$JAR"
  curl -s -c "$JAR" -X POST http://127.0.0.1:8000/api/admin/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"admin\",\"password\":\"$PASS\"}" >/dev/null
  RESP=$(curl -s -b "$JAR" -X POST http://127.0.0.1:8000/api/admin/v1/accounts/device/start \
    -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:8000' -d '{}')
  URI=$(printf '%s' "$RESP" | python3 -c 'import sys,json;
try:
  d=json.load(sys.stdin)["data"]; print(d["verificationUriComplete"])
except Exception: print("")')
  if [ -z "$URI" ]; then
    echo "  device/start gagal: $(printf '%s' "$RESP" | head -c 160)" >> data/device_loop.log
    sleep "$SLEEP"; continue
  fi
  echo "  uri=$URI" >> data/device_loop.log

  # 2) jalankan driver — egress bergantian: ganjil = IP langsung, genap = residensial
  if [ $((i % 2)) -eq 0 ]; then
    export GROK_PROXY="${GROK_RESID_PROXY:?set GROK_RESID_PROXY=http://user:pass@host:port}"
    echo "  egress=residential" >> data/device_loop.log
  else
    unset GROK_PROXY
    echo "  egress=direct" >> data/device_loop.log
  fi
  rm -f data/device_steps.jsonl data/device_done.txt
  timeout 420 xvfb-run -a .venv/bin/python device_auth2.py "$URI" >> data/device_loop.log 2>&1

  # 3) sukses kalau pool grok2api bertambah / ada penanda auth
  if [ -f data/device_done.txt ]; then
    echo "AUTH_DONE $NOW" >> data/device_loop.log
    exit 0
  fi
  if grep -q 'GATE' data/device_steps.jsonl 2>/dev/null; then
    echo "  gate tertutup -> tunggu ${SLEEP}s" >> data/device_loop.log
  fi
  sleep "$SLEEP"
done
echo "GIVEUP $(date -u +%H:%M:%S)" >> data/device_loop.log
