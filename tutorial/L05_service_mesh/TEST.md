# L05 — Testing & Validation Guide

Test every L05 service mesh feature by interacting with the ShopInsights dashboard in a browser, then observing what happens in Kiali and OpenShift Console Traces.

**Prerequisites:** `setup.sh` and `demo.sh` have completed successfully.

---

## URLs

Get your cluster-specific URLs by running:

```bash
echo "Dashboard:      https://$(oc get route dashboard-ui -n shopinsights -o jsonpath='{.spec.host}')"
echo "Kiali:          https://$(oc get route kiali -n istio-system -o jsonpath='{.spec.host}')"
echo "Console Traces: https://$(oc get route console -n openshift-console -o jsonpath='{.spec.host}')/observe/traces"
```

Open all three URLs in separate browser tabs — you'll switch between them throughout the tests.

- **Dashboard** — the ShopInsights app. Every click here generates traffic through the service mesh.
- **Kiali** — service mesh observability (workloads, services, Istio config). Login with your OpenShift credentials.
- **Console Traces** — distributed tracing built into the OpenShift Console (Observe > Traces).

---

## Step 1: Generate traffic from the Dashboard

Open the **Dashboard** and click through all three tabs:

1. Click **Products** tab — this calls `products-service`
2. Click **Refresh** a few times to generate more requests
3. Click **Orders** tab — this calls `orders-service`
4. Click **Refresh** a few times
5. Click **Analytics** tab — this calls `analytics-service` (which also calls products-service and orders-service internally)
6. Click **Refresh** a few times

Every click generates HTTP requests that flow through the ambient mesh (ztunnel mTLS) and the waypoint proxy (L7 routing + tracing).

---

## Step 2: Observe traces in OpenShift Console

Switch to the **Console Traces** tab.

1. Select **Tempo instance**: `istio-system / sample`
2. **Tenant** auto-selects `dev`
3. Set **Time range** to `Last 30 minutes`
4. You should see a **scatter plot** of trace durations and a **trace list** below it

**What to look for:**
- Traces from `products-service.shopinsights.svc.cluster.local`, `orders-service.shopinsights.svc.cluster.local`, and `analytics-service.shopinsights.svc.cluster.local`
- Each trace represents one HTTP request processed by the waypoint proxy
- Click any trace name to see the **span waterfall** — a Gantt chart showing the request duration, HTTP method, path, and status code

**This validates:** distributed tracing pipeline (waypoint -> OTel Collector -> Tempo gateway -> Console UI).

---

## Step 3: Observe the mesh in Kiali

Switch to the **Kiali** tab (login with OpenShift SSO if prompted).

### 3a. Workloads

1. Click **Workloads** in the left sidebar
2. Select the **shopinsights** namespace
3. You should see: `dashboard-ui`, `products-service`, `orders-service`, `analytics-service`, `analytics-service-v2`, and `waypoint`
4. Click **waypoint** — this is the L7 proxy handling all HTTP traffic for labeled services

**This validates:** ambient mesh enrollment (all workloads visible, no sidecars — pod count is 1/1, not 2/2).

### 3b. Services

1. Click **Services** in the left sidebar
2. Look at the **Labels** column — `analytics-service`, `orders-service`, and `products-service` should have `istio.io/use-waypoint: waypoint`
3. Click **orders-service** — you should see the **DestinationRule** (circuit breaker) in its Istio config section
4. Click **analytics-service** — you should see the **DestinationRule** (v1/v2 subsets) and the **HTTPRoute** (canary split)

**This validates:** waypoint proxy association and Istio config (circuit breaker + canary routing).

### 3c. Istio Config

1. Click **Istio Config** in the left sidebar
2. You should see:
   - **DestinationRule** `orders-service` — circuit breaker (connection pool limits + outlier detection)
   - **DestinationRule** `analytics-service` — subsets v1 and v2
   - **HTTPRoute** `analytics-service-canary` — 90/10 traffic split
3. Green checkmarks mean the config is valid

**This validates:** all Istio resources are applied and healthy.

### 3d. Graph (limited in ambient mode)

1. Click **Graph** in the left sidebar
2. Select the **shopinsights** namespace
3. You'll see nodes for each workload but **traffic edges may not appear** — this is a known limitation of ambient mode (Kiali needs Istio Prometheus metrics that ztunnel/waypoint don't expose by default)

---

## Step 4: Test the canary split

Go back to the **Dashboard** and click the **Analytics** tab.

1. Click **Refresh** 20+ times rapidly
2. Watch the responses — approximately 90% should come from v1 and 10% from v2
3. Switch to **Kiali > Istio Config** and click the **HTTPRoute** `analytics-service-canary` to see the weight configuration (90/10)

**This validates:** canary deployment with Gateway API HTTPRoute traffic splitting through the waypoint.

---

## Step 5: Verify the NetworkPolicy

The NetworkPolicy is already applied. You've been testing it throughout — every Dashboard click proves it works:

- **Dashboard loads** in the browser — the OpenShift ingress controller is allowed through
- **All tabs return data** — intra-namespace traffic on port 8080 is allowed
- **Traces appear** — the waypoint can reach the OTel collector in istio-system

The NetworkPolicy blocks all other ingress. If it were misconfigured, the Dashboard would fail to load or show errors on the tabs.

**This validates:** defense-in-depth NetworkPolicy alongside ambient mesh mTLS.

---

## Step 6: Verify mTLS

Every request you made in the previous steps was encrypted with mTLS by ztunnel — transparently, without the application knowing. To confirm:

```bash
oc logs -n ztunnel -l app=ztunnel --tail=10 | grep "shopinsights"
```

You should see log lines like:
```
connection complete src.workload="dashboard-ui-..." dst.workload="waypoint-..." direction="outbound"
```

The `dst.identity="spiffe://cluster.local/ns/shopinsights/sa/..."` confirms mTLS with SPIFFE identity.

**This validates:** automatic mTLS in ambient mode (no sidecars, no app changes).

---

## Summary

| Feature | Generate by | Observe in |
|---------|------------|------------|
| Ambient mesh (no sidecars) | — | Kiali Workloads (pods show 1/1) |
| Automatic mTLS | Any Dashboard click | ztunnel logs (HBONE + SPIFFE) |
| Waypoint proxy (L7) | Any Dashboard click | Kiali Workloads (waypoint pod) |
| Canary split (90/10) | Dashboard Analytics tab | Kiali Istio Config (HTTPRoute) |
| Circuit breaker | — | Kiali Services > orders-service (DestinationRule) |
| Network Policy | Dashboard loads at all | Dashboard working = policy allows ingress |
| Distributed tracing | Any Dashboard click | Console Traces (Observe > Traces) |

---

## Trace Pipeline Architecture

```
Browser --> Dashboard UI --> products/orders/analytics services
                                    |
                              [ztunnel mTLS]
                                    |
                              [waypoint proxy]
                                    |
                            OTLP HTTP (port 4318)
                                    |
                            OTel Collector
                          (adds X-Scope-OrgID: dev
                           + bearer token auth)
                                    |
                            OTLP gRPC + TLS
                                    |
                            Tempo gateway
                                    |
                            Tempo storage
                                    |
                        Console Traces
                      (Observe > Traces)
```

---

## Known Limitations

1. **Kiali traffic graph** — shows nodes but not traffic edges. Ambient mode proxies don't expose `istio_requests_total` metrics to Prometheus. All other Kiali views work.

2. **Trace span coverage** — only waypoint-labeled services produce spans. `dashboard-ui` (the client) doesn't appear in traces because it isn't routed through the waypoint.

3. **Circuit breaker** — the DestinationRule is configured but won't visibly trip under normal browsing. You'd need a load testing tool to exceed 50 concurrent TCP connections.

4. **No standalone Jaeger UI** — multitenancy (required by Console Traces) makes the Jaeger UI inaccessible in a browser. The Tempo gateway requires bearer token auth. Use Console Traces instead — it's the supported replacement.
