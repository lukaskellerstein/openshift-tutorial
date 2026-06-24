#!/usr/bin/env bash
# generate-haproxy-config.sh — Generate HAProxy configuration for UPI installations
#
# Generates an haproxy.cfg file for OpenShift UPI installations.
# Customize the variables below to match your environment.
#
# Usage:
#   ./scripts/generate-haproxy-config.sh > /etc/haproxy/haproxy.cfg
#   systemctl restart haproxy
#
# Prerequisites:
#   - HAProxy installed on the load balancer host
#   - Network connectivity to all OpenShift nodes

set -euo pipefail

# --- Configuration ---
# Modify these variables to match your environment

BOOTSTRAP_IP="192.168.1.20"
MASTER_0_IP="192.168.1.21"
MASTER_1_IP="192.168.1.22"
MASTER_2_IP="192.168.1.23"
WORKER_0_IP="192.168.1.31"
WORKER_1_IP="192.168.1.32"
WORKER_2_IP="192.168.1.33"

# Set to "yes" during initial installation, "no" after bootstrap-complete
INCLUDE_BOOTSTRAP="yes"

# --- Generate Configuration ---

cat <<EOF
# HAProxy configuration for OpenShift UPI installation
# Generated: $(date)
#
# IMPORTANT: After bootstrap-complete, re-run this script with
# INCLUDE_BOOTSTRAP="no" and restart HAProxy.

global
    log         127.0.0.1 local2
    chroot      /var/lib/haproxy
    pidfile     /var/run/haproxy.pid
    maxconn     4000
    user        haproxy
    group       haproxy
    daemon
    stats socket /var/lib/haproxy/stats

defaults
    mode        tcp
    log         global
    option      tcplog
    option      dontlognull
    timeout connect 10s
    timeout client  1m
    timeout server  1m
    retries     3

# --------------------------------------------------
# Stats page (optional, useful for debugging)
# Access at http://<lb-ip>:9000/stats
# --------------------------------------------------
listen stats
    bind *:9000
    mode http
    stats enable
    stats uri /stats
    stats refresh 10s
    stats admin if LOCALHOST

# --------------------------------------------------
# Kubernetes API Server (port 6443)
# --------------------------------------------------
frontend api-server
    bind *:6443
    default_backend api-server-backend
    option tcplog

backend api-server-backend
    balance roundrobin
    option httpchk GET /readyz HTTP/1.0
    option log-health-checks
    default-server inter 10s downinter 5s rise 2 fall 3 slowstart 60s maxconn 250 maxqueue 256 weight 100
EOF

if [[ "${INCLUDE_BOOTSTRAP}" == "yes" ]]; then
cat <<EOF
    server bootstrap ${BOOTSTRAP_IP}:6443 check check-ssl verify none
EOF
fi

cat <<EOF
    server master-0   ${MASTER_0_IP}:6443 check check-ssl verify none
    server master-1   ${MASTER_1_IP}:6443 check check-ssl verify none
    server master-2   ${MASTER_2_IP}:6443 check check-ssl verify none

# --------------------------------------------------
# Machine Config Server (port 22623)
# --------------------------------------------------
frontend machine-config-server
    bind *:22623
    default_backend machine-config-server-backend
    option tcplog

backend machine-config-server-backend
    balance roundrobin
    default-server inter 10s downinter 5s rise 2 fall 3 slowstart 60s maxconn 250 maxqueue 256 weight 100
EOF

if [[ "${INCLUDE_BOOTSTRAP}" == "yes" ]]; then
cat <<EOF
    server bootstrap ${BOOTSTRAP_IP}:22623 check
EOF
fi

cat <<EOF
    server master-0   ${MASTER_0_IP}:22623 check
    server master-1   ${MASTER_1_IP}:22623 check
    server master-2   ${MASTER_2_IP}:22623 check

# --------------------------------------------------
# Ingress HTTP (port 80)
# --------------------------------------------------
frontend ingress-http
    bind *:80
    default_backend ingress-http-backend
    option tcplog

backend ingress-http-backend
    balance roundrobin
    option httpchk GET /healthz/ready HTTP/1.0
    option log-health-checks
    default-server inter 10s downinter 5s rise 2 fall 3 slowstart 60s maxconn 250 maxqueue 256 weight 100
    server worker-0 ${WORKER_0_IP}:80 check port 1936
    server worker-1 ${WORKER_1_IP}:80 check port 1936
    server worker-2 ${WORKER_2_IP}:80 check port 1936

# --------------------------------------------------
# Ingress HTTPS (port 443)
# --------------------------------------------------
frontend ingress-https
    bind *:443
    default_backend ingress-https-backend
    option tcplog

backend ingress-https-backend
    balance roundrobin
    option httpchk GET /healthz/ready HTTP/1.0
    option log-health-checks
    default-server inter 10s downinter 5s rise 2 fall 3 slowstart 60s maxconn 250 maxqueue 256 weight 100
    server worker-0 ${WORKER_0_IP}:443 check port 1936
    server worker-1 ${WORKER_1_IP}:443 check port 1936
    server worker-2 ${WORKER_2_IP}:443 check port 1936
EOF

echo ""
echo "# Configuration generated successfully." >&2
echo "# After bootstrap-complete, set INCLUDE_BOOTSTRAP=\"no\" and re-generate." >&2
