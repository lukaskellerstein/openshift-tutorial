#!/usr/bin/env bash
# L12 — Cleanup: remove Grafana and custom dashboards
set -euo pipefail

echo "=== L12 Cleanup ==="

# --- Grafana dashboards ---
echo "Removing Grafana dashboards..."
oc delete grafanadashboard shopinsights-overview -n shopinsights 2>/dev/null || true
oc delete grafanadashboard shopinsights-products -n shopinsights 2>/dev/null || true
oc delete grafanadashboard shopinsights-logs -n shopinsights 2>/dev/null || true
oc delete grafanadashboard shopinsights-traces -n shopinsights 2>/dev/null || true

# --- Grafana datasources ---
echo "Removing Grafana datasources..."
oc delete grafanadatasource prometheus loki tempo -n shopinsights 2>/dev/null || true

# --- Grafana instance ---
echo "Removing Grafana instance..."
oc delete grafana grafana -n shopinsights 2>/dev/null || true

# --- RBAC ---
echo "Removing Grafana RBAC..."
oc delete clusterrolebinding grafana-tempo-traces-reader 2>/dev/null || true
oc delete clusterrolebinding grafana-loki-logs-reader 2>/dev/null || true
oc delete clusterrole grafana-loki-logs-reader 2>/dev/null || true
oc adm policy remove-cluster-role-from-user cluster-monitoring-view \
  -z grafana-sa -n shopinsights 2>/dev/null || true

# --- Grafana Operator ---
echo "Removing Grafana Operator..."
oc delete subscription grafana-operator -n openshift-operators 2>/dev/null || true
oc delete csv -n openshift-operators -l operators.coreos.com/grafana-operator.openshift-operators 2>/dev/null || true
for csv in $(oc get csv -n openshift-operators --no-headers 2>/dev/null | grep -i grafana | awk '{print $1}'); do
  oc delete csv "$csv" -n openshift-operators 2>/dev/null || true
done

echo ""
echo "=== L12 Cleanup Complete ==="
echo "Note: L07 resources (Prometheus, Loki, ServiceMonitor, etc.) were NOT removed."
echo "To remove those, run L07/scripts/cleanup.sh."
