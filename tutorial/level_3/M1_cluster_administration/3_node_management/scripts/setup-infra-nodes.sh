#!/bin/bash
# setup-infra-nodes.sh
# Automates the creation of infrastructure nodes and migration of platform workloads.
#
# Usage: ./scripts/setup-infra-nodes.sh
#
# Prerequisites:
# - Logged in as cluster-admin: oc whoami
# - An existing worker MachineSet to use as a template
#
# This script:
# 1. Extracts cluster ID and provider details from an existing MachineSet
# 2. Generates an infra MachineSet customized for your cluster
# 3. Creates the infra MachineConfigPool
# 4. Moves router, registry, and monitoring to infra nodes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"

echo "=== OpenShift Infrastructure Node Setup ==="
echo ""

# Verify cluster-admin access
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run 'oc login' first."
  exit 1
fi

CURRENT_USER=$(oc whoami)
echo "Logged in as: ${CURRENT_USER}"

# Get cluster infrastructure name
CLUSTER_ID=$(oc get -o jsonpath='{.status.infrastructureName}' infrastructure cluster)
echo "Cluster ID: ${CLUSTER_ID}"

# Get the first worker MachineSet as a template
WORKER_MS=$(oc get machinesets -n openshift-machine-api -o jsonpath='{.items[0].metadata.name}')
echo "Template MachineSet: ${WORKER_MS}"

if [ -z "${WORKER_MS}" ]; then
  echo "ERROR: No MachineSets found. Is this an IPI-provisioned cluster?"
  exit 1
fi

# Extract availability zone from the worker MachineSet
ZONE=$(oc get machineset "${WORKER_MS}" -n openshift-machine-api \
  -o jsonpath='{.spec.template.spec.providerSpec.value.placement.availabilityZone}')
echo "Availability Zone: ${ZONE}"

echo ""
echo "--- Step 1: Generate Infra MachineSet ---"

# Generate infra MachineSet from existing worker MachineSet
oc get machineset "${WORKER_MS}" -n openshift-machine-api -o json \
  | jq --arg cluster_id "${CLUSTER_ID}" --arg zone "${ZONE}" '
    .metadata.name = "\($cluster_id)-infra-\($zone)" |
    del(.metadata.uid, .metadata.resourceVersion, .metadata.creationTimestamp, .metadata.generation, .status) |
    .metadata.labels["machine.openshift.io/cluster-api-cluster"] = $cluster_id |
    .spec.replicas = 3 |
    .spec.selector.matchLabels["machine.openshift.io/cluster-api-machineset"] = "\($cluster_id)-infra-\($zone)" |
    .spec.template.metadata.labels["machine.openshift.io/cluster-api-machineset"] = "\($cluster_id)-infra-\($zone)" |
    .spec.template.metadata.labels["machine.openshift.io/cluster-api-machine-role"] = "infra" |
    .spec.template.metadata.labels["machine.openshift.io/cluster-api-machine-type"] = "infra" |
    .spec.template.spec.metadata.labels["node-role.kubernetes.io/infra"] = "" |
    .spec.template.spec.taints = [{"key": "node-role.kubernetes.io/infra", "effect": "NoSchedule"}]
  ' > /tmp/infra-machineset.json

echo "Generated infra MachineSet at /tmp/infra-machineset.json"
echo ""

read -p "Apply the infra MachineSet? (y/N): " -r REPLY
if [[ "${REPLY}" =~ ^[Yy]$ ]]; then
  oc apply -f /tmp/infra-machineset.json
  echo "Infra MachineSet created. Waiting for machines to provision..."

  # Wait for machines to reach Running phase (timeout: 10 minutes)
  TIMEOUT=600
  ELAPSED=0
  while [ ${ELAPSED} -lt ${TIMEOUT} ]; do
    RUNNING=$(oc get machines -n openshift-machine-api \
      -l machine.openshift.io/cluster-api-machine-role=infra \
      -o jsonpath='{range .items[*]}{.status.phase}{"\n"}{end}' | grep -c "Running" || true)
    TOTAL=$(oc get machines -n openshift-machine-api \
      -l machine.openshift.io/cluster-api-machine-role=infra \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | wc -l | tr -d ' ')

    echo "  Infra machines: ${RUNNING}/${TOTAL} Running (${ELAPSED}s elapsed)"

    if [ "${RUNNING}" -eq "${TOTAL}" ] && [ "${TOTAL}" -gt 0 ]; then
      echo "All infra machines are Running."
      break
    fi
    sleep 15
    ELAPSED=$((ELAPSED + 15))
  done

  if [ ${ELAPSED} -ge ${TIMEOUT} ]; then
    echo "WARNING: Timeout waiting for infra machines. Check: oc get machines -n openshift-machine-api"
  fi
else
  echo "Skipped MachineSet creation."
fi

echo ""
echo "--- Step 2: Create Infra MachineConfigPool ---"

read -p "Create the infra MachineConfigPool? (y/N): " -r REPLY
if [[ "${REPLY}" =~ ^[Yy]$ ]]; then
  oc apply -f "${MANIFEST_DIR}/mcp-infra.yaml"
  echo "Infra MCP created."
else
  echo "Skipped MCP creation."
fi

echo ""
echo "--- Step 3: Move Platform Workloads to Infra Nodes ---"

read -p "Move router, registry, and monitoring to infra nodes? (y/N): " -r REPLY
if [[ "${REPLY}" =~ ^[Yy]$ ]]; then
  echo "Moving Ingress Controller..."
  oc apply -f "${MANIFEST_DIR}/ingresscontroller-infra.yaml"

  echo "Moving Image Registry..."
  oc patch configs.imageregistry.operator.openshift.io/cluster --type=merge -p '{
    "spec": {
      "nodeSelector": {"node-role.kubernetes.io/infra": ""},
      "tolerations": [{"key": "node-role.kubernetes.io/infra", "effect": "NoSchedule"}]
    }
  }'

  echo "Moving Monitoring Stack..."
  oc apply -f "${MANIFEST_DIR}/monitoring-infra.yaml"

  echo ""
  echo "Platform workloads are being moved. This may take several minutes."
  echo "Monitor progress with:"
  echo "  oc get pods -n openshift-ingress -o wide"
  echo "  oc get pods -n openshift-image-registry -o wide"
  echo "  oc get pods -n openshift-monitoring -o wide"
else
  echo "Skipped workload migration."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Verify with:"
echo "  oc get nodes -l node-role.kubernetes.io/infra"
echo "  oc get mcp"
echo "  oc get machines -n openshift-machine-api -l machine.openshift.io/cluster-api-machine-role=infra"
