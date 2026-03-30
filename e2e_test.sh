#!/usr/bin/env bash
# InvariantFlow — End-to-end smoke test
# Run with: bash e2e_test.sh
# Assumes: docker compose up is running (backend on 8000, frontend on 5173)

set -euo pipefail

API="http://localhost:8000"
PASS=0
FAIL=0
WARN=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; PASS=$((PASS+1)); }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; FAIL=$((FAIL+1)); }
yellow() { printf "\033[33m⚠ %s\033[0m\n" "$1"; WARN=$((WARN+1)); }
header() { printf "\n\033[1m=== %s ===\033[0m\n" "$1"; }

check_status() {
  local label="$1" url="$2" expected="$3" method="${4:-GET}" body="${5:-}"
  if [ "$method" = "POST" ] && [ -n "$body" ]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$url" -H "Content-Type: application/json" -d "$body")
  else
    code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  fi
  if [ "$code" = "$expected" ]; then
    green "$label (HTTP $code)"
  else
    red "$label — expected $expected, got $code"
  fi
}

check_json_field() {
  local label="$1" url="$2" field="$3" method="${4:-GET}" body="${5:-}"
  if [ "$method" = "POST" ] && [ -n "$body" ]; then
    value=$(curl -s -X POST "$url" -H "Content-Type: application/json" -d "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field','__MISSING__'))" 2>/dev/null || echo "__ERROR__")
  else
    value=$(curl -s "$url" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field','__MISSING__'))" 2>/dev/null || echo "__ERROR__")
  fi
  if [ "$value" != "__MISSING__" ] && [ "$value" != "__ERROR__" ]; then
    green "$label — $field=$value"
  else
    red "$label — field '$field' missing or error"
  fi
}

# ============================================================
header "1. Health checks"
# ============================================================

check_status "Backend root" "$API/docs" "200"
check_status "Frontend" "http://localhost:5173" "200"

# ============================================================
header "2. Mock logistics API"
# ============================================================

# Create shipment
SHIP_RESP=$(curl -s -X POST "$API/api/v1/shipments" -H "Content-Type: application/json" \
  -d '{"weight":800,"origin":"BLR","destination":"DEL"}')
SHIP_ID=$(echo "$SHIP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('shipment_id',''))" 2>/dev/null)
if [ -n "$SHIP_ID" ]; then
  green "Create shipment — id=$SHIP_ID"
else
  red "Create shipment — no shipment_id returned"
fi

# Assign vehicle
check_status "Assign vehicle" "$API/api/v1/shipments/$SHIP_ID/assign" "200" "POST" '{"vehicle_id":"VH_001"}'

# Dispatch
check_status "Dispatch" "$API/api/v1/shipments/$SHIP_ID/dispatch" "200" "POST" '{}'

# Intentional bug test: overweight shipment should still dispatch (bug exists)
OVER_RESP=$(curl -s -X POST "$API/api/v1/shipments" -H "Content-Type: application/json" \
  -d '{"weight":1200,"origin":"BLR","destination":"DEL"}')
OVER_ID=$(echo "$OVER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('shipment_id',''))" 2>/dev/null)
curl -s -X POST "$API/api/v1/shipments/$OVER_ID/assign" -H "Content-Type: application/json" \
  -d '{"vehicle_id":"VH_001"}' > /dev/null
DISPATCH_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/v1/shipments/$OVER_ID/dispatch" -H "Content-Type: application/json" -d '{}')
if [ "$DISPATCH_CODE" = "200" ]; then
  green "Intentional bug confirmed — overweight dispatch returns 200 (the swarm should catch this)"
else
  yellow "Overweight dispatch returned $DISPATCH_CODE — bug may have been fixed?"
fi

# ============================================================
header "3. Protocol endpoints"
# ============================================================

check_status "A2A agent card" "$API/.well-known/agent-card.json" "200"
check_json_field "Agent card has name" "$API/.well-known/agent-card.json" "name"
check_status "Agent cards list" "$API/api/v1/agents/cards" "200"
check_status "Agent status" "$API/api/v1/agents/status" "200"

# MCP (may or may not be mounted depending on fastapi-mcp install)
MCP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API/mcp" 2>/dev/null || echo "000")
if [ "$MCP_CODE" = "200" ] || [ "$MCP_CODE" = "405" ]; then
  green "MCP endpoint reachable (HTTP $MCP_CODE)"
else
  yellow "MCP endpoint returned $MCP_CODE — fastapi-mcp may not be installed"
fi

# ============================================================
header "4. Testing — Direct mode"
# ============================================================

DIRECT_RESP=$(curl -s -X POST "$API/api/v1/testing/run" -H "Content-Type: application/json" \
  -d '{"mode":"direct","seed_starter":true,"entity":"Shipment"}')
DIRECT_FAILED=$(echo "$DIRECT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('failed',0))" 2>/dev/null)
DIRECT_PASSED=$(echo "$DIRECT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('passed',0))" 2>/dev/null)
DIRECT_TOTAL=$(echo "$DIRECT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_scenarios',0))" 2>/dev/null)
DIRECT_RUN_ID=$(echo "$DIRECT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null)

if [ -n "$DIRECT_RUN_ID" ]; then
  green "Direct run completed — run_id=$DIRECT_RUN_ID"
else
  red "Direct run — no run_id returned"
fi

if [ "$DIRECT_TOTAL" -gt 0 ] 2>/dev/null; then
  green "Direct mode ran $DIRECT_TOTAL scenarios ($DIRECT_PASSED pass, $DIRECT_FAILED fail)"
else
  red "Direct mode — no scenarios ran"
fi

if [ "$DIRECT_FAILED" -gt 0 ] 2>/dev/null; then
  green "Direct mode caught violations ($DIRECT_FAILED failures) — weight bug detected"
else
  red "Direct mode caught ZERO failures — the weight bug was NOT detected"
fi

# ============================================================
header "5. Testing — Blackboard mode"
# ============================================================

BB_RESP=$(curl -s -X POST "$API/api/v1/testing/run" -H "Content-Type: application/json" \
  -d '{"mode":"blackboard","seed_starter":true,"entity":"Shipment"}')
BB_FAILED=$(echo "$BB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('failed',0))" 2>/dev/null)
BB_TOTAL=$(echo "$BB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_scenarios',0))" 2>/dev/null)
BB_DEAD=$(echo "$BB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dead_tasks',0))" 2>/dev/null)
BB_RUN_ID=$(echo "$BB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null)

if [ -n "$BB_RUN_ID" ]; then
  green "Blackboard run completed — run_id=$BB_RUN_ID"
else
  red "Blackboard run — no run_id"
fi

if [ "$BB_TOTAL" -gt 0 ] 2>/dev/null; then
  green "Blackboard mode ran $BB_TOTAL scenarios ($BB_FAILED failures)"
else
  red "Blackboard mode — no scenarios ran"
fi

if [ "$BB_FAILED" -gt 0 ] 2>/dev/null; then
  green "Blackboard mode caught violations"
else
  red "Blackboard mode caught ZERO failures"
fi

if [ "$BB_DEAD" = "0" ] 2>/dev/null; then
  green "No dead tasks in blackboard run"
else
  yellow "Blackboard run had $BB_DEAD dead tasks — check /api/v1/tasks/dead"
fi

# ============================================================
header "6. Testing — LangGraph mode (critic loop)"
# ============================================================

LG_RESP=$(curl -s -X POST "$API/api/v1/testing/run" -H "Content-Type: application/json" \
  -d '{"mode":"langgraph","seed_starter":true,"entity":"Shipment"}')
LG_FAILED=$(echo "$LG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('failed',0))" 2>/dev/null)
LG_TOTAL=$(echo "$LG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_scenarios',0))" 2>/dev/null)
LG_RUN_ID=$(echo "$LG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null)
LG_FEEDBACK=$(echo "$LG_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('feedback',[])))" 2>/dev/null)

if [ -n "$LG_RUN_ID" ]; then
  green "LangGraph run completed — run_id=$LG_RUN_ID"
else
  red "LangGraph run — no run_id"
fi

if [ "$LG_TOTAL" -gt 0 ] 2>/dev/null; then
  green "LangGraph mode ran $LG_TOTAL scenarios ($LG_FAILED failures)"
else
  red "LangGraph mode — no scenarios ran"
fi

if [ "$LG_FEEDBACK" -gt 0 ] 2>/dev/null; then
  green "Critic produced $LG_FEEDBACK feedback entries"
else
  yellow "Critic produced no feedback — loop may have stopped immediately"
fi

# Cost tracking
LG_COST=$(echo "$LG_RESP" | python3 -c "import sys,json; c=json.load(sys.stdin).get('cost'); print(c.get('run_total_usd',0) if c else 'None')" 2>/dev/null)
if [ "$LG_COST" != "None" ]; then
  green "Cost tracking present — run_total_usd=$LG_COST"
else
  yellow "Cost tracking missing from response"
fi

# ============================================================
header "7. Run history"
# ============================================================

check_status "List runs" "$API/api/v1/testing/runs" "200"
RUNS_COUNT=$(curl -s "$API/api/v1/testing/runs" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null)
if [ "$RUNS_COUNT" -ge 3 ] 2>/dev/null; then
  green "Run history has $RUNS_COUNT runs (expected ≥3 from tests above)"
else
  yellow "Run history has $RUNS_COUNT runs (expected ≥3)"
fi

# ============================================================
header "8. Ingestion pipeline"
# ============================================================

INGEST_RESP=$(curl -s -X POST "$API/api/v1/ingestion/ingest" -H "Content-Type: application/json" \
  -d '{"source":"e2e-test","text":"shipment weight must not exceed vehicle capacity. shipment must be assigned before dispatch."}')
INGEST_TOTAL=$(echo "$INGEST_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_rules',0))" 2>/dev/null)

if [ "$INGEST_TOTAL" -ge 2 ] 2>/dev/null; then
  green "Ingestion extracted $INGEST_TOTAL rules from raw text"
else
  red "Ingestion extracted $INGEST_TOTAL rules (expected ≥2)"
fi

# ============================================================
header "9. Rule approval flow"
# ============================================================

PENDING=$(curl -s "$API/api/v1/rules/pending" | python3 -c "import sys,json; d=json.load(sys.stdin); rules=d.get('rules',[]); print(rules[0].get('rule_id','') if rules else '')" 2>/dev/null)
if [ -n "$PENDING" ]; then
  green "Pending rules found — first: $PENDING"

  # Approve it
  APPROVE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/v1/rules/$PENDING/approve" \
    -H "Content-Type: application/json" -d '{"approved_by":"e2e-test"}')
  if [ "$APPROVE_CODE" = "200" ]; then
    green "Rule $PENDING approved successfully"
  else
    red "Rule approval returned $APPROVE_CODE"
  fi
else
  yellow "No pending rules to test approval flow (ingestion may have failed)"
fi

# ============================================================
header "10. SSE stream check"
# ============================================================

# Connect to SSE for 3 seconds, count events
SSE_EVENTS=$(timeout 5 curl -s -N "$API/api/v1/stream/testing" 2>/dev/null | head -20 | grep -c "^data:" || echo "0")
if [ "$SSE_EVENTS" -gt 0 ] 2>/dev/null; then
  green "SSE stream is active — received $SSE_EVENTS events in 5s"
else
  yellow "SSE stream returned 0 events in 5s (may need an active run to emit)"
fi

# ============================================================
header "11. Dead tasks check"
# ============================================================

DEAD_COUNT=$(curl -s "$API/api/v1/tasks/dead" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null)
if [ "$DEAD_COUNT" = "0" ] 2>/dev/null; then
  green "No dead tasks across all runs"
else
  yellow "$DEAD_COUNT dead tasks found — investigate via /api/v1/tasks/dead"
fi

# ============================================================
header "12. Frontend pages"
# ============================================================

for path in "/" "/rules" "/ingest" "/runs"; do
  FE_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5173$path")
  if [ "$FE_CODE" = "200" ]; then
    green "Frontend $path (HTTP $FE_CODE)"
  else
    red "Frontend $path — HTTP $FE_CODE"
  fi
done

# ============================================================
header "SUMMARY"
# ============================================================

TOTAL=$((PASS + FAIL + WARN))
printf "\n"
printf "\033[32m  Passed: %d\033[0m\n" "$PASS"
printf "\033[31m  Failed: %d\033[0m\n" "$FAIL"
printf "\033[33m  Warnings: %d\033[0m\n" "$WARN"
printf "  Total: %d checks\n\n" "$TOTAL"

if [ "$FAIL" -gt 0 ]; then
  printf "\033[31m❌ %d failures need fixing.\033[0m\n" "$FAIL"
  exit 1
else
  printf "\033[32m✅ All critical checks passed.\033[0m\n"
  exit 0
fi
