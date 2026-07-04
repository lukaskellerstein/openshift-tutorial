# L05 — Testing & Validation Guide

This guide walks through every L05 feature and shows how to verify it works. Run these checks after `setup.sh` and `demo.sh` have completed successfully.

## Get the UI URLs

```bash
# OpenShift Console — Traces view (Observe > Traces)
echo "https://$(oc get route console -n openshift-console -o jsonpath='{.spec.host}')/observe/traces"

# Kiali Dashboard (login with your OpenShift credentials)
echo "https://$(oc get route kiali -n istio-system -o jsonpath='{.spec.host}')"

# Jaeger UI (legacy, via Tempo gateway)
echo "https://$(oc get route tempo-sample-jaegerui -n istio-system -o jsonpath='{.spec.host}')"
```

---

## Test 1: Ambient Mesh Enrollment

Verify the namespace is enrolled in the ambient mesh and pods have **no sidecars**.

```bash
# Check the namespace label
oc get namespace shopinsights -o jsonpath='{.metadata.labels.istio\.io/dataplane-mode}'
# Expected: ambient

# Confirm pods are 1/1 (not 2/2 — no sidecar injected)
oc get pods -n shopinsights
# Expected: all pods show 1/1 READY
```

If pods showed 2/2, that would mean sidecar injection — ambient mode uses per-node ztunnel proxies instead.

```bash
# Verify ztunnel is running on each node
oc get pods -n ztunnel -o wide
# Expected: one ztunnel pod per node, all Running
```

---

## Test 2: Automatic mTLS

In ambient mode, ztunnel encrypts all pod-to-pod traffic with mTLS automatically. The application sees plain HTTP — encryption is transparent.

```bash
# Call a service from inside the mesh
oc exec deploy/dashboard-ui -n shopinsights -- curl -s http://products-service:8080/healthz
# Expected: {"status": "healthy"} or similar success response

oc exec deploy/dashboard-ui -n shopinsights -- curl -s http://orders-service:8080/healthz
# Expected: success response

oc exec deploy/dashboard-ui -n shopinsights -- curl -s http://analytics-service:8080/healthz
# Expected: success response
```

To confirm traffic is actually encrypted via HBONE:

```bash
# Check ztunnel logs for HBONE connections
oc logs -n ztunnel -l app=ztunnel --tail=20 | grep -i "hbone\|connect"
# Expected: log lines showing HBONE tunnel connections between pods
```

### Optional: Enforce STRICT mTLS

The `peer-authentication.yaml` manifest exists but is not applied by default. To enforce strict mTLS (reject all plaintext):

```bash
oc apply -f manifests/peer-authentication.yaml -n shopinsights
# Then re-test the curl commands above — they should still work (traffic goes through ztunnel)
```

---

## Test 3: Waypoint Proxy

The waypoint proxy provides L7 (HTTP) processing — it enables traffic splitting, circuit breaking, and distributed tracing.

```bash
# Verify waypoint pod is running
oc get pods -n shopinsights -l gateway.networking.k8s.io/gateway-name=waypoint
# Expected: 1/1 Running

# Verify services are labeled to use the waypoint
oc get service -n shopinsights -L istio.io/use-waypoint
# Expected: analytics-service, orders-service, products-service all show "waypoint"
```

To verify the waypoint is processing traffic:

```bash
# Generate a request
oc exec deploy/dashboard-ui -n shopinsights -- curl -s http://products-service:8080/products

# Check waypoint logs for the request
oc logs -n shopinsights -l gateway.networking.k8s.io/gateway-name=waypoint --tail=10
# Expected: access log entries showing HTTP method, path, response code
```

---

## Test 4: Canary Deployment (90/10 Traffic Split)

The analytics-service has two versions deployed with an HTTPRoute splitting traffic 90% to v1 and 10% to v2.

```bash
# Verify both versions are running
oc get pods -n shopinsights -l component=analytics-service
# Expected: two pods — one with version=v1, one with version=v2

# Check the HTTPRoute configuration
oc get httproute -n shopinsights
# Expected: analytics-service-canary

# View the traffic split weights
oc get httproute analytics-service-canary -n shopinsights -o yaml | grep -A5 backendRefs
# Expected: v1 weight=90, v2 weight=10
```

### Run the canary test

```bash
# Send 20 requests and count the responses
for i in $(seq 1 20); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://analytics-service:8080/healthz 2>/dev/null
  echo ""
done
# Expected: ~18 responses from v1, ~2 from v2
# The response body or headers should indicate which version handled the request
```

---

## Test 5: Circuit Breaker

The orders-service has a DestinationRule with connection pool limits and outlier detection.

```bash
# Verify the DestinationRule exists
oc get destinationrule -n shopinsights
# Expected: orders-service

# View the circuit breaker configuration
oc get destinationrule orders-service -n shopinsights -o yaml
# Expected:
#   connectionPool:
#     tcp: maxConnections=50
#     http: h2UpgradePolicy, maxRequestsPerConnection=5, maxRetries=3
#   outlierDetection:
#     consecutive5xxErrors=3, interval=10s, baseEjectionTime=30s
```

**Note:** Triggering the circuit breaker requires generating enough concurrent load to exceed the connection pool limits (50 TCP connections or 10 pending HTTP/1.1 requests). This typically requires a load testing tool like `hey` or `fortio`. Under normal traffic, the circuit breaker is a safety net — you won't see it trip.

---

## Test 6: Network Policy

The NetworkPolicy restricts which traffic can reach the shopinsights pods. It allows:
- Intra-namespace traffic on ports 8080 (app) and 15008 (HBONE)
- Istio control plane (istio-system namespace)
- Ztunnel HBONE traffic (port 15008)
- Kubelet health probes (host-network IPs)
- OpenShift ingress controller

```bash
# Verify the NetworkPolicy exists
oc get networkpolicy -n shopinsights
# Expected: shopinsights-mesh-policy

# Test that allowed traffic still works
oc exec deploy/dashboard-ui -n shopinsights -- curl -s http://products-service:8080/healthz
# Expected: success (intra-namespace traffic is allowed)

# Verify the app is reachable via the Route (ingress controller is allowed)
curl -s "https://$(oc get route dashboard-ui -n shopinsights -o jsonpath='{.spec.host}')" | head -5
# Expected: HTML response from the dashboard
```

---

## Test 7: Distributed Tracing

Traces are generated by the waypoint proxy, sent to the OpenTelemetry Collector, then forwarded to Tempo with tenant authentication. You can view traces in the **OpenShift Console** (recommended) or the legacy **Jaeger UI**.

### Generate traces

```bash
# Send traffic through waypoint-labeled services
for i in $(seq 1 10); do
  oc exec deploy/dashboard-ui -n shopinsights -- curl -s http://products-service:8080/products > /dev/null
  oc exec deploy/dashboard-ui -n shopinsights -- curl -s http://orders-service:8080/orders > /dev/null
  oc exec deploy/dashboard-ui -n shopinsights -- curl -s http://analytics-service:8080/healthz > /dev/null
done
echo "Traffic sent — traces should appear in ~10 seconds"
```

### Option A: OpenShift Console (recommended)

1. Open the OpenShift Console and navigate to **Observe > Traces**
2. Select **Tempo instance**: `istio-system / sample`
3. **Tenant** is automatically set to `dev`
4. Set the **Time range** (e.g. Last 30 minutes) and click to search
5. The scatter plot shows trace durations over time; the table lists individual traces
6. Click a trace name to see the **span waterfall** (Gantt chart) with timing details

### Option B: Jaeger UI (legacy)

1. Open the Jaeger UI URL (from the "Get UI URLs" section above)
2. In the **Service** dropdown, select a service — names use FQDN format:
   - `analytics-service.shopinsights.svc.cluster.local`
   - `orders-service.shopinsights.svc.cluster.local`
   - `products-service.shopinsights.svc.cluster.local`
3. Click **Find Traces**
4. Click any trace to see the span waterfall

> **Note:** The Jaeger UI shows a deprecation warning — Red Hat is replacing it with the Console Traces view (Option A). Both work for now.

### What to look for

- Each trace shows a single HTTP request processed by the waypoint proxy
- Spans include: HTTP method, URL path, response status code, duration
- The span's **service name** is the destination service (the one the waypoint routed to)
- Trace duration shows the end-to-end latency through the waypoint

### Trace pipeline architecture

```
Istio waypoint (Envoy) --OTLP HTTP--> OTel Collector --OTLP gRPC + auth--> Tempo gateway --> Tempo storage
                                      (adds X-Scope-OrgID: dev header
                                       and bearer token for tenant auth)
```

---

## Test 8: Kiali Dashboard

Kiali provides several views for observing the mesh. Log in with your OpenShift credentials (SSO).

### Workloads view

1. Open Kiali and navigate to **Workloads** in the left sidebar
2. Select the **shopinsights** namespace from the dropdown
3. You should see all deployments: `dashboard-ui`, `products-service`, `orders-service`, `analytics-service`, `analytics-service-v2`, and the `waypoint` proxy
4. Click any workload to see its details: pods, labels, Istio configuration

### Services view

1. Navigate to **Services**
2. You'll see all services in the shopinsights namespace
3. Services labeled with `istio.io/use-waypoint=waypoint` show the waypoint association
4. Click a service to see its details and associated Istio config (DestinationRules, HTTPRoutes)

### Istio Config view

1. Navigate to **Istio Config**
2. You should see:
   - `DestinationRule` for orders-service (circuit breaker) and analytics-service (subsets)
   - `HTTPRoute` for the canary split
   - `PeerAuthentication` (if you applied the optional STRICT mTLS)
3. Green checkmarks mean the config is valid; red/yellow indicates issues

### Graph view

1. Navigate to **Graph** and select the **shopinsights** namespace
2. You'll see the service topology with nodes for each workload
3. **Note:** In ambient mode, traffic edges (animated lines between nodes) may not appear. This is because Kiali relies on Istio Prometheus metrics (`istio_requests_total`, etc.) that the ztunnel/waypoint proxies don't expose to Prometheus without additional custom configuration. The nodes themselves will appear, but traffic flow lines require sidecar-mode Prometheus metrics.

---

## Known Limitations

1. **Kiali traffic graph** — The graph shows nodes but not traffic edges (animated lines). Ambient mode ztunnel and waypoint proxies don't expose standard `istio_requests_total` metrics to Prometheus without additional PodMonitor/ServiceMonitor configuration. All other Kiali views (Workloads, Services, Istio Config) work correctly.

2. **Trace span coverage** — Only services routed through the waypoint proxy produce HTTP-level trace spans. The `dashboard-ui` service (the client making requests) does not appear as a span source because it's not a waypoint-labeled service — it sends traffic, but the trace starts at the waypoint.

3. **OTLP protocol** — The waypoint sends traces via OTLP HTTP (port 4318) to the OTel Collector. OTLP gRPC directly from the waypoint to Tempo breaks through HBONE tunneling, so the collector acts as a bridge (receiving HTTP, forwarding gRPC with TLS + tenant auth).

4. **Tempo multitenancy** — The Console Traces UI requires TempoMonolithic with multitenancy enabled. This adds the OTel Collector as a bridge component (to inject the `X-Scope-OrgID` tenant header and bearer token that the Tempo gateway requires).

5. **Circuit breaker testing** — The circuit breaker configuration is in place but won't visibly trip under normal single-request testing. You'd need a load testing tool to exceed the connection pool limits.
