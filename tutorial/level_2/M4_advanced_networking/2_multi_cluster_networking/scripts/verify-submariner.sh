#!/usr/bin/env bash
# verify-submariner.sh — Verify Submariner connectivity between clusters
#
# Usage:
#   ./scripts/verify-submariner.sh
#
# This script checks the health of a Submariner deployment by verifying:
#   1. Gateway node readiness
#   2. Tunnel connections between clusters
#   3. Globalnet status (if enabled)
#   4. Lighthouse (service discovery) readiness
#   5. Cross-cluster DNS resolution

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "      $1"; }

echo "============================================"
echo "  Submariner Health Check"
echo "============================================"
echo ""

# 1. Check Submariner gateway pods
echo "--- Gateway Status ---"
GATEWAY_PODS=$(oc get pods -n submariner-operator -l app=submariner-gateway --no-headers 2>/dev/null || true)
if [ -n "$GATEWAY_PODS" ]; then
  RUNNING=$(echo "$GATEWAY_PODS" | grep -c "Running" || true)
  TOTAL=$(echo "$GATEWAY_PODS" | wc -l | tr -d ' ')
  if [ "$RUNNING" -eq "$TOTAL" ]; then
    pass "Gateway pods: $RUNNING/$TOTAL running"
  else
    fail "Gateway pods: $RUNNING/$TOTAL running"
  fi
else
  fail "No gateway pods found in submariner-operator namespace"
  info "Is Submariner installed? Check: oc get pods -n submariner-operator"
fi
echo ""

# 2. Check Submariner route agent
echo "--- Route Agent Status ---"
ROUTEAGENT_PODS=$(oc get pods -n submariner-operator -l app=submariner-routeagent --no-headers 2>/dev/null || true)
if [ -n "$ROUTEAGENT_PODS" ]; then
  RUNNING=$(echo "$ROUTEAGENT_PODS" | grep -c "Running" || true)
  TOTAL=$(echo "$ROUTEAGENT_PODS" | wc -l | tr -d ' ')
  if [ "$RUNNING" -eq "$TOTAL" ]; then
    pass "Route agent pods: $RUNNING/$TOTAL running"
  else
    fail "Route agent pods: $RUNNING/$TOTAL running"
  fi
else
  fail "No route agent pods found"
fi
echo ""

# 3. Check Lighthouse agent (service discovery)
echo "--- Lighthouse (Service Discovery) Status ---"
LIGHTHOUSE_AGENT=$(oc get pods -n submariner-operator -l app=submariner-lighthouse-agent --no-headers 2>/dev/null || true)
if [ -n "$LIGHTHOUSE_AGENT" ]; then
  RUNNING=$(echo "$LIGHTHOUSE_AGENT" | grep -c "Running" || true)
  if [ "$RUNNING" -gt 0 ]; then
    pass "Lighthouse agent running"
  else
    fail "Lighthouse agent not running"
  fi
else
  fail "No lighthouse agent pod found"
fi

LIGHTHOUSE_DNS=$(oc get pods -n submariner-operator -l app=submariner-lighthouse-coredns --no-headers 2>/dev/null || true)
if [ -n "$LIGHTHOUSE_DNS" ]; then
  RUNNING=$(echo "$LIGHTHOUSE_DNS" | grep -c "Running" || true)
  if [ "$RUNNING" -gt 0 ]; then
    pass "Lighthouse CoreDNS running"
  else
    fail "Lighthouse CoreDNS not running"
  fi
else
  fail "No lighthouse CoreDNS pod found"
fi
echo ""

# 4. Check gateway connections
echo "--- Cluster Connections ---"
GATEWAYS=$(oc get gateways.submariner.io -n submariner-operator -o json 2>/dev/null || echo '{"items":[]}')
CONNECTION_COUNT=$(echo "$GATEWAYS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
count = 0
for gw in data.get('items', []):
    for conn in gw.get('status', {}).get('connections', []):
        status = conn.get('status', 'unknown')
        endpoint = conn.get('endpoint', {}).get('cluster_id', 'unknown')
        print(f'  Cluster: {endpoint}, Status: {status}')
        if status == 'connected':
            count += 1
print(f'TOTAL_CONNECTED={count}')
" 2>/dev/null || echo "TOTAL_CONNECTED=0")

CONNECTED=$(echo "$CONNECTION_COUNT" | grep "TOTAL_CONNECTED" | cut -d= -f2)
if [ "${CONNECTED:-0}" -gt 0 ]; then
  pass "Connected to $CONNECTED remote cluster(s)"
else
  warn "No active connections found (expected if running on a single cluster)"
fi
echo ""

# 5. Check ServiceExports
echo "--- ServiceExport Status ---"
EXPORTS=$(oc get serviceexports.multicluster.x-k8s.io --all-namespaces --no-headers 2>/dev/null || true)
if [ -n "$EXPORTS" ]; then
  EXPORT_COUNT=$(echo "$EXPORTS" | wc -l | tr -d ' ')
  pass "Found $EXPORT_COUNT ServiceExport(s):"
  echo "$EXPORTS" | while read -r line; do
    info "  $line"
  done
else
  warn "No ServiceExports found (create one to enable cross-cluster service discovery)"
fi
echo ""

# 6. Check cross-cluster DNS
echo "--- Cross-Cluster DNS Test ---"
if oc get serviceexports.multicluster.x-k8s.io demo-server -n cross-cluster-demo &>/dev/null; then
  DNS_NAME="demo-server.cross-cluster-demo.svc.clusterset.local"
  info "Testing resolution of: $DNS_NAME"
  CLIENT_POD=$(oc get pods -n cross-cluster-demo -l app=demo-client -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  if [ -n "$CLIENT_POD" ]; then
    RESULT=$(oc exec -n cross-cluster-demo "$CLIENT_POD" -- nslookup "$DNS_NAME" 2>/dev/null || true)
    if echo "$RESULT" | grep -q "Address"; then
      pass "DNS resolution successful for $DNS_NAME"
    else
      warn "DNS resolution failed (may need time to propagate)"
    fi
  else
    warn "No demo-client pod found to test DNS resolution"
  fi
else
  info "Skipping DNS test (demo-server ServiceExport not found)"
fi
echo ""

# 7. Check Globalnet (if enabled)
echo "--- Globalnet Status ---"
GLOBALNET=$(oc get pods -n submariner-operator -l app=submariner-globalnet --no-headers 2>/dev/null || true)
if [ -n "$GLOBALNET" ]; then
  RUNNING=$(echo "$GLOBALNET" | grep -c "Running" || true)
  if [ "$RUNNING" -gt 0 ]; then
    pass "Globalnet enabled and running"
    CLUSTER_GLOBAL_CIDR=$(oc get clusters.submariner.io -n submariner-operator -o jsonpath='{.items[0].spec.global_cidr}' 2>/dev/null || echo "unknown")
    info "  Cluster Global CIDR: $CLUSTER_GLOBAL_CIDR"
  else
    fail "Globalnet pods not running"
  fi
else
  info "Globalnet is not enabled (clusters must have non-overlapping CIDRs)"
fi

echo ""
echo "============================================"
echo "  Health check complete"
echo "============================================"
