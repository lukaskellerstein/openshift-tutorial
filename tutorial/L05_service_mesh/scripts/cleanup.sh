#!/usr/bin/env bash
# L05 — Cleanup: remove service mesh components
set -euo pipefail

echo "=== L05 Cleanup ==="

# Remove canary resources
echo "Removing canary resources..."
oc delete httproute analytics-service-canary -n shopinsights 2>/dev/null || true
oc delete service analytics-service-v1 analytics-service-v2 -n shopinsights 2>/dev/null || true
oc delete deployment analytics-service-v2 -n shopinsights 2>/dev/null || true
oc delete destinationrule analytics-service orders-service -n shopinsights 2>/dev/null || true
oc delete peerauthentication default -n shopinsights 2>/dev/null || true
oc delete networkpolicy shopinsights-mesh-policy -n shopinsights 2>/dev/null || true

# Remove version label from analytics
echo "Removing version label from analytics deployment..."
oc patch deployment analytics-service -n shopinsights \
  --type=json -p '[{"op":"remove","path":"/spec/template/metadata/labels/version"}]' 2>/dev/null || true

# Remove waypoint proxy and service labels
echo "Removing waypoint proxy and service labels..."
oc label service analytics-service orders-service products-service -n shopinsights istio.io/use-waypoint- 2>/dev/null || true
oc delete gateway waypoint -n shopinsights 2>/dev/null || true

# Remove ambient mesh enrollment
echo "Removing ambient mesh enrollment..."
oc label namespace shopinsights istio.io/dataplane-mode- 2>/dev/null || true

# Remove ztunnel impersonation RBAC
echo "Removing ztunnel impersonation RBAC..."
oc delete clusterrolebinding ztunnel-impersonation 2>/dev/null || true
oc delete clusterrole ztunnel-impersonation 2>/dev/null || true

# Remove observability
echo "Removing UIPlugin, OTel collector, Kiali, and Tempo..."
oc delete uiplugin distributed-tracing 2>/dev/null || true
oc delete opentelemetrycollector otel-collector -n istio-system 2>/dev/null || true
oc delete clusterrolebinding tempomonolithic-traces-write tempomonolithic-traces-read 2>/dev/null || true
oc delete clusterrole tempomonolithic-traces-write tempomonolithic-traces-read 2>/dev/null || true
oc delete serviceaccount otel-collector -n istio-system 2>/dev/null || true
oc delete kiali kiali -n istio-system 2>/dev/null || true
oc delete tempomonolithic sample -n istio-system 2>/dev/null || true
oc delete telemetry mesh-tracing -n istio-system 2>/dev/null || true
oc adm policy remove-cluster-role-from-user cluster-monitoring-view \
  -z kiali-service-account -n istio-system 2>/dev/null || true

# Remove Istio components
echo "Removing Istio components..."
oc delete ztunnel default 2>/dev/null || true
oc delete istiocni default 2>/dev/null || true
oc delete istio default 2>/dev/null || true
oc delete project istio-system 2>/dev/null || true
oc delete project istio-cni 2>/dev/null || true
oc delete project ztunnel 2>/dev/null || true

# Remove operators (optional)
echo "Removing operator subscriptions..."
oc delete subscription servicemeshoperator3 -n openshift-operators 2>/dev/null || true
oc delete subscription kiali-ossm -n openshift-operators 2>/dev/null || true
oc delete subscription tempo-product -n openshift-operators 2>/dev/null || true
oc delete subscription cluster-observability-operator -n openshift-operators 2>/dev/null || true
oc delete subscription opentelemetry-product -n openshift-operators 2>/dev/null || true

# Clean up CSVs
echo "Removing operator CSVs..."
oc delete csv -n openshift-operators -l operators.coreos.com/servicemeshoperator3.openshift-operators 2>/dev/null || true
oc delete csv -n openshift-operators -l operators.coreos.com/kiali-ossm.openshift-operators 2>/dev/null || true
oc delete csv -n openshift-operators -l operators.coreos.com/tempo-product.openshift-operators 2>/dev/null || true
oc delete csv -n openshift-operators -l operators.coreos.com/cluster-observability-operator.openshift-operators 2>/dev/null || true
oc delete csv -n openshift-operators -l operators.coreos.com/opentelemetry-product.openshift-operators 2>/dev/null || true

echo ""
echo "=== L05 Cleanup Complete ==="
