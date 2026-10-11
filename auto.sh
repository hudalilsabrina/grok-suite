#!/usr/bin/env bash
# Coba harvest sampai TARGET akun ada atau habis percobaan.
#   ./auto.sh [max_attempts] [sleep_seconds] [target_akun]
# Saat xAI mematikan email-signup, satu percobaan berhenti cepat (~45 dtk).
# Saat jendela terbuka, satu percobaan bisa menghasilkan beberapa akun.
cd "$(dirname "$0")"
N=${1:-20}
SLEEP=${2:-1200}
TARGET=${3:-3}
for i in $(seq 1 "$N"); do
  NOW=$(date -u +%H:%M:%S)
  N_NOW=$( [ -s accounts.txt ] && wc -l < accounts.txt || echo 0 )
  echo "ATTEMPT $i $NOW (punya: $N_NOW/$TARGET)"
  echo "=== attempt $i/$NOW (punya: $N_NOW/$TARGET) ===" >> data/auto.log
  xvfb-run -a ./run.sh harvest "$TARGET" --no-proxy >> data/auto.log 2>&1
  N_NOW=$( [ -s accounts.txt ] && wc -l < accounts.txt || echo 0 )
  if [ "$N_NOW" -ge "$TARGET" ]; then
    echo "SUCCESS $NOW akun=$N_NOW"
    echo "SUCCESS $(date -u +%H:%M:%S) akun=$N_NOW" >> data/auto.log
    exit 0
  fi
  sleep "$SLEEP"
done
echo "GIVEUP $(date -u +%H:%M:%S) akun=$( [ -s accounts.txt ] && wc -l < accounts.txt || echo 0 )"
echo "GIVEUP $(date -u +%H:%M:%S)" >> data/auto.log
exit 1
