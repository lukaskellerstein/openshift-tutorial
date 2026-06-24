#!/bin/bash
# setup-cnv-operator.sh — Install the OpenShift Virtualization (CNV) operator
# Requires cluster-admin privileges
# Usage: ./scripts/setup-cnv-operator.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"

echo "=== OpenShift Virtualization (CNV) Operator Installation ==="
echo ""

# Verify cluster-admin access
echo "[1/6] Verifying cluster-admin access..."
if ! oc auth can-i create subscription -n openshift-cnv 2>/dev/null; then
  echo "ERROR: cluster-admin access required. Log in as kubeadmin:"
  echo "  oc login -u kubeadmin -p <password> https://api.crc.testing:6443"
  exit 1
fi
echo "  OK: cluster-admin access confirmed."

# Check hardware virtualization support
echo ""
echo "[2/6] Checking hardware virtualization support..."
VIRT_NODES=$(oc get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.devices\.kubevirt\.io/kvm}{"\n"}{end}' 2>/dev/null || true)
if [ -z "$VIRT_NODES" ]; then
  echo "  WARNING: Cannot detect KVM support yet (operator not installed)."
  echo "  Hardware virtualization (VT-x/AMD-V) must be enabled in BIOS."
  echo "  On CRC, nested virtualization must be supported by the host."
else
  echo "  KVM-capable nodes:"
  echo "$VIRT_NODES" | sed 's/^/    /'
fi

# Create the openshift-cnv namespace
echo ""
echo "[3/6] Creating openshift-cnv namespace..."
oc create namespace openshift-cnv --dry-run=client -o yaml | oc apply -f -

# Apply OperatorGroup
echo ""
echo "[4/6] Applying OperatorGroup..."
oc apply -f "${MANIFEST_DIR}/cnv-operator-group.yaml"

# Apply Subscription
echo ""
echo "[5/6] Applying Subscription (manual approval)..."
oc apply -f "${MANIFEST_DIR}/cnv-subscription.yaml"

# Wait for InstallPlan and approve it
echo ""
echo "[6/6] Waiting for InstallPlan..."
echo "  This may take 1-3 minutes while the operator catalog is queried."

TIMEOUT=180
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  INSTALL_PLAN=$(oc get installplan -n openshift-cnv -o jsonpath='{.items[?(@.spec.approved==false)].metadata.name}' 2>/dev/null || true)
  if [ -n "$INSTALL_PLAN" ]; then
    echo "  Found InstallPlan: ${INSTALL_PLAN}"
    echo "  Approving..."
    oc patch installplan "${INSTALL_PLAN}" -n openshift-cnv --type merge -p '{"spec":{"approved":true}}'
    echo "  InstallPlan approved."
    break
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
  echo "  Waiting... (${ELAPSED}s / ${TIMEOUT}s)"
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo "  WARNING: Timed out waiting for InstallPlan."
  echo "  Check manually: oc get installplan -n openshift-cnv"
  exit 1
fi

# Wait for CSV to succeed
echo ""
echo "  Waiting for operator to install (this may take 3-5 minutes)..."
oc wait csv -n openshift-cnv -l operators.coreos.com/kubevirt-hyperconverged.openshift-cnv \
  --for=jsonpath='{.status.phase}'=Succeeded --timeout=300s 2>/dev/null || {
  echo "  Waiting for CSV to appear..."
  sleep 30
  CSV_NAME=$(oc get csv -n openshift-cnv -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  if [ -n "$CSV_NAME" ]; then
    oc wait csv "${CSV_NAME}" -n openshift-cnv --for=jsonpath='{.status.phase}'=Succeeded --timeout=300s
  else
    echo "  WARNING: CSV not found. Check: oc get csv -n openshift-cnv"
  fi
}

echo ""
echo "=== Operator installed successfully ==="
echo ""
echo "Next step: Apply the HyperConverged CR to activate KubeVirt components:"
echo "  oc apply -f ${MANIFEST_DIR}/hyperconverged.yaml"
echo ""
