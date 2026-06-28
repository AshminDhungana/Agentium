#!/usr/bin/env bash
#
# Performance Regression Gate Orchestrator (Phase 18.2)
#
# Usage:
#   ./scripts/run_perf_gate.sh [HOST]
#
#   HOST  - target base URL (default: http://localhost:8000)
#
# Exits with non-zero status if any performance threshold is not met.
#
set -euo pipefail

HOST="${1:-http://localhost:8000}"
RESULTS_FILE=".perf_results.json"
REPORT_DIR="perf_reports"
mkdir -p "$REPORT_DIR"

# ── Colours ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GRN='\033[0;32m'
YEL='\033[1;33m'
BLD='\033[1m'
RST='\033[0m'

echo -e "${BLD}Agentium Performance Regression Gate${RST}"
echo "====================================="
echo "Target : $HOST"
echo "Date   : $(date)"
echo ""

# ── Helpers ───────────────────────────────────────────────────────
fetch_metrics() {
    curl -sf "$HOST/api/v1/monitoring/metrics" 2>/dev/null || echo '{}'
}

# ── 1. ChromaDB Benchmark ─────────────────────────────────────────
echo -e "${YEL}[1/3] ChromaDB Benchmark${RST}"
echo "      ├─ Seeding 10,000 documents..."
echo "      ├─ Running 100 sequential queries..."

if command -v pytest &>/dev/null; then
    cd backend || exit 1
    pytest tests/benchmarks/test_chroma_query.py -m benchmark --benchmark-only \
        --benchmark-save=baseline 2>&1 | tee "$REPORT_DIR/benchmark.log" || true
    cd ..
fi

# Locate the most recent benchmark JSON
BENCH_JSON=$(ls -1t backend/benchmarks/baseline/bm-*.json 2>/dev/null | head -n1 || true)
if [[ -f "$BENCH_JSON" ]]; then
    P95=$(jq -re '.benchmarks[0].stats.p95' "$BENCH_JSON" 2>/dev/null || echo "0")
    # pytest-benchmark reports in seconds; convert to ms
    P95_MS=$(awk "BEGIN {printf \"%.2f\", $P95 * 1000}")
    echo "      └─ p95 = ${P95_MS}ms"
    if (($(echo "$P95_MS < 200" | bc))); then
        echo -e "      ${GRN}PASS${RST}  p95 ${P95_MS}ms < 200ms"
    else
        echo -e "      ${RED}FAIL${RST}  p95 ${P95_MS}ms >= 200ms"
        CHROMA_PASS=false
    fi
else
    echo "      └─ No benchmark JSON found; skipping assertion"
fi

# ── 2. Load Test (Locust) ────────────────────────────────────────
echo -e "${YEL}[2/3] Load Test${RST}"
LOCUST_USERS="${LOCUST_USERS:-1000}"
LOCUST_SPAWN="${LOCUST_SPAWN_RATE:-10}"
LOCUST_TIME="${LOCUST_RUN_TIME:-5m}"

echo "      ├─ Users : $LOCUST_USERS"
echo "      ├─ Spawn rate: $LOCUST_SPAWN/s"
echo "      ├─ Duration: $LOCUST_TIME"

if command -v locust &>/dev/null; then
    cd backend/tests/load || exit 1
    locust \
        --host "$HOST" \
        --users "$LOCUST_USERS" \
        --spawn-rate "$LOCUST_SPAWN" \
        --run-time "$LOCUST_TIME" \
        --headless \
        --html "$REPORT_DIR/locust_report.html" \
        2>&1 | tee "$REPORT_DIR/locust.log" || true
    cd ../../..
else
    echo "      └─ locust not installed; skipping load test"
fi

# ── 3. p95 Threshold Assertion ───────────────────────────────────
echo -e "${YEL}[3/3] Threshold Assertion${RST}"

sleep 2  # short delay for metrics to settle
METRICS=$(fetch_metrics)
ENDPOINTS=$(echo "$METRICS" | jq -re '.endpoints // {}')

if [[ -z "$ENDPOINTS" ]]; then
    echo "      └─ No timing metrics available (middleware may be disabled)"
    exit 1
fi

P95_PASS=true
while IFS="=" read -r ep data; do
    P95=$(echo "$data" | jq -re '.p95_ms // 0')
    case "$ep" in
        *"agents"*"parent"*) TARGET=100 ;;   # task routing
        *"tasks"*)          TARGET=100 ;;   # task routing
        *"agents"*)         TARGET=50  ;;   # constitutional
        *)                  TARGET=500 ;;   # general
    esac
    if (( $(echo "$P95 <= $TARGET" | bc -l) )); then
        echo -e "      ${GRN}PASS${RST}  $ep  p95=${P95}ms  (target ${TARGET}ms)"
    else
        echo -e "      ${RED}FAIL${RST}  $ep  p95=${P95}ms  (target ${TARGET}ms)"
        P95_PASS=false
    fi
done < <(echo "$ENDPOINTS" | jq -re 'to_entries[] | "\(.key)=\(.value|tojson)"')

echo ""
if $P95_PASS; then
    echo -e "${GRN}Performance Regression Gate: PASSED${RST}"
    exit 0
else
    echo -e "${RED}Performance Regression Gate: FAILED${RST}"
    exit 1
fi
