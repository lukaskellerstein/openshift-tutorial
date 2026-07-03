# LP-L02 — Expose Services Externally: Routes and TLS

**Level:** Personalized
**Duration:** 45 min

## Overview

Your four services are running inside the cluster, but nobody outside the cluster can reach them. In Kubernetes, you would create Ingress resources and point them at your Traefik ingress controller. In OpenShift, you create Routes instead — and the ingress controller (HAProxy) is already running. No Helm chart to install, no CRDs to register, no LoadBalancer service to provision. You just create a Route and get a URL.

This lesson creates Routes with edge TLS termination for all four ShopInsights services, making the Dashboard and APIs accessible from your browser.

## Prerequisites

- Completed: [L01 — Deploy the Microservices Stack](../L01_deploy_microservices/)
- All four pods running in the `shopinsights` project:
  ```bash
  oc get pods -l app=shopinsights -n shopinsights
  ```
- OpenShift cluster running (CRC or Developer Sandbox)

## K8s Context

In vanilla Kubernetes with Traefik, exposing a service externally requires:

1. **Install Traefik** — deploy it via Helm, configure a LoadBalancer Service, and manage its lifecycle yourself.
2. **Create IngressRoute resources** — define hostname-to-service mappings using Traefik's `IngressRoute` CRD (`traefik.io/v1alpha1`).
3. **Configure TLS** — install cert-manager, create a ClusterIssuer, and reference a `certResolver` in each IngressRoute.

That is three moving parts before a single request reaches your app.

In OpenShift, the HAProxy-based router is pre-installed and managed by the cluster. You create a Route, and it works.

## Concepts

### Routes

A Route is an OpenShift-native resource (`route.openshift.io/v1`) that maps an external hostname to a Service. Under the hood, the OpenShift Router — an HAProxy instance managed by the Ingress Operator — watches for Route objects and updates its configuration automatically.

Key properties of Routes:

- **Pre-installed**: The router runs in the `openshift-ingress` namespace from day one. No installation required.
- **Automatic hostname generation**: If you omit `spec.host`, OpenShift generates `<route-name>-<project>.<apps-domain>` (e.g., `<route-name>-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com`).
- **Built-in TLS**: Edge TLS is available immediately using the router's wildcard certificate. No cert-manager needed.
- **HAProxy features**: The router supports sticky sessions, rate limiting, IP whitelisting, and custom timeouts via Route annotations.

### TLS Termination Modes

Routes support three TLS termination modes:

| Mode | TLS terminates at | Backend traffic | Use case |
|------|-------------------|-----------------|----------|
| **Edge** | Router (HAProxy) | HTTP (unencrypted) | Most common. Router handles TLS, backend app does not need certs. |
| **Passthrough** | Backend pod | HTTPS (end-to-end) | App manages its own TLS certificate. Router just forwards TCP. |
| **Re-encrypt** | Router, then re-encrypted | HTTPS to backend | Both the router and the backend have certificates. Maximum security. |

For this tutorial, we use **edge** termination — the router terminates TLS and forwards plain HTTP to our services on port 8080. This is the right choice for most applications.

### Automatic Hostname Generation

Every OpenShift cluster has a wildcard apps domain. When you create a Route, OpenShift generates a hostname following this pattern:

```
<route-name>-<project-name>.<apps-domain>
```

For example, a Route named `dashboard-ui` in the `shopinsights` project gets:

```
dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com
```

You can override this with `spec.host`, but the automatic generation is convenient for development.

## Your Question, Answered

> "Is Route a replacement for Traefik?"

**Yes, for HTTP/HTTPS ingress.** The HAProxy router replaces Traefik as the external ingress layer. Here is a side-by-side comparison:

**Traefik IngressRoute (Kubernetes):**

```yaml
# Requires: Traefik CRDs installed, Traefik Deployment running,
# LoadBalancer Service provisioned, cert-manager for TLS
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: dashboard-ui
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`dashboard.example.com`)
      kind: Rule
      services:
        - name: dashboard-ui
          port: 8080
  tls:
    certResolver: letsencrypt
```

**OpenShift Route (OpenShift):**

```yaml
# Requires: nothing extra — the HAProxy router is pre-installed
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: dashboard-ui
spec:
  to:
    kind: Service
    name: dashboard-ui
  port:
    targetPort: 8080
  tls:
    termination: edge
```

The Route YAML is simpler because the infrastructure is already in place. No CRDs to install, no ingress controller to deploy, no cert-manager to configure. The router's wildcard certificate covers all Routes automatically.

**What Routes do NOT replace:**
- Traefik middleware (rate limiting, circuit breakers) — use Route annotations or the Service Mesh (L03) instead
- Traefik's dashboard — use the OpenShift Web Console's Networking > Routes view
- TCP/UDP proxying — Routes only handle HTTP/HTTPS (use Service type `LoadBalancer` or `NodePort` for TCP/UDP)

## Step-by-Step

### Step 1: Create a Route for the Dashboard UI

The Dashboard is the main entry point for users, so we expose it first.

```bash
oc apply -f manifests/dashboard-route.yaml
```

```yaml
# manifests/dashboard-route.yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: dashboard-ui
  labels:
    app: shopinsights
    component: dashboard-ui
    tutorial: personalized
    lesson: "02"
spec:
  host: dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com
  to:
    kind: Service
    name: dashboard-ui
  port:
    targetPort: 8080
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

Key fields:

- **`spec.host`**: The external hostname. We set it explicitly for clarity, but you could omit it and let OpenShift generate it.
- **`spec.to`**: Points to the `dashboard-ui` Service created in L01.
- **`spec.port.targetPort`**: The port on the Service (8080).
- **`tls.termination: edge`**: TLS terminates at the router. Traffic from the router to the pod is plain HTTP.
- **`tls.insecureEdgeTerminationPolicy: Redirect`**: HTTP requests on port 80 are redirected to HTTPS. This is a security best practice.

### Step 2: Create a Route for the Products Service API

```bash
oc apply -f manifests/products-route.yaml
```

```yaml
# manifests/products-route.yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: products-service
  labels:
    app: shopinsights
    component: products-service
    tutorial: personalized
    lesson: "02"
spec:
  host: products-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com
  to:
    kind: Service
    name: products-service
  port:
    targetPort: 8080
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

### Step 3: Create a Route for the Orders Service API

```bash
oc apply -f manifests/orders-route.yaml
```

```yaml
# manifests/orders-route.yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: orders-service
  labels:
    app: shopinsights
    component: orders-service
    tutorial: personalized
    lesson: "02"
spec:
  host: orders-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com
  to:
    kind: Service
    name: orders-service
  port:
    targetPort: 8080
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

### Step 4: Create a Route for the Analytics Service API

```bash
oc apply -f manifests/analytics-route.yaml
```

```yaml
# manifests/analytics-route.yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: analytics-service
  labels:
    app: shopinsights
    component: analytics-service
    tutorial: personalized
    lesson: "02"
spec:
  host: analytics-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com
  to:
    kind: Service
    name: analytics-service
  port:
    targetPort: 8080
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

### Step 5: Verify the Routes

List all Routes in the project:

```bash
oc get routes -l app=shopinsights
```

Expected output:

```
NAME                HOST/PORT                                          PATH   SERVICES            PORT   TERMINATION     WILDCARD
analytics-service   analytics-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com           analytics-service   8080   edge/Redirect   None
dashboard-ui        dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com                dashboard-ui        8080   edge/Redirect   None
orders-service      orders-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com              orders-service      8080   edge/Redirect   None
products-service    products-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com            products-service    8080   edge/Redirect   None
```

Test each Route with `curl`:

```bash
# Dashboard UI
curl -sk https://dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/

# Products API
curl -sk https://products-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/products

# Orders API
curl -sk https://orders-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/orders

# Analytics API
curl -sk https://analytics-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/analytics/summary

# Health endpoints
curl -sk https://products-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/healthz
curl -sk https://orders-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/healthz
curl -sk https://analytics-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/healthz
```

The `-sk` flags: `-s` suppresses the progress bar, `-k` skips TLS certificate verification (CRC uses a self-signed certificate).

### Step 6: Verify HTTP-to-HTTPS Redirect

Because we set `insecureEdgeTerminationPolicy: Redirect`, HTTP requests are automatically redirected to HTTPS:

```bash
curl -sI http://dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/ 2>&1 | head -5
```

Expected output:

```
HTTP/1.1 302 Found
location: https://dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/
```

### Step 7: View Routes in the Web Console

1. Open the Web Console (run `oc whoami --show-console` to get the URL)
2. Switch to the **Developer** perspective
3. Select the `shopinsights` project
4. Click **Topology** — each component now shows a small "open URL" icon (the arrow in the top-right corner of each node). Click it to open the Route in your browser.
5. Or navigate to **Networking > Routes** in the **Administrator** perspective to see all Routes in a table with their hostnames, TLS status, and target Services.

The Web Console also shows Route metrics (request rate, error rate, latency) if monitoring is enabled — we will explore this in L07.

## Verification

Run this verification script to confirm everything is working:

```bash
echo "=== Routes ==="
oc get routes -l app=shopinsights -o custom-columns=NAME:.metadata.name,HOST:.spec.host,TLS:.spec.tls.termination,SERVICE:.spec.to.name

echo ""
echo "=== Dashboard UI ==="
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/

echo "=== Products API ==="
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://products-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/healthz

echo "=== Orders API ==="
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://orders-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/healthz

echo "=== Analytics API ==="
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://analytics-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/healthz

echo "=== HTTP Redirect ==="
curl -sk -o /dev/null -w "HTTP %{http_code}\n" http://dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com/
```

Expected output:

```
=== Routes ===
NAME                HOST                                               TLS    SERVICE
analytics-service   analytics-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com    edge   analytics-service
dashboard-ui        dashboard-ui-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com         edge   dashboard-ui
orders-service      orders-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com       edge   orders-service
products-service    products-service-rh-ee-lkellers-dev.apps.rm1.0a51.p1.openshiftapps.com     edge   products-service

=== Dashboard UI ===
HTTP 200
=== Products API ===
HTTP 200
=== Orders API ===
HTTP 200
=== Analytics API ===
HTTP 200
=== HTTP Redirect ===
HTTP 302
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes (with Traefik) | OpenShift |
|--------|--------------------------|-----------|
| Ingress controller | Install Traefik via Helm, manage upgrades yourself | HAProxy router pre-installed and managed by the cluster |
| Resource type | `IngressRoute` CRD (Traefik-specific) | `Route` (native to OpenShift) |
| TLS certificates | Install cert-manager, create Certificate + Secret | Router wildcard cert covers all Routes automatically |
| TLS termination modes | Depends on ingress controller config | Edge, passthrough, re-encrypt — built into Route spec |
| HTTP-to-HTTPS redirect | Traefik middleware or annotation | `insecureEdgeTerminationPolicy: Redirect` |
| Hostname generation | Manual — you set the host in Ingress | Automatic — `<name>-<project>.apps.<domain>` |
| Web UI for routes | Traefik dashboard (separate) | Built into OpenShift Web Console |
| TCP/UDP proxying | Traefik supports TCP/UDP routes | Routes are HTTP/HTTPS only — use LoadBalancer/NodePort for TCP/UDP |
| Can I still use Ingress? | N/A | Yes — OpenShift supports `Ingress` objects too, converts them to Routes |
| Sticky sessions | Traefik middleware | Route annotation: `haproxy.router.openshift.io/disable_cookies` |

## Key Takeaways

- **Routes replace Traefik** for HTTP/HTTPS ingress. The HAProxy router is pre-installed — zero setup required.
- **Edge TLS** is the most common termination mode: the router handles TLS, your app serves plain HTTP on port 8080.
- **`insecureEdgeTerminationPolicy: Redirect`** should always be set to redirect HTTP to HTTPS.
- **Automatic hostnames** follow the pattern `<name>-<project>.<apps-domain>` — you do not need to configure DNS entries for development. Run `oc whoami --show-console | sed 's|https://console-openshift-console.||'` to find your cluster's apps domain.
- If you need Kubernetes `Ingress` objects for compatibility (e.g., shared Helm charts), OpenShift automatically converts them to Routes behind the scenes.

## Cleanup

Remove the Routes created in this lesson:

```bash
oc delete route -l tutorial=personalized,lesson=02
```

Verify they are gone:

```bash
oc get routes -l app=shopinsights
```

Note: This only removes the Routes. The underlying Services and Deployments from L01 remain running. The services are just no longer accessible from outside the cluster.

## Next Steps

Your services are now accessible from outside the cluster, but all traffic between services inside the cluster is unencrypted and unobserved. In [L03: Service Mesh with Istio](../L03_service_mesh/), you will add Envoy sidecars for mutual TLS, traffic management (canary deployments), and observability (Kiali service graph).

## Deep Dive

For the full conceptual treatment of Routes vs Ingress, including passthrough and re-encrypt examples, path-based routing, and custom certificates, see the comprehensive tutorial:
- [L1-M4.2 Routes vs Ingress](../../tutorial/level_1/M4_networking_routes/2_routes_vs_ingress/)
