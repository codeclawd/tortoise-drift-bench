#!/usr/bin/env bash
# run_experiment.sh — the frozen experiment runner for autoresearch-loop.
#
# Faithful generalization of Karpathy's `uv run train.py > run.log 2>&1`:
#   - runs the configured FROZEN BENCHMARK command once,
#   - enforces a hard timeout (macOS has no `timeout`, so we implement one),
#   - scrapes the scalar `metric:` (and optional `mem_mb:` / `correct:`) the benchmark prints,
#   - emits a normalized summary block the agent greps.
#
# It does NOT know anything about the target's domain. The benchmark itself is the
# ground truth and lives in the target repo. Configure via autoresearch.config (sourced below).
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${AUTORESEARCH_CONFIG:-$HERE/autoresearch.config}"

# ---- config (overridable via env or autoresearch.config) -------------------
BENCH_CMD=""          # REQUIRED: shell command that runs the frozen benchmark and prints "metric: <n>"
METRIC_KEY="metric"   # line prefix to scrape for the scalar to minimize
MEM_KEY="mem_mb"      # optional line prefix for peak memory
CORRECT_KEY="correct" # optional line prefix; must equal "true" or the run is a crash
TIMEOUT_SEC="600"     # hard kill after this many seconds (Karpathy's 10-min rule)
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && . "$CONFIG"

if [ -z "$BENCH_CMD" ]; then
  echo "ERROR: BENCH_CMD is not set. Create $CONFIG (see autoresearch.config.example)." >&2
  echo "---"; echo "${METRIC_KEY}:        0.000000"; echo "${CORRECT_KEY}:       false"
  exit 2
fi

# ---- portable timeout: run BENCH_CMD in bg into its OWN log, kill after TIMEOUT_SEC
# Self-contained: we capture the benchmark to $BENCH_LOG, scrape THAT, then echo it
# through. This does not depend on the agent's outer `> run.log` redirect (which is
# still being written when we'd otherwise grep it — a race we deliberately avoid).
BENCH_LOG="$(mktemp -t autoresearch.XXXXXX)"
trap 'rm -f "$BENCH_LOG"' EXIT
_start=$(date +%s)
bash -c "$BENCH_CMD" > "$BENCH_LOG" 2>&1 &
_cmd_pid=$!
( sleep "$TIMEOUT_SEC"; kill -9 "$_cmd_pid" 2>/dev/null ) &
_watch_pid=$!
wait "$_cmd_pid" 2>/dev/null
_rc=$?
kill -9 "$_watch_pid" 2>/dev/null
wait "$_watch_pid" 2>/dev/null
_end=$(date +%s)
_elapsed=$(( _end - _start ))

# Echo the benchmark's raw output through so it lands in the agent's run.log too.
cat "$BENCH_LOG"

# ---- scrape the benchmark's own output -------------------------------------
_metric="$(grep -E "^${METRIC_KEY}:" "$BENCH_LOG" 2>/dev/null | tail -n1 | awk '{print $2}')"
_mem="$(grep -E "^${MEM_KEY}:" "$BENCH_LOG" 2>/dev/null | tail -n1 | awk '{print $2}')"
_correct="$(grep -E "^${CORRECT_KEY}:" "$BENCH_LOG" 2>/dev/null | tail -n1 | awk '{print $2}')"

# ---- decide crash vs ok ----------------------------------------------------
_status="ok"
if [ "$_rc" -eq 137 ]; then _status="timeout"; fi
if [ -z "$_metric" ]; then _status="crash"; fi
if [ -n "$_correct" ] && [ "$_correct" != "true" ]; then _status="incorrect"; fi

# ---- normalized summary block (this is what the agent greps) ---------------
echo "---"
if [ "$_status" = "ok" ]; then
  echo "${METRIC_KEY}:        ${_metric}"
  echo "${MEM_KEY}:        ${_mem:-0.0}"
  echo "${CORRECT_KEY}:       ${_correct:-true}"
else
  # On any failure, emit a sentinel so the agent's grep sees a non-improving result.
  echo "run_status:    ${_status}"
  echo "${METRIC_KEY}:        0.000000   # FAILED (${_status}) — treat as discard/crash"
  echo "${CORRECT_KEY}:       false"
fi
echo "bench_seconds: ${_elapsed}"
echo "exit_code:     ${_rc}"
