#!/bin/bash
# Complete teardown of the AI Platform capstone deployment.
# Removes all resources in reverse dependency order to avoid
# orphaned resources and hanging finalizers.
#
# Usage: ./teardown.sh [--namespace ai-platform-prod] [--confirm]

set -euo pipefail

# ---------------------------------------------------------------------------
# Color codes
# ---------------------------------------------------------------------------
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
NAMESPACE="${NAMESPACE:-ai-platform-prod}"
CONFIRM=false
ARGOCD_APP="${ARGOCD_APP:-ai-platform-prod}"
ARGOCD_NS="${ARGOCD_NS:-openshift-gitops}"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --namespace=*)
      NAMESPACE="${1#*=}"
      shift
      ;;
    --confirm)
      CONFIRM=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [--namespace ai-platform-prod] [--confirm]"
      echo ""
      echo "Options:"
      echo "  --namespace   Target namespace (default: ai-platform-prod)"
      echo "  --confirm     Skip interactive confirmation prompt"
      echo "  --help        Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helper: print a step header
# ---------------------------------------------------------------------------
step_count=0
step() {
  step_count=$((step_count + 1))
  echo ""
  echo -e "${YELLOW}[Step ${step_count}]${NC} $1"
}

# ---------------------------------------------------------------------------
# Helper: delete resources with standard flags
# Uses --ignore-not-found so the script is idempotent.
# Uses --wait=false for resources that may have finalizers.
# ---------------------------------------------------------------------------
delete_resource() {
  local resource_type="$1"
  local resource_name="$2"
  local extra_flags="${3:-}"

  echo -e "  Deleting ${resource_type}/${resource_name}..."
  # shellcheck disable=SC2086
  oc delete "${resource_type}" "${resource_name}" \
    -n "${NAMESPACE}" \
    --ignore-not-found \
    --wait=false \
    ${extra_flags} 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Helper: delete resources by label selector
# ---------------------------------------------------------------------------
delete_by_label() {
  local resource_type="$1"
  local label_selector="$2"
  local extra_flags="${3:-}"

  echo -e "  Deleting ${resource_type} with label ${label_selector}..."
  # shellcheck disable=SC2086
  oc delete "${resource_type}" \
    -n "${NAMESPACE}" \
    -l "${label_selector}" \
    --ignore-not-found \
    --wait=false \
    ${extra_flags} 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Confirmation prompt
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  AI Platform Capstone Teardown"
echo "============================================"
echo "  Namespace: ${NAMESPACE}"
echo "  ArgoCD:    ${ARGOCD_APP} (in ${ARGOCD_NS})"
echo "============================================"
echo ""
echo -e "${RED}WARNING: This will permanently delete ALL resources in '${NAMESPACE}'${NC}"
echo -e "${RED}         and the namespace itself.${NC}"
echo ""

if [[ "${CONFIRM}" != "true" ]]; then
  read -r -p "Are you sure you want to proceed? (yes/no): " answer
  if [[ "${answer}" != "yes" ]]; then
    echo "Teardown cancelled."
    exit 0
  fi
fi

echo ""
echo -e "${GREEN}Starting teardown...${NC}"

# ===========================
# Step 1: ArgoCD Application
# ===========================
# Delete ArgoCD Application FIRST to stop auto-reconciliation.
# If ArgoCD is running and the Application has selfHeal enabled,
# it would recreate resources we delete in subsequent steps.
step "Removing ArgoCD Application (stops auto-reconciliation)"

# Remove the finalizer first to prevent cascading delete from blocking.
# The cascade finalizer would try to delete all managed resources, but
# we want to do that ourselves in a controlled order.
oc patch application "${ARGOCD_APP}" -n "${ARGOCD_NS}" \
  --type=json \
  -p='[{"op": "remove", "path": "/metadata/finalizers"}]' \
  2>/dev/null || true

oc delete application "${ARGOCD_APP}" \
  -n "${ARGOCD_NS}" \
  --ignore-not-found \
  --wait=false \
  2>/dev/null || true
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 2: Agent Deployment, Service, Route
# ===========================
step "Removing Agent resources"

delete_by_label "route" "app=langgraph-agent"
delete_by_label "service" "app=langgraph-agent"
delete_by_label "deployment" "app=langgraph-agent"
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 3: InferenceService and ServingRuntime
# ===========================
step "Removing InferenceService and ServingRuntime"

delete_resource "inferenceservice" "gemma-4-e4b"
delete_resource "servingruntime" "gemma-4-e4b"

# Wait briefly for KServe to clean up predictor pods
echo "  Waiting for model serving pods to terminate..."
oc wait pod \
  -n "${NAMESPACE}" \
  -l "serving.kserve.io/inferenceservice=gemma-4-e4b" \
  --for=delete \
  --timeout=120s 2>/dev/null || true
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 4: MCP resources (Gateway, MCPServer CRs)
# ===========================
step "Removing MCP resources"

# MCPServerRegistration and MCPGatewayExtension CRs
delete_by_label "mcpserverregistration.mcp.kuadrant.io" "app=mcp-gateway"
delete_by_label "mcpgatewayextension.mcp.kuadrant.io" "app=mcp-gateway"

# HTTPRoutes (Gateway API) used by MCP
delete_by_label "httproute.gateway.networking.k8s.io" "app=mcp-gateway"

# The Gateway itself
delete_resource "gateway.gateway.networking.k8s.io" "mcp-gateway"

# MCP server deployments and services
delete_by_label "deployment" "app=mcp-gateway"
delete_by_label "service" "app=mcp-gateway"
delete_by_label "deployment" "app.kubernetes.io/part-of=mcp-servers"
delete_by_label "service" "app.kubernetes.io/part-of=mcp-servers"
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 5: RAG infrastructure (pgvector StatefulSet, PVCs)
# ===========================
step "Removing RAG infrastructure (pgvector)"

delete_by_label "statefulset" "app=pgvector"
delete_by_label "deployment" "app=pgvector"
delete_by_label "service" "app=pgvector"

# PVCs are not automatically deleted with StatefulSets; delete explicitly.
delete_by_label "pvc" "app=pgvector"
delete_resource "pvc" "pgvector-data"
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 6: Monitoring resources
# ===========================
step "Removing monitoring resources (ServiceMonitor, PrometheusRule, Grafana dashboards)"

delete_by_label "servicemonitor.monitoring.coreos.com" "app=vllm-serving"
delete_resource "servicemonitor" "vllm-metrics"

delete_by_label "prometheusrule.monitoring.coreos.com" "app=vllm-serving"
delete_resource "prometheusrule" "vllm-alerts"

# Grafana dashboard ConfigMaps
delete_by_label "configmap" "grafana_dashboard=1"
delete_resource "configmap" "ai-platform-dashboard"

# MLflow
delete_resource "mlflowserver.mlflow.opendatahub.io" "mlflow"
delete_by_label "deployment" "app=mlflow"
delete_by_label "service" "app=mlflow"
delete_by_label "route" "app=mlflow"
delete_by_label "pvc" "app=mlflow"

# TrustyAI
delete_by_label "trustyaiservice.trustyai.opendatahub.io" "app.kubernetes.io/part-of=trustyai"
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 7: Governance resources (AuthConfig)
# ===========================
step "Removing governance resources (AuthConfig, guardrails)"

delete_resource "authconfig.authorino.kuadrant.io" "gemma-4-e4b-auth"
delete_by_label "authconfig.authorino.kuadrant.io" "opendatahub.io/component=model-auth"

# Guardrails orchestrator
delete_by_label "deployment" "app=guardrails-orchestrator"
delete_by_label "service" "app=guardrails-orchestrator"
delete_resource "configmap" "guardrails-config"
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 8: Evaluation resources (LMEvalJob CRs)
# ===========================
step "Removing evaluation resources (LMEvalJob CRs)"

# Delete all LMEvalJob CRs in the namespace
oc delete lmevaljob --all \
  -n "${NAMESPACE}" \
  --ignore-not-found \
  --wait=false 2>/dev/null || true

delete_by_label "job" "app.kubernetes.io/part-of=lm-eval"
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 9: ConfigMaps and Secrets
# ===========================
step "Removing application ConfigMaps and Secrets"

# Delete tutorial-labeled ConfigMaps and Secrets (preserves system-managed ones)
delete_by_label "configmap" "tutorial-level=3,tutorial-module=M5"
delete_by_label "secret" "tutorial-level=3,tutorial-module=M5"

# Named resources that may not have tutorial labels
delete_resource "configmap" "langgraph-agent-config"
delete_resource "configmap" "agent-with-mcp-config"
delete_resource "configmap" "mcp-servers-config"
delete_resource "secret" "pgvector-credentials"
delete_resource "secret" "mcp-gateway-tls"
delete_resource "secret" "model-s3-credentials"
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 10: RBAC (Roles, RoleBindings, ServiceAccounts)
# ===========================
step "Removing RBAC resources"

delete_by_label "rolebinding" "tutorial-level=3"
delete_by_label "role" "tutorial-level=3"
delete_by_label "serviceaccount" "tutorial-level=3"

# Named RBAC resources that may not have tutorial labels
delete_resource "serviceaccount" "agent-sa"
delete_resource "serviceaccount" "model-serving-sa"
delete_resource "rolebinding" "agent-model-access"
delete_resource "role" "model-inference-role"

# Cluster-scoped RBAC resources (these are NOT namespaced)
echo "  Removing cluster-scoped RBAC resources..."
oc delete clusterrolebinding \
  -l "tutorial-level=3,tutorial-module=M5,app.kubernetes.io/part-of=ai-platform" \
  --ignore-not-found 2>/dev/null || true
oc delete clusterrole \
  -l "tutorial-level=3,tutorial-module=M5,app.kubernetes.io/part-of=ai-platform" \
  --ignore-not-found 2>/dev/null || true
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 11: NetworkPolicies
# ===========================
step "Removing NetworkPolicies"

oc delete networkpolicy --all \
  -n "${NAMESPACE}" \
  --ignore-not-found 2>/dev/null || true
echo -e "  ${GREEN}Done${NC}"

# ===========================
# Step 12: Delete the namespace
# ===========================
step "Deleting namespace '${NAMESPACE}'"

echo -e "  ${YELLOW}This may take a minute while OpenShift finalizes resource cleanup...${NC}"
oc delete namespace "${NAMESPACE}" \
  --ignore-not-found \
  --wait=false 2>/dev/null || true

# Wait for the namespace to be fully terminated (up to 5 minutes)
echo "  Waiting for namespace to terminate..."
timeout=300
elapsed=0
while oc get namespace "${NAMESPACE}" -o name &>/dev/null; do
  if [[ "${elapsed}" -ge "${timeout}" ]]; then
    echo -e "  ${YELLOW}WARNING: Namespace '${NAMESPACE}' is still terminating after ${timeout}s.${NC}"
    echo -e "  ${YELLOW}This usually means a finalizer is blocking deletion.${NC}"
    echo -e "  ${YELLOW}Check with: oc get namespace ${NAMESPACE} -o yaml${NC}"
    break
  fi
  sleep 5
  elapsed=$((elapsed + 5))
done

if ! oc get namespace "${NAMESPACE}" -o name &>/dev/null; then
  echo -e "  Namespace '${NAMESPACE}' terminated successfully."
fi
echo -e "  ${GREEN}Done${NC}"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  Teardown Summary"
echo "============================================"
echo "  Steps completed: ${step_count}"
echo ""
echo "  Resources removed:"
echo "    - ArgoCD Application (${ARGOCD_APP})"
echo "    - Agent Deployment, Service, Route"
echo "    - InferenceService and ServingRuntime (gemma-4-e4b)"
echo "    - MCP Gateway and MCPServer registrations"
echo "    - pgvector StatefulSet and PVCs"
echo "    - Monitoring (ServiceMonitor, PrometheusRule, Grafana dashboards)"
echo "    - MLflow and TrustyAI"
echo "    - Governance (AuthConfig, guardrails)"
echo "    - Evaluation (LMEvalJob CRs)"
echo "    - ConfigMaps and Secrets"
echo "    - RBAC (Roles, RoleBindings, ServiceAccounts)"
echo "    - NetworkPolicies"
echo "    - Namespace (${NAMESPACE})"
echo ""
if oc get namespace "${NAMESPACE}" -o name &>/dev/null; then
  echo -e "  STATUS: ${YELLOW}NAMESPACE STILL TERMINATING${NC}"
  echo "  Run 'oc get namespace ${NAMESPACE} -o yaml' to check finalizers."
else
  echo -e "  STATUS: ${GREEN}TEARDOWN COMPLETE${NC}"
fi
echo "============================================"
echo ""
