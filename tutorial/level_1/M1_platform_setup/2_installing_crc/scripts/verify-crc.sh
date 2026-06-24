#!/usr/bin/env bash
# verify-crc.sh — Verify that OpenShift Local (CRC) is installed and working correctly
# Usage: bash scripts/verify-crc.sh
#
# This script checks:
#   1. CRC is installed and on PATH
#   2. CRC VM is running
#   3. oc CLI is available
#   4. Can authenticate as developer
#   5. Can query the API server
#   6. Web Console route is accessible
#   7. Can create and delete a test project

set -euo pipefail

PASS=0
FAIL=0
API_URL="https://api.crc.testing:6443"

pass() {
  echo "  PASS: $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "  FAIL: $1"
  FAIL=$((FAIL + 1))
}

echo "========================================"
echo "  OpenShift Local (CRC) Verification"
echo "========================================"
echo ""

# --- Check 1: CRC binary ---
echo "[1/7] Checking CRC is installed..."
if command -v crc &>/dev/null; then
  CRC_VERSION=$(crc version 2>/dev/null | head -1)
  pass "CRC is installed ($CRC_VERSION)"
else
  fail "CRC binary not found on PATH"
fi

# --- Check 2: CRC VM is running ---
echo "[2/7] Checking CRC VM status..."
if crc status 2>/dev/null | grep -q "Running"; then
  pass "CRC VM is running"
else
  fail "CRC VM is not running (run 'crc start')"
fi

# --- Check 3: oc CLI is available ---
echo "[3/7] Checking oc CLI..."
# Source crc oc-env in case it is not in the current shell
eval "$(crc oc-env 2>/dev/null)" 2>/dev/null || true

if command -v oc &>/dev/null; then
  OC_VERSION=$(oc version --client 2>/dev/null | head -1)
  pass "oc CLI is available ($OC_VERSION)"
else
  fail "oc CLI not found (run: eval \$(crc oc-env))"
fi

# --- Check 4: Can log in as developer ---
echo "[4/7] Checking authentication (developer user)..."
if oc login -u developer -p developer "$API_URL" --insecure-skip-tls-verify=true &>/dev/null; then
  WHOAMI=$(oc whoami 2>/dev/null)
  pass "Logged in as '$WHOAMI'"
else
  fail "Cannot log in as developer"
fi

# --- Check 5: Can query the API server ---
echo "[5/7] Checking API server connectivity..."
NODE_COUNT=$(oc get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$NODE_COUNT" -ge 1 ]; then
  NODE_NAME=$(oc get nodes --no-headers 2>/dev/null | awk '{print $1}')
  pass "API server reachable ($NODE_COUNT node(s): $NODE_NAME)"
else
  fail "Cannot reach the API server or no nodes found"
fi

# --- Check 6: Web Console route exists ---
echo "[6/7] Checking Web Console route..."
CONSOLE_URL=$(oc get routes -n openshift-console console -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [ -n "$CONSOLE_URL" ]; then
  pass "Web Console route exists (https://$CONSOLE_URL)"
else
  # Try logging in as kubeadmin to check (developer may not have permission)
  KUBEADMIN_PASS=""
  if [ -f "$HOME/.crc/machines/crc/kubeadmin-password" ]; then
    KUBEADMIN_PASS=$(cat "$HOME/.crc/machines/crc/kubeadmin-password")
  fi
  if [ -n "$KUBEADMIN_PASS" ]; then
    oc login -u kubeadmin -p "$KUBEADMIN_PASS" "$API_URL" --insecure-skip-tls-verify=true &>/dev/null
    CONSOLE_URL=$(oc get routes -n openshift-console console -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
    if [ -n "$CONSOLE_URL" ]; then
      pass "Web Console route exists (https://$CONSOLE_URL)"
    else
      fail "Web Console route not found"
    fi
    # Switch back to developer
    oc login -u developer -p developer "$API_URL" --insecure-skip-tls-verify=true &>/dev/null
  else
    fail "Cannot verify Web Console route (kubeadmin password not found)"
  fi
fi

# --- Check 7: Can create and delete a test project ---
echo "[7/7] Checking project creation..."
oc login -u developer -p developer "$API_URL" --insecure-skip-tls-verify=true &>/dev/null
TEST_PROJECT="crc-verify-test-$$"
if oc new-project "$TEST_PROJECT" &>/dev/null; then
  if oc get project "$TEST_PROJECT" &>/dev/null; then
    oc delete project "$TEST_PROJECT" &>/dev/null
    pass "Can create and delete projects ($TEST_PROJECT)"
  else
    fail "Project created but cannot be found"
  fi
else
  fail "Cannot create a test project"
fi

# --- Summary ---
echo ""
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Some checks failed. Review the output above and consult"
  echo "the Troubleshooting section in the lesson README."
  exit 1
else
  echo ""
  echo "All checks passed. Your CRC installation is working correctly."
  echo "You are ready to proceed to the next lesson."
  exit 0
fi
