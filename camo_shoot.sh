#!/usr/bin/env bash
# Tembak: 1 test camoufox tiap N detik sampai dapat 1 akun atau habis percobaan.
#   ./camo_shoot.sh [max_try] [sleep_seconds]
cd "$(dirname "$0")"
N=${1:-12}
SLEEP=${2:-300}
for i in $(seq 1 "$N"); do
  echo "=== tembak $i/$(date -u +%H:%M:%S) ===" >> data/shoot.log
  timeout 700 xvfb-run -a ${CAMO_PY:-python3} harvest_camoufox.py >> data/shoot.log 2>&1
  if [ -s accounts.txt ]; then
    echo "SUCCESS $(date -u +%H:%M:%S)" >> data/shoot.log
    exit 0
  fi
  if grep -q 'gate-tutup' data/camo_harvest.jsonl 2>/dev/null; then
    echo "  gate tutup -> tunggu ${SLEEP}s" >> data/shoot.log
  else
    echo "  belum dapat (bukan gate) -> tunggu ${SLEEP}s" >> data/shoot.log
  fi
  sleep "$SLEEP"
done
echo "GIVEUP $(date -u +%H:%M:%S)" >> data/shoot.log
