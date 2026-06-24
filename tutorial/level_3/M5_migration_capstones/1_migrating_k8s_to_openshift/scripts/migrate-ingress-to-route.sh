#!/usr/bin/env bash
#
# migrate-ingress-to-route.sh
# Converts Kubernetes Ingress resources to OpenShift Routes.
# Generates Route YAML files for each Ingress rule found.
#
# Usage: ./migrate-ingress-to-route.sh <namespace> [output-dir]
#

set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace> [output-dir]}"
OUTPUT_DIR="${2:-./generated-routes}"

mkdir -p "$OUTPUT_DIR"

echo "Converting Ingress resources in namespace '${NAMESPACE}' to Routes..."
echo "Output directory: ${OUTPUT_DIR}"
echo ""

INGRESS_LIST=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

if [ -z "$INGRESS_LIST" ]; then
  echo "No Ingress resources found in namespace '${NAMESPACE}'."
  exit 0
fi

CONVERTED=0

for INGRESS_NAME in $INGRESS_LIST; do
  echo "Processing Ingress: ${INGRESS_NAME}"

  # Get the number of rules
  RULE_COUNT=$(kubectl get ingress "$INGRESS_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.rules}' 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

  if [ "$RULE_COUNT" -eq 0 ]; then
    echo "  [SKIP] No rules found in Ingress '${INGRESS_NAME}'"
    continue
  fi

  for i in $(seq 0 $((RULE_COUNT - 1))); do
    HOST=$(kubectl get ingress "$INGRESS_NAME" -n "$NAMESPACE" -o jsonpath="{.spec.rules[$i].host}" 2>/dev/null || echo "")
    SVC_NAME=$(kubectl get ingress "$INGRESS_NAME" -n "$NAMESPACE" -o jsonpath="{.spec.rules[$i].http.paths[0].backend.service.name}" 2>/dev/null || echo "")
    SVC_PORT=$(kubectl get ingress "$INGRESS_NAME" -n "$NAMESPACE" -o jsonpath="{.spec.rules[$i].http.paths[0].backend.service.port.number}" 2>/dev/null || echo "")

    if [ -z "$SVC_NAME" ]; then
      echo "  [SKIP] Rule $i has no backend service"
      continue
    fi

    ROUTE_NAME="${INGRESS_NAME}"
    if [ "$RULE_COUNT" -gt 1 ]; then
      ROUTE_NAME="${INGRESS_NAME}-${i}"
    fi

    ROUTE_FILE="${OUTPUT_DIR}/${ROUTE_NAME}-route.yaml"

    # Check if TLS is configured on the Ingress
    HAS_TLS=$(kubectl get ingress "$INGRESS_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.tls}' 2>/dev/null || echo "")

    TLS_SECTION=""
    if [ -n "$HAS_TLS" ] && [ "$HAS_TLS" != "null" ]; then
      TLS_SECTION="  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect"
    fi

    cat > "$ROUTE_FILE" <<YAML
# Auto-generated Route from Ingress '${INGRESS_NAME}' (rule ${i})
# Review and adjust before applying to OpenShift
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: ${ROUTE_NAME}
  labels:
    app: ${SVC_NAME}
    tutorial-level: "3"
    tutorial-module: "M5"
    migrated-from: ingress
spec:
  host: ${HOST}
  to:
    kind: Service
    name: ${SVC_NAME}
    weight: 100
  port:
    targetPort: ${SVC_PORT}
${TLS_SECTION}
  wildcardPolicy: None
YAML

    echo "  [OK] Generated: ${ROUTE_FILE}"
    CONVERTED=$((CONVERTED + 1))
  done
done

echo ""
echo "Conversion complete: ${CONVERTED} Route(s) generated in ${OUTPUT_DIR}/"
echo ""
echo "Next steps:"
echo "  1. Review each generated Route YAML"
echo "  2. Update hostnames to match your OpenShift cluster domain"
echo "  3. Apply: oc apply -f ${OUTPUT_DIR}/"
