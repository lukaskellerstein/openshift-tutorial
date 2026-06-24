#!/usr/bin/env bash
#
# pre-migration-audit.sh
# Audits a Kubernetes namespace for OpenShift migration readiness.
# Run this against your K8s cluster BEFORE migrating.
#
# Usage: ./pre-migration-audit.sh <namespace>
#

set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace>}"
REPORT_FILE="migration-audit-${NAMESPACE}-$(date +%Y%m%d-%H%M%S).txt"

echo "=============================================="
echo "  OpenShift Migration Readiness Audit"
echo "  Namespace: ${NAMESPACE}"
echo "  Date: $(date)"
echo "=============================================="
echo ""

# ---- 1. Check for root containers ----
echo "=== 1. Containers Running as Root ==="
echo "    (These will FAIL under OpenShift restricted SCC)"
echo ""

ROOT_CONTAINERS=0
while IFS= read -r pod; do
  [ -z "$pod" ] && continue
  uid=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.containers[*].securityContext.runAsUser}' 2>/dev/null || echo "")
  run_as_root=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.securityContext.runAsUser}' 2>/dev/null || echo "")

  if [ "$uid" = "0" ] || [ "$run_as_root" = "0" ]; then
    echo "  [FAIL] Pod '$pod' explicitly runs as root (UID 0)"
    ROOT_CONTAINERS=$((ROOT_CONTAINERS + 1))
  fi

  # Check for no securityContext (may default to root)
  sc=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].securityContext}' 2>/dev/null || echo "")
  if [ -z "$sc" ] || [ "$sc" = "{}" ]; then
    echo "  [WARN] Pod '$pod' has no securityContext (may default to root)"
    ROOT_CONTAINERS=$((ROOT_CONTAINERS + 1))
  fi
done < <(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n')

if [ "$ROOT_CONTAINERS" -eq 0 ]; then
  echo "  [PASS] No root containers detected"
fi
echo ""

# ---- 2. Check for privileged ports ----
echo "=== 2. Containers Using Privileged Ports (<1024) ==="
echo "    (Non-root users cannot bind to ports below 1024)"
echo ""

PRIV_PORTS=0
while IFS= read -r pod; do
  [ -z "$pod" ] && continue
  ports=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.containers[*].ports[*].containerPort}' 2>/dev/null || echo "")
  for port in $ports; do
    if [ "$port" -lt 1024 ] 2>/dev/null; then
      echo "  [FAIL] Pod '$pod' uses privileged port $port"
      PRIV_PORTS=$((PRIV_PORTS + 1))
    fi
  done
done < <(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n')

if [ "$PRIV_PORTS" -eq 0 ]; then
  echo "  [PASS] No privileged ports detected"
fi
echo ""

# ---- 3. Check for Ingress resources ----
echo "=== 3. Ingress Resources (Convert to Routes) ==="
echo ""

INGRESS_COUNT=$(kubectl get ingress -n "$NAMESPACE" -o name 2>/dev/null | wc -l | tr -d ' ')
if [ "$INGRESS_COUNT" -gt 0 ]; then
  echo "  [INFO] Found $INGRESS_COUNT Ingress resource(s) to convert to Routes:"
  kubectl get ingress -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name,HOSTS:.spec.rules[*].host,PATHS:.spec.rules[*].http.paths[*].path 2>/dev/null
else
  echo "  [PASS] No Ingress resources found"
fi
echo ""

# ---- 4. Check for Docker Hub images ----
echo "=== 4. Docker Hub Images (May Need Alternatives) ==="
echo "    (Consider UBI-based or Red Hat registry images)"
echo ""

DOCKERHUB_IMAGES=0
while IFS= read -r pod; do
  [ -z "$pod" ] && continue
  images=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.containers[*].image}' 2>/dev/null || echo "")
  for image in $images; do
    # Docker Hub images often lack a registry prefix or use docker.io
    if echo "$image" | grep -qvE '^(registry\.|quay\.|gcr\.|ecr\.|mcr\.|ghcr\.)' && echo "$image" | grep -qvE 'redhat\.com|redhat\.io'; then
      echo "  [WARN] Pod '$pod' uses image '$image' (likely Docker Hub)"
      DOCKERHUB_IMAGES=$((DOCKERHUB_IMAGES + 1))
    fi
  done
done < <(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n')

if [ "$DOCKERHUB_IMAGES" -eq 0 ]; then
  echo "  [PASS] No Docker Hub images detected"
fi
echo ""

# ---- 5. Check for PersistentVolumeClaims ----
echo "=== 5. Persistent Volume Claims ==="
echo "    (Ensure StorageClass compatibility on OpenShift)"
echo ""

PVC_COUNT=$(kubectl get pvc -n "$NAMESPACE" -o name 2>/dev/null | wc -l | tr -d ' ')
if [ "$PVC_COUNT" -gt 0 ]; then
  echo "  [INFO] Found $PVC_COUNT PVC(s):"
  kubectl get pvc -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,STORAGECLASS:.spec.storageClassName,SIZE:.spec.resources.requests.storage 2>/dev/null
  echo ""
  echo "  Verify that equivalent StorageClasses exist on the OpenShift cluster."
else
  echo "  [PASS] No PVCs found"
fi
echo ""

# ---- 6. Check for hostPath volumes ----
echo "=== 6. HostPath Volumes (Blocked by Default on OpenShift) ==="
echo ""

HOSTPATH=0
while IFS= read -r pod; do
  [ -z "$pod" ] && continue
  hp=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.volumes[?(@.hostPath)].name}' 2>/dev/null || echo "")
  if [ -n "$hp" ]; then
    echo "  [FAIL] Pod '$pod' uses hostPath volume(s): $hp"
    HOSTPATH=$((HOSTPATH + 1))
  fi
done < <(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n')

if [ "$HOSTPATH" -eq 0 ]; then
  echo "  [PASS] No hostPath volumes detected"
fi
echo ""

# ---- 7. Check for resource limits ----
echo "=== 7. Resource Requests and Limits ==="
echo "    (Best practice: always set on OpenShift for quota enforcement)"
echo ""

NO_LIMITS=0
while IFS= read -r pod; do
  [ -z "$pod" ] && continue
  limits=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].resources.limits}' 2>/dev/null || echo "")
  if [ -z "$limits" ] || [ "$limits" = "{}" ]; then
    echo "  [WARN] Pod '$pod' has no resource limits"
    NO_LIMITS=$((NO_LIMITS + 1))
  fi
done < <(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n')

if [ "$NO_LIMITS" -eq 0 ]; then
  echo "  [PASS] All pods have resource limits"
fi
echo ""

# ---- 8. Check RBAC ----
echo "=== 8. RBAC Resources ==="
echo ""

echo "  RoleBindings:"
kubectl get rolebindings -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name,ROLE:.roleRef.name 2>/dev/null || echo "  None found"
echo ""
echo "  ServiceAccounts:"
kubectl get sa -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name 2>/dev/null || echo "  None found"
echo ""

# ---- Summary ----
echo "=============================================="
echo "  AUDIT SUMMARY"
echo "=============================================="
echo "  Root containers / missing securityContext:  $ROOT_CONTAINERS"
echo "  Privileged ports (<1024):                   $PRIV_PORTS"
echo "  Ingress resources to convert:               $INGRESS_COUNT"
echo "  Docker Hub images:                          $DOCKERHUB_IMAGES"
echo "  PVCs to verify:                             $PVC_COUNT"
echo "  HostPath volumes:                           $HOSTPATH"
echo "  Containers without resource limits:         $NO_LIMITS"
echo "=============================================="
echo ""

TOTAL_ISSUES=$((ROOT_CONTAINERS + PRIV_PORTS + HOSTPATH))
if [ "$TOTAL_ISSUES" -gt 0 ]; then
  echo "  RESULT: $TOTAL_ISSUES blocking issue(s) found. Fix before migrating."
  echo ""
  echo "  See the lesson README.md for remediation steps."
  exit 1
else
  echo "  RESULT: No blocking issues. Ready for migration (review warnings above)."
  exit 0
fi
