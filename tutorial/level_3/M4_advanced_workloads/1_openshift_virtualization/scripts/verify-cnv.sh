#!/bin/bash
# verify-cnv.sh — Verify that OpenShift Virtualization is healthy
# Usage: ./scripts/verify-cnv.sh

set -euo pipefail

echo "=== OpenShift Virtualization Health Check ==="
echo ""

ERRORS=0

# Check HyperConverged CR status
echo "[1/6] HyperConverged CR status:"
HC_STATUS=$(oc get hyperconverged kubevirt-hyperconverged -n openshift-cnv -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || echo "NotFound")
if [ "$HC_STATUS" = "True" ]; then
  echo "  OK: HyperConverged is Available"
else
  echo "  FAIL: HyperConverged status = ${HC_STATUS}"
  ERRORS=$((ERRORS + 1))
fi

# Check KubeVirt CR
echo ""
echo "[2/6] KubeVirt CR status:"
KV_STATUS=$(oc get kubevirt kubevirt-kubevirt-hyperconverged -n openshift-cnv -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
if [ "$KV_STATUS" = "Deployed" ]; then
  echo "  OK: KubeVirt phase = Deployed"
else
  echo "  FAIL: KubeVirt phase = ${KV_STATUS}"
  ERRORS=$((ERRORS + 1))
fi

# Check CDI (Containerized Data Importer)
echo ""
echo "[3/6] CDI status:"
CDI_STATUS=$(oc get cdi cdi-kubevirt-hyperconverged -n openshift-cnv -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
if [ "$CDI_STATUS" = "Deployed" ]; then
  echo "  OK: CDI phase = Deployed"
else
  echo "  FAIL: CDI phase = ${CDI_STATUS}"
  ERRORS=$((ERRORS + 1))
fi

# Check virt-operator pods
echo ""
echo "[4/6] Operator pods:"
oc get pods -n openshift-cnv -l kubevirt.io=virt-operator --no-headers 2>/dev/null | while read -r line; do
  echo "  $line"
done
VIRT_OP_READY=$(oc get pods -n openshift-cnv -l kubevirt.io=virt-operator -o jsonpath='{.items[*].status.phase}' 2>/dev/null | tr ' ' '\n' | grep -c "Running" || echo 0)
if [ "$VIRT_OP_READY" -ge 1 ]; then
  echo "  OK: virt-operator pods running"
else
  echo "  FAIL: No virt-operator pods running"
  ERRORS=$((ERRORS + 1))
fi

# Check virt-handler DaemonSet (one per node)
echo ""
echo "[5/6] virt-handler DaemonSet (per-node agent):"
oc get ds -n openshift-cnv -l kubevirt.io=virt-handler --no-headers 2>/dev/null | while read -r line; do
  echo "  $line"
done

# Check KVM device availability
echo ""
echo "[6/6] KVM device availability per node:"
oc get nodes -o jsonpath='{range .items[*]}  {.metadata.name}: kvm={.status.allocatable.devices\.kubevirt\.io/kvm}{"\n"}{end}' 2>/dev/null || echo "  Unable to query (operator may still be initializing)"

echo ""
if [ $ERRORS -eq 0 ]; then
  echo "=== All checks passed ==="
else
  echo "=== ${ERRORS} check(s) failed — review output above ==="
  exit 1
fi
