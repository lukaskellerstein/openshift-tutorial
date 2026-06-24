# L1-M4.2 — Routes vs Ingress

**Level:** Foundations
**Duration:** 30 min

## Overview

In Kubernetes you expose HTTP services externally through an Ingress resource backed by a separately installed ingress controller. OpenShift predates Ingress with its own **Route** resource and ships a production-ready HAProxy-based router out of the box. This lesson walks you through creating both a Route and a Kubernetes Ingress pointing to the same backend Service so you can see the differences firsthand, and explores Route-specific features like TLS termination modes and annotations.

## Prerequisites

- Completed: L1-M4.1 (Services & Pod Networking)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `developer` (`oc login -u developer -p developer https://api.crc.testing:6443`)

## K8s Context

In vanilla Kubernetes, exposing an HTTP service outside the cluster requires two things:

1. **An Ingress resource** — a declarative routing rule (host, path, backend Service).
2. **An Ingress controller** — a separate component you must install yourself (NGINX, Traefik, HAProxy, etc.). Without it the Ingress resource does nothing.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
spec:
  rules:
    - host: my-app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  number: 8080
```

TLS configuration requires manually creating a Secret with the certificate and key, then referencing it in the Ingress `tls` block. There is no built-in concept of TLS termination modes — the behavior depends entirely on the controller you chose.

## Concepts

### Routes: OpenShift's Native Ingress

OpenShift introduced Routes in version 3 (2015), years before Kubernetes standardized the Ingress API. A Route is an OpenShift-specific resource (`route.openshift.io/v1`) that maps an external hostname to an internal Service.

Key advantages over basic Ingress:

- **Pre-installed router** — An HAProxy-based router runs in the `openshift-ingress` namespace from the moment the cluster starts. No setup required.
- **Automatic hostname generation** — If you omit `spec.host`, OpenShift generates one: `<route-name>-<project>.apps.<cluster-domain>`.
- **Built-in TLS termination modes** — Routes support three modes natively:
  - **Edge** — TLS terminates at the router. Traffic between the router and the pod is unencrypted (HTTP). The router's default wildcard certificate is used unless you supply your own.
  - **Passthrough** — The router passes encrypted traffic directly to the pod. The pod must handle TLS itself. No path-based routing is possible in this mode.
  - **Re-encrypt** — TLS terminates at the router and is re-established to the pod. Both the external and internal connections are encrypted, potentially with different certificates.
- **Route annotations** — Fine-grained control over HAProxy behavior: timeouts, load-balancing algorithms, rate limiting, IP whitelisting, and more.

### Ingress on OpenShift

Kubernetes Ingress resources also work on OpenShift. The OpenShift router processes them alongside Routes — it acts as both a Route controller and an Ingress controller. Under the hood, the router translates each Ingress into an internal Route object.

This means you do not need to install a separate ingress controller on OpenShift. Your existing Ingress manifests from Kubernetes will work, but you gain additional capabilities by using Routes.

### When to Use Which

| Scenario | Recommendation |
|----------|---------------|
| New OpenShift-native app | Use Routes for richer features |
| Migrating existing K8s manifests | Ingress works fine as-is |
| Need TLS passthrough or re-encrypt | Use Routes (Ingress supports these via annotations, but Routes are more explicit) |
| Multi-cluster portability | Use Ingress for K8s compatibility |
| Need HAProxy-specific tuning | Use Route annotations |

### Route Annotations

Routes support annotations that control HAProxy behavior. Common ones:

| Annotation | Purpose | Example Value |
|------------|---------|---------------|
| `haproxy.router.openshift.io/timeout` | Backend timeout | `60s` |
| `haproxy.router.openshift.io/balance` | Load-balancing algorithm | `roundrobin`, `leastconn`, `source` |
| `haproxy.router.openshift.io/rate-limit-connections` | Connection rate limit | `true` |
| `haproxy.router.openshift.io/rate-limit-connections.rate-http` | HTTP rate limit (per second) | `10` |
| `haproxy.router.openshift.io/ip_whitelist` | Restrict to specific source IPs | `192.168.1.0/24` |
| `router.openshift.io/cookie_name` | Session affinity cookie name | `my_session` |

## Step-by-Step

### Step 1: Create a project for this lesson

```bash
oc new-project routes-demo \
  --display-name="Routes vs Ingress Demo" \
  --description="L1-M4.2: Comparing Routes and Ingress"
```

### Step 2: Deploy a simple backend application

Deploy an NGINX-based application that serves a default page. Apply the Deployment and Service manifests:

```bash
oc apply -f manifests/deployment.yaml
oc apply -f manifests/service.yaml
```

The Deployment (`manifests/deployment.yaml`) runs a single NGINX pod:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-app
  labels:
    app: demo-app
    tutorial-level: "1"
    tutorial-module: "M4"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo-app
  template:
    metadata:
      labels:
        app: demo-app
    spec:
      containers:
        - name: nginx
          image: bitnami/nginx:latest
          ports:
            - containerPort: 8080
```

> **Note:** We use `bitnami/nginx` instead of the official `nginx` image because it runs as a non-root user, which is compatible with OpenShift's default `restricted` SCC. The official `nginx` image tries to bind to port 80 as root and will fail on OpenShift.

The Service (`manifests/service.yaml`) exposes the Deployment internally:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: demo-app
  labels:
    app: demo-app
    tutorial-level: "1"
    tutorial-module: "M4"
spec:
  selector:
    app: demo-app
  ports:
    - port: 8080
      targetPort: 8080
      protocol: TCP
```

Wait for the pod to be running:

```bash
oc get pods -l app=demo-app -w
```

Expected output:

```
NAME                        READY   STATUS    RESTARTS   AGE
demo-app-5d4f7b8c9-xk2mn   1/1     Running   0          30s
```

Press `Ctrl+C` once the pod is `Running`.

### Step 3: Create an OpenShift Route

Apply the Route manifest:

```bash
oc apply -f manifests/openshift-route.yaml
```

The Route (`manifests/openshift-route.yaml`):

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: demo-app-route
  labels:
    app: demo-app
    tutorial-level: "1"
    tutorial-module: "M4"
spec:
  to:
    kind: Service
    name: demo-app
  port:
    targetPort: 8080
```

Notice that we did not specify `spec.host`. OpenShift will automatically generate a hostname.

Check the Route:

```bash
oc get route demo-app-route
```

Expected output:

```
NAME             HOST/PORT                                        PATH   SERVICES   PORT   TERMINATION   WILDCARD
demo-app-route   demo-app-route-routes-demo.apps-crc.testing             demo-app   8080                 None
```

The hostname follows the pattern: `<route-name>-<project>.apps-crc.testing`.

Test the Route:

```bash
curl -s http://demo-app-route-routes-demo.apps-crc.testing | head -5
```

You should see the NGINX welcome page HTML.

### Step 4: Create a Route with edge TLS termination

Now create a Route with TLS. Apply the edge TLS Route manifest:

```bash
oc apply -f manifests/route-edge-tls.yaml
```

The Route (`manifests/route-edge-tls.yaml`):

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: demo-app-edge
  labels:
    app: demo-app
    tutorial-level: "1"
    tutorial-module: "M4"
spec:
  host: demo-app-edge-routes-demo.apps-crc.testing
  to:
    kind: Service
    name: demo-app
  port:
    targetPort: 8080
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

The `insecureEdgeTerminationPolicy: Redirect` tells the router to redirect HTTP requests to HTTPS automatically.

Check the Route:

```bash
oc get route demo-app-edge
```

Expected output:

```
NAME            HOST/PORT                                        PATH   SERVICES   PORT   TERMINATION   WILDCARD
demo-app-edge   demo-app-edge-routes-demo.apps-crc.testing              demo-app   8080   edge          None
```

Notice the `TERMINATION` column now shows `edge`.

Test the HTTPS endpoint (use `-k` to accept the self-signed wildcard certificate on CRC):

```bash
curl -k https://demo-app-edge-routes-demo.apps-crc.testing | head -5
```

Test that HTTP redirects to HTTPS:

```bash
curl -I http://demo-app-edge-routes-demo.apps-crc.testing
```

Expected output:

```
HTTP/1.1 302 Found
location: https://demo-app-edge-routes-demo.apps-crc.testing/
```

### Step 5: Create a Route with annotations

Apply the annotated Route manifest to see HAProxy-level configuration:

```bash
oc apply -f manifests/route-annotated.yaml
```

The Route (`manifests/route-annotated.yaml`):

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: demo-app-annotated
  labels:
    app: demo-app
    tutorial-level: "1"
    tutorial-module: "M4"
  annotations:
    haproxy.router.openshift.io/timeout: "60s"
    haproxy.router.openshift.io/balance: "leastconn"
    router.openshift.io/cookie_name: "my_app_session"
spec:
  host: demo-app-annotated-routes-demo.apps-crc.testing
  to:
    kind: Service
    name: demo-app
  port:
    targetPort: 8080
  tls:
    termination: edge
```

Verify the annotations are set:

```bash
oc get route demo-app-annotated -o jsonpath='{.metadata.annotations}' | python3 -m json.tool
```

Expected output (abbreviated):

```json
{
    "haproxy.router.openshift.io/balance": "leastconn",
    "haproxy.router.openshift.io/timeout": "60s",
    "router.openshift.io/cookie_name": "my_app_session"
}
```

### Step 6: Create a Kubernetes Ingress for comparison

Now create a standard Kubernetes Ingress pointing to the same Service:

```bash
oc apply -f manifests/k8s-ingress.yaml
```

The Ingress (`manifests/k8s-ingress.yaml`):

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: demo-app-ingress
  labels:
    app: demo-app
    tutorial-level: "1"
    tutorial-module: "M4"
spec:
  rules:
    - host: demo-app-ingress-routes-demo.apps-crc.testing
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: demo-app
                port:
                  number: 8080
```

Check the Ingress:

```bash
oc get ingress demo-app-ingress
```

Expected output:

```
NAME               CLASS    HOSTS                                              ADDRESS   PORTS   AGE
demo-app-ingress   <none>   demo-app-ingress-routes-demo.apps-crc.testing                80      5s
```

The OpenShift router automatically picks up the Ingress and creates an internal Route for it. You can verify this:

```bash
oc get routes
```

You will see your manually created Routes AND an auto-generated one for the Ingress.

Test the Ingress:

```bash
curl -s http://demo-app-ingress-routes-demo.apps-crc.testing | head -5
```

You should see the same NGINX welcome page — the same backend, accessed through a Kubernetes Ingress instead of an OpenShift Route.

### Step 7: Compare all routes side by side

List all Routes and the Ingress together to see them in one view:

```bash
echo "=== OpenShift Routes ==="
oc get routes

echo ""
echo "=== Kubernetes Ingress ==="
oc get ingress
```

Expected output:

```
=== OpenShift Routes ===
NAME                 HOST/PORT                                              PATH   SERVICES   PORT   TERMINATION   WILDCARD
demo-app-annotated   demo-app-annotated-routes-demo.apps-crc.testing               demo-app   8080   edge          None
demo-app-edge        demo-app-edge-routes-demo.apps-crc.testing                    demo-app   8080   edge          None
demo-app-route       demo-app-route-routes-demo.apps-crc.testing                   demo-app   8080                 None

=== Kubernetes Ingress ===
NAME               CLASS    HOSTS                                              ADDRESS   PORTS   AGE
demo-app-ingress   <none>   demo-app-ingress-routes-demo.apps-crc.testing                80      2m
```

### Step 8: Create a Route using the CLI (alternative to YAML)

You can also create Routes directly with `oc expose`:

```bash
oc expose service demo-app --name=demo-app-cli
```

Check it:

```bash
oc get route demo-app-cli
```

Expected output:

```
NAME           HOST/PORT                                      PATH   SERVICES   PORT   TERMINATION   WILDCARD
demo-app-cli   demo-app-cli-routes-demo.apps-crc.testing             demo-app   8080                 None
```

This is the quickest way to expose a Service, but it only creates a basic HTTP Route without TLS. For TLS, use `oc create route`:

```bash
oc create route edge demo-app-cli-tls \
  --service=demo-app \
  --port=8080
```

```bash
oc get route demo-app-cli-tls
```

Expected output:

```
NAME               HOST/PORT                                          PATH   SERVICES   PORT   TERMINATION   WILDCARD
demo-app-cli-tls   demo-app-cli-tls-routes-demo.apps-crc.testing             demo-app   8080   edge          None
```

### Step 9: Inspect the router itself

To see the pre-installed HAProxy router that powers all of this:

```bash
oc get pods -n openshift-ingress
```

Expected output:

```
NAME                              READY   STATUS    RESTARTS   AGE
router-default-7b5df44ff-abcde    1/1     Running   0          24h
```

Check the IngressController configuration:

```bash
oc get ingresscontroller default -n openshift-ingress-operator -o yaml | grep -A5 "spec:"
```

This shows the cluster's default ingress controller that handles both Routes and Ingress resources.

## Verification

Run these commands to confirm the lesson is complete:

```bash
# 1. Backend pod is running
oc get pods -l app=demo-app -o jsonpath='{.items[0].status.phase}'
# Expected: Running

# 2. Basic Route works
curl -s -o /dev/null -w "%{http_code}" http://demo-app-route-routes-demo.apps-crc.testing
# Expected: 200

# 3. Edge TLS Route works
curl -s -k -o /dev/null -w "%{http_code}" https://demo-app-edge-routes-demo.apps-crc.testing
# Expected: 200

# 4. Kubernetes Ingress works
curl -s -o /dev/null -w "%{http_code}" http://demo-app-ingress-routes-demo.apps-crc.testing
# Expected: 200

# 5. All Routes are listed
oc get routes --no-headers | wc -l
# Expected: 5 or more (route, edge, annotated, cli, cli-tls, plus any auto-generated)
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| External HTTP routing resource | `Ingress` | `Route` (native), plus `Ingress` is supported |
| Ingress controller | Must install separately (NGINX, Traefik, etc.) | HAProxy-based router pre-installed |
| Automatic hostname | Not available | Generated if `spec.host` is omitted |
| TLS termination modes | Depends on controller; configured via annotations | Built-in: edge, passthrough, re-encrypt |
| HTTP-to-HTTPS redirect | Controller-specific annotation | `insecureEdgeTerminationPolicy: Redirect` |
| Load-balancing tuning | Controller-specific | Standard HAProxy annotations |
| CLI shortcut | None | `oc expose svc`, `oc create route edge/passthrough/reencrypt` |
| Session affinity | Controller-specific annotation | `router.openshift.io/cookie_name` annotation |
| Wildcard certificate | Manual setup | Auto-generated for `*.apps.<domain>` |

## Key Takeaways

- OpenShift Routes predate Kubernetes Ingress and provide richer, out-of-the-box functionality including automatic hostname generation, built-in TLS termination modes (edge, passthrough, re-encrypt), and HAProxy annotations for fine-grained control.
- The HAProxy-based router is pre-installed on every OpenShift cluster — you never need to install or manage an ingress controller.
- Kubernetes Ingress resources work on OpenShift without modification because the OpenShift router acts as both a Route controller and an Ingress controller.
- Use Routes for OpenShift-native applications where you want the full feature set; use Ingress when you need portability across Kubernetes distributions.
- Route annotations give you direct control over HAProxy behavior (timeouts, load balancing, rate limiting, session affinity) without needing controller-specific configuration.

## Cleanup

```bash
# Delete all resources created in this lesson
oc delete all -l tutorial-level=1,tutorial-module=M4 -n routes-demo
oc delete ingress demo-app-ingress -n routes-demo
oc delete route demo-app-cli demo-app-cli-tls -n routes-demo

# Delete the project
oc delete project routes-demo
```

## Next Steps

In **L1-M4.3 — TLS & Certificates**, you will dive deeper into certificate management on OpenShift — how auto-generated certificates work, how to attach custom certificates to Routes, and how to integrate cert-manager for automated certificate lifecycle management.
