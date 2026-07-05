#!/usr/bin/env bash
set -euo pipefail

# ── Parse flags ──────────────────────────────────────────────────────────────
NAMESPACE=""
while getopts "n:" opt; do
  case $opt in
    n) NAMESPACE="$OPTARG" ;;
    *) echo "Usage: $0 [-n namespace]"; exit 1 ;;
  esac
done

if [[ -z "$NAMESPACE" ]]; then
  NAMESPACE="$(oc project -q)"
fi

# ── Prerequisites ────────────────────────────────────────────────────────────
for cmd in oc curl jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: '$cmd' is required but not found."
    exit 1
  fi
done

# ── Resolve URLs ─────────────────────────────────────────────────────────────
KEYCLOAK_URL="https://$(oc get route keycloak -n "$NAMESPACE" -o jsonpath='{.spec.host}')"
PRODUCTS_URL="https://$(oc get route products-service -n "$NAMESPACE" -o jsonpath='{.spec.host}')"

echo "Keycloak URL:  $KEYCLOAK_URL"
echo "Products URL:  $PRODUCTS_URL"
echo ""

PASS=0
FAIL=0

run_test() {
  local description="$1"
  local expected_code="$2"
  local actual_code="$3"

  if [[ "$actual_code" == "$expected_code" ]]; then
    echo "  PASS: $description (HTTP $actual_code)"
    ((PASS++))
  else
    echo "  FAIL: $description (expected HTTP $expected_code, got HTTP $actual_code)"
    ((FAIL++))
  fi
}

# ── Get alice's token (password grant) ───────────────────────────────────────
echo "==> Obtaining token for alice (editor role)..."
ALICE_RESPONSE=$(curl -sk -X POST \
  "$KEYCLOAK_URL/realms/shopinsights/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=shopinsights-dashboard" \
  -d "username=alice" \
  -d "password=alice123")

ALICE_TOKEN=$(echo "$ALICE_RESPONSE" | jq -r '.access_token')
if [[ "$ALICE_TOKEN" == "null" || -z "$ALICE_TOKEN" ]]; then
  echo "ERROR: Failed to obtain token for alice."
  echo "Response: $ALICE_RESPONSE"
  exit 1
fi
echo "  Token obtained successfully."
echo ""

# ── Test 1: GET /products without token (should be 200) ─────────────────────
echo "==> Test 1: GET /products without token"
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" "$PRODUCTS_URL/products")
run_test "GET /products without token returns 200" "200" "$HTTP_CODE"

# ── Test 2: POST /products without token (should be 401) ────────────────────
echo "==> Test 2: POST /products without token"
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" -X POST \
  "$PRODUCTS_URL/products" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Product", "price": 9.99}')
run_test "POST /products without token returns 401" "401" "$HTTP_CODE"

# ── Test 3: POST /products with alice's token (should be 200 or 201) ────────
echo "==> Test 3: POST /products with alice's token (editor)"
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" -X POST \
  "$PRODUCTS_URL/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -d '{"name": "Test Product", "price": 9.99}')
if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "201" ]]; then
  echo "  PASS: POST /products with alice's token returns success (HTTP $HTTP_CODE)"
  ((PASS++))
else
  echo "  FAIL: POST /products with alice's token (expected HTTP 200 or 201, got HTTP $HTTP_CODE)"
  ((FAIL++))
fi

# ── Get service token for analytics-service (client credentials grant) ──────
echo ""
echo "==> Obtaining service token for analytics-service (client credentials)..."
SERVICE_RESPONSE=$(curl -sk -X POST \
  "$KEYCLOAK_URL/realms/shopinsights/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=analytics-service" \
  -d "client_secret=analytics-service-secret")

SERVICE_TOKEN=$(echo "$SERVICE_RESPONSE" | jq -r '.access_token')
if [[ "$SERVICE_TOKEN" == "null" || -z "$SERVICE_TOKEN" ]]; then
  echo "ERROR: Failed to obtain service token for analytics-service."
  echo "Response: $SERVICE_RESPONSE"
  exit 1
fi
echo "  Service token obtained successfully."
echo ""

# ── Test 4: GET /products with service token ────────────────────────────────
echo "==> Test 4: GET /products with analytics-service token"
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" \
  "$PRODUCTS_URL/products" \
  -H "Authorization: Bearer $SERVICE_TOKEN")
run_test "GET /products with service token returns 200" "200" "$HTTP_CODE"

# ── Test 5: POST /products with service token ───────────────────────────────
echo "==> Test 5: POST /products with analytics-service token"
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" -X POST \
  "$PRODUCTS_URL/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  -d '{"name": "Analytics Product", "price": 19.99}')
if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "201" ]]; then
  echo "  PASS: POST /products with service token returns success (HTTP $HTTP_CODE)"
  ((PASS++))
else
  echo "  FAIL: POST /products with service token (expected HTTP 200 or 201, got HTTP $HTTP_CODE)"
  ((FAIL++))
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
