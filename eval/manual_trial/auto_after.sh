#!/usr/bin/env bash
# Detached auto-resume for the AtlasKB manual-trial eval.
# Waits for the OpenRouter free-tier daily cap to reset, then runs the AFTER pass
# with reduced LLM fan-out (fits the 50/day budget), flushes cache, and writes
# results/after.json + AFTER_COMPARISON.md. Runs independently of any Claude
# session (launch with: nohup bash auto_after.sh >log 2>&1 & disown).
set -u
cd /Users/joeltharakan/Documents/Atlaskb || exit 1
LOG=eval/manual_trial/results/auto_after.log
mkdir -p eval/manual_trial/results
echo "[auto_after] started $(date -u)" >>"$LOG"

RESET=1786233600          # X-RateLimit-Reset (epoch seconds), 2026-08-09 00:00 UTC
TARGET=$((RESET + 180))   # small buffer

while [ "$(date +%s)" -lt "$TARGET" ]; do sleep 300; done
echo "[auto_after] cap window reached $(date -u)" >>"$LOG"

# Confirm the cap actually cleared before spending the window (retry up to ~30 min).
KEY=$(grep '^OPENROUTER_API_KEY=' .env | cut -d= -f2-)
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d '{"model":"nvidia/nemotron-nano-9b-v2:free","messages":[{"role":"user","content":"ok"}],"max_tokens":3}')
  echo "[auto_after] probe $i -> HTTP $code" >>"$LOG"
  [ "$code" = "200" ] && break
  sleep 60
done

# Restart API with reduced fan-out so the whole suite fits under 50 free calls.
pkill -f "uvicorn app.main:app"; sleep 3
AGENT_MAX_ITERATIONS=1 nohup uv run --package atlaskb-api uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 >>"$LOG" 2>&1 &
sleep 10
curl -s http://localhost:8000/health >>"$LOG"; echo >>"$LOG"

# Fresh cache so results reflect current ACLs/code.
docker exec atlaskb-redis-1 sh -c "redis-cli --scan --pattern 'atlaskb:cache:*' | xargs -r redis-cli del" >>"$LOG" 2>&1

# Run the AFTER pass and build the comparison.
.venv/bin/python eval/manual_trial/harness.py --phase after >>"$LOG" 2>&1
.venv/bin/python eval/manual_trial/compare.py >>"$LOG" 2>&1

# Restore API to default settings (re-query enabled).
pkill -f "uvicorn app.main:app"; sleep 3
nohup uv run --package atlaskb-api uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 >>"$LOG" 2>&1 &
sleep 8
curl -s http://localhost:8000/health >>"$LOG"; echo >>"$LOG"

echo "[auto_after] done $(date -u)" >>"$LOG"
touch eval/manual_trial/results/after_done.marker
