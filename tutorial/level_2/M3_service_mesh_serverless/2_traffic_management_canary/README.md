# L2-M3.2 — Traffic Management & Canary Deployments

**Level:** Practitioner
**Duration:** 45 min

## Overview

In Kubernetes, you can split traffic between Deployment versions using multiple Services and manual label manipulation, but it is brittle and limited to coarse-grained percentages. OpenShift Service Mesh (Istio) gives you fine-grained traffic management through VirtualServices and DestinationRules -- the same primitives Istio users know, but installed and configured through OpenShift operators. In this lesson you will perform a full canary deployment with progressive traffic shifting (90/10, 50/50, then 100), configure circuit breakers to prevent cascading failures, set up retry and timeout policies, and visualize everything in Kiali.

## Prerequisites

- Completed: L2-M3.1 (OpenShift Service Mesh installed with ServiceMeshControlPlane and ServiceMeshMemberRoll configured)
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI installed and logged in
- Service Mesh operators installed (Elasticsearch, Jaeger, Kiali, OpenShift Service Mesh)
- A project enrolled in the ServiceMeshMemberRoll (this lesson uses `bookinfo-mesh`)

## K8s Context

In vanilla Kubernetes, traffic splitting between application versions typically involves:

1. **Multiple Deployments** with different pod labels (e.g., `version: v1` and `version: v2`).
2. **A single Service** that selects both versions (if labels overlap) -- which gives roughly equal distribution by pod count, not by percentage.
3. **Ingress controllers** (NGINX, Traefik) that support canary annotations -- but these are vendor-specific and limited to ingress-level traffic only.

For circuit breaking, Kubernetes offers no native solution. You rely on application-level libraries (Hystrix, resilience4j) or a service mesh.

If you have used Istio on Kubernetes directly, the VirtualService and DestinationRule CRDs will be familiar. OpenShift Service Mesh wraps Istio with multi-tenant isolation, operator-based lifecycle management, and Kiali pre-integrated for observability.

## Concepts

### VirtualServices

A VirtualService defines how requests are routed to a Service. It intercepts traffic at the Envoy sidecar and applies routing rules *before* the request reaches the upstream Service. You can:

- Split traffic by weight (percentages) across multiple subsets.
- Route based on HTTP headers, URI paths, or query parameters.
- Apply retries, timeouts, and fault injection.

Think of it as a programmable layer between your Service and the actual pods.

### DestinationRules

A DestinationRule defines **subsets** of a Service (usually mapping to versions) and connection-level policies (circuit breaking, connection pool settings, TLS mode). While VirtualServices say *where* traffic goes, DestinationRules say *how* connections to that destination behave.

### Canary Deployments

A canary deployment rolls out a new version to a small percentage of traffic first. If metrics look good, you gradually shift more traffic. If something breaks, you shift back to 0%. This is safer than a rolling update because:

- You control the blast radius (only 10% of users see the new version initially).
- You can observe error rates, latency, and business metrics before committing.
- Rollback is instant -- just change the weight back.

### Circuit Breakers

Circuit breakers prevent a failing service from cascading failures to its callers. When a destination exceeds error thresholds (too many consecutive 5xx errors, too many pending requests, or too many connections), the circuit "opens" and subsequent requests fail fast rather than waiting and timing out.

### Kiali Dashboard

Kiali is OpenShift Service Mesh's observability console. It provides:

- A real-time service topology graph showing traffic flow and error rates.
- VirtualService and DestinationRule configuration validation.
- Distributed tracing integration (Jaeger).
- Health indicators per service, workload, and application.

## Step-by-Step

### Step 1: Create the Project and Enroll in the Mesh

If you completed L2-M3.1, you may already have a project enrolled in the mesh. If not, create one and add it to the ServiceMeshMemberRoll.

```bash
# Create the project
oc new-project bookinfo-mesh

# Verify the ServiceMeshMemberRoll includes your project
# (This should have been configured in L2-M3.1)
oc get servicemeshmemberroll default -n istio-system -o jsonpath='{.spec.members}' 
```

Expected output:
```
["bookinfo-mesh"]
```

If your project is not listed, add it:

```bash
oc patch servicemeshmemberroll default -n istio-system \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/members/-", "value": "bookinfo-mesh"}]'
```

### Step 2: Deploy the Stable Version (v1)

Deploy v1 of a sample application. We use a simple HTTP service that returns its version in the response body -- this makes it easy to verify which version is handling traffic.

```bash
# Apply the v1 Deployment
oc apply -f manifests/deployment-v1.yaml

# Apply the v2 Deployment (but it will receive no traffic yet)
oc apply -f manifests/deployment-v2.yaml

# Apply the Service
oc apply -f manifests/service.yaml
```

Verify both versions are running:

```bash
oc get pods -l app=canary-demo -n bookinfo-mesh
```

Expected output:
```
NAME                               READY   STATUS    RESTARTS   AGE
canary-demo-v1-6b8d9f7c5d-xk2p4   2/2     Running   0          30s
canary-demo-v2-7f4e8a6b3c-rm9n1   2/2     Running   0          28s
```

Note the `2/2` in the READY column -- this means the Envoy sidecar was injected alongside your application container. If you see `1/1`, sidecar injection is not working. Check that the namespace has the annotation `sidecar.istio.io/inject: "true"` or that the pods have it.

### Step 3: Create the DestinationRule with Subsets

The DestinationRule maps version labels to named subsets. These subsets are what VirtualService routing rules reference.

```bash
oc apply -f manifests/destination-rule.yaml
```

```yaml
# manifests/destination-rule.yaml defines two subsets:
#   "v1" -> pods with label version: v1
#   "v2" -> pods with label version: v2
```

Verify:

```bash
oc get destinationrule canary-demo -n bookinfo-mesh -o yaml
```

### Step 4: Route All Traffic to v1 (Baseline)

Start with 100% of traffic going to v1. This establishes a baseline before introducing canary traffic.

```bash
oc apply -f manifests/virtualservice-100-v1.yaml
```

Create a Route so you can access the service from outside the mesh:

```bash
oc apply -f manifests/gateway.yaml
oc apply -f manifests/route.yaml
```

Test the baseline:

```bash
# Get the route URL
ROUTE_URL=$(oc get route canary-demo -n bookinfo-mesh -o jsonpath='{.spec.host}')

# Send 10 requests -- all should return v1
for i in $(seq 1 10); do
  curl -s http://${ROUTE_URL}/version
  echo ""
done
```

Expected output:
```
{"version":"v1","pod":"canary-demo-v1-6b8d9f7c5d-xk2p4"}
{"version":"v1","pod":"canary-demo-v1-6b8d9f7c5d-xk2p4"}
{"version":"v1","pod":"canary-demo-v1-6b8d9f7c5d-xk2p4"}
... (all v1)
```

### Step 5: Canary Phase 1 -- Shift 10% to v2 (90/10)

Now introduce the canary. Only 10% of traffic goes to v2 -- enough to detect problems, low enough to limit blast radius.

```bash
oc apply -f manifests/virtualservice-canary-90-10.yaml
```

Verify the traffic split:

```bash
# Send 100 requests and count versions
for i in $(seq 1 100); do
  curl -s http://${ROUTE_URL}/version
  echo ""
done | grep -c '"v2"'
```

Expected output (approximately):
```
10
```

You should see roughly 10 out of 100 requests hitting v2. The exact number will vary -- Envoy uses weighted random selection, not strict round-robin.

**What to monitor during canary:**
- Error rates: Are v2 responses returning 5xx errors?
- Latency: Is v2 slower than v1?
- Business metrics: Are conversion rates or key KPIs different?

Open Kiali to visualize the traffic split:

```bash
# Get the Kiali route
oc get route kiali -n istio-system -o jsonpath='{.spec.host}'
```

Navigate to the Kiali URL in your browser. Go to **Graph** > select the `bookinfo-mesh` namespace. You should see traffic flowing to both v1 (90%) and v2 (10%) with colored edges indicating success (green) or errors (red).

### Step 6: Canary Phase 2 -- Shift to 50/50

If v2 looks healthy at 10%, increase to 50%.

```bash
oc apply -f manifests/virtualservice-canary-50-50.yaml
```

Verify:

```bash
for i in $(seq 1 100); do
  curl -s http://${ROUTE_URL}/version
  echo ""
done | grep -c '"v2"'
```

Expected output (approximately):
```
50
```

### Step 7: Canary Phase 3 -- Promote v2 to 100%

v2 has proven itself. Route all traffic to v2.

```bash
oc apply -f manifests/virtualservice-100-v2.yaml
```

Verify:

```bash
for i in $(seq 1 10); do
  curl -s http://${ROUTE_URL}/version
  echo ""
done
```

Expected output:
```
{"version":"v2","pod":"canary-demo-v2-7f4e8a6b3c-rm9n1"}
{"version":"v2","pod":"canary-demo-v2-7f4e8a6b3c-rm9n1"}
... (all v2)
```

At this point, you can safely scale down or delete the v1 Deployment:

```bash
oc scale deployment canary-demo-v1 --replicas=0 -n bookinfo-mesh
```

### Step 8: Configure Circuit Breakers

Now add circuit breaker settings to protect against cascading failures. Apply the DestinationRule with circuit breaker configuration:

```bash
oc apply -f manifests/destination-rule-circuit-breaker.yaml
```

This configuration limits:
- **Maximum connections**: 100 per host
- **Maximum pending requests**: 10 (requests queued when all connections are busy)
- **Maximum requests per connection**: 10
- **Consecutive errors before ejection**: 5 (after 5 consecutive 5xx errors, the host is ejected from the load balancing pool)
- **Ejection duration**: 30 seconds (the host is ejected for 30s before being re-evaluated)
- **Maximum ejection percentage**: 50% (never eject more than half the hosts)

To test the circuit breaker, you can use a load testing tool:

```bash
# Install fortio (a load testing tool) if not already available
# Or use the fortio pod deployed in the mesh
oc apply -f manifests/fortio-client.yaml

# Wait for the pod to be ready
oc wait --for=condition=ready pod -l app=fortio -n bookinfo-mesh --timeout=60s

# Send concurrent requests to trigger circuit breaking
oc exec $(oc get pod -l app=fortio -n bookinfo-mesh -o jsonpath='{.items[0].metadata.name}') \
  -c fortio -- \
  fortio load -c 50 -qps 0 -n 200 \
  http://canary-demo.bookinfo-mesh.svc.cluster.local:8080/version
```

In the output, look for `Code 503` responses -- these indicate the circuit breaker is tripping. The `overflow` counter in Envoy stats will also increment.

### Step 9: Configure Retry and Timeout Policies

Apply a VirtualService with retry and timeout policies:

```bash
oc apply -f manifests/virtualservice-resilience.yaml
```

This configuration adds:
- **Timeout**: 5 seconds per request (if the upstream does not respond within 5s, the request fails).
- **Retries**: up to 3 attempts, with each retry attempt timing out after 2 seconds. Retries trigger on `5xx` errors, `gateway-error`, and `connect-failure`.

To verify retries are working, you can check Envoy stats:

```bash
# Check retry stats on a sidecar
oc exec $(oc get pod -l app=canary-demo,version=v2 -n bookinfo-mesh -o jsonpath='{.items[0].metadata.name}') \
  -c istio-proxy -- \
  pilot-agent request GET stats | grep retry
```

Expected output (after some traffic):
```
cluster.outbound|8080||canary-demo.bookinfo-mesh.svc.cluster.local.retry_or_shadow_abandoned: 0
cluster.outbound|8080||canary-demo.bookinfo-mesh.svc.cluster.local.upstream_rq_retry: 3
cluster.outbound|8080||canary-demo.bookinfo-mesh.svc.cluster.local.upstream_rq_retry_success: 2
```

### Step 10: Visualize in Kiali

Open Kiali and explore the traffic management configuration:

```bash
# Get the Kiali route
KIALI_URL=$(oc get route kiali -n istio-system -o jsonpath='{.spec.host}')
echo "Open in browser: https://${KIALI_URL}"
```

In Kiali:

1. **Graph view**: Select the `bookinfo-mesh` namespace. Choose "Versioned app graph" from the dropdown. Enable "Traffic Animation" to see requests flowing in real time. The edge labels show requests per second and error rates.

2. **Istio Config**: Navigate to Istio Config in the left sidebar. You should see your VirtualService and DestinationRule listed with green checkmarks (valid configuration). If there are warnings, Kiali will explain what is wrong.

3. **Workloads view**: Click on `canary-demo-v2` to see inbound/outbound metrics, logs, and traces for the canary version specifically.

4. **Traffic policies**: In the service detail page, Kiali shows the active traffic routing rules and lets you edit weights directly through the UI (useful for quick adjustments during a real canary).

## Verification

Run the following checks to confirm everything is working:

```bash
# 1. Verify VirtualService exists and has the expected routes
oc get virtualservice canary-demo -n bookinfo-mesh -o jsonpath='{.spec.http[0].route[*].weight}'
# Expected: weights matching your current traffic split

# 2. Verify DestinationRule subsets
oc get destinationrule canary-demo -n bookinfo-mesh -o jsonpath='{.spec.subsets[*].name}'
# Expected: v1 v2

# 3. Verify the Service is reachable
ROUTE_URL=$(oc get route canary-demo -n bookinfo-mesh -o jsonpath='{.spec.host}')
curl -s -o /dev/null -w "%{http_code}" http://${ROUTE_URL}/version
# Expected: 200

# 4. Verify sidecar injection (2/2 containers per pod)
oc get pods -l app=canary-demo -n bookinfo-mesh -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[*].ready
# Expected: all containers show "true,true"

# 5. Verify Kiali can see the configuration
KIALI_URL=$(oc get route kiali -n istio-system -o jsonpath='{.spec.host}')
echo "Open https://${KIALI_URL} and check Graph view for bookinfo-mesh namespace"
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift Service Mesh |
|--------|-----------|----------------------|
| Traffic splitting | Manual label manipulation or Ingress annotations (vendor-specific) | VirtualService with weighted routing (standard Istio API) |
| Canary deployments | Requires Flagger, Argo Rollouts, or custom scripting | Native via VirtualService weight updates; Kiali UI for visualization |
| Circuit breakers | Application-level libraries (Hystrix, resilience4j) | DestinationRule `outlierDetection` -- infrastructure-level, language-agnostic |
| Retries and timeouts | Application code or Ingress annotations | VirtualService `retries` and `timeout` fields -- transparent to the app |
| Observability | Install Prometheus, Grafana, Jaeger separately | Kiali, Jaeger, Prometheus, Grafana pre-integrated by the operator |
| Multi-tenancy | Istio is cluster-scoped by default | Service Mesh is multi-tenant via ServiceMeshMemberRoll |
| Installation | Helm chart or istioctl, manual lifecycle | Operator-managed with CRDs (ServiceMeshControlPlane) |
| mTLS | Manual configuration | Enabled by default in the control plane |

## Key Takeaways

- **VirtualServices control routing logic** (where traffic goes), while **DestinationRules control connection behavior** (how traffic gets there). You almost always need both.
- **Canary deployments with traffic splitting** are safer than rolling updates because you control the exact percentage of users exposed to the new version, and rollback is instantaneous.
- **Circuit breakers operate at the infrastructure level** via Envoy sidecars, so every service gets protection regardless of programming language or framework -- no library changes needed.
- **Retry and timeout policies should be tuned carefully**: aggressive retries can amplify load during an outage (retry storms). Start conservative and adjust based on observed behavior.
- **Kiali provides real-time visibility** into traffic flow, configuration validation, and health status -- use it actively during canary deployments to make promote/rollback decisions.

## Troubleshooting

### Traffic split percentages do not match expected ratios

Envoy uses weighted random selection, not deterministic round-robin. With small sample sizes (10-20 requests), variance is high. Send at least 100 requests to see percentages stabilize. Also verify that the VirtualService was actually applied:

```bash
oc get virtualservice canary-demo -n bookinfo-mesh -o yaml | grep weight
```

### Pods show 1/1 READY instead of 2/2

Sidecar injection is not working. Check:

```bash
# Verify the namespace is in the ServiceMeshMemberRoll
oc get servicemeshmemberroll default -n istio-system -o yaml

# Verify sidecar injection annotation on the namespace or pod
oc get namespace bookinfo-mesh -o jsonpath='{.metadata.annotations}'
```

If missing, add the annotation:

```bash
oc label namespace bookinfo-mesh istio-injection=enabled
```

Then delete the pods to trigger re-creation with sidecars.

### VirtualService has no effect

The VirtualService `hosts` field must match the Service name exactly. Also verify the `gateways` field includes `mesh` (for in-mesh traffic) or your Gateway name (for ingress traffic):

```bash
oc get virtualservice canary-demo -o jsonpath='{.spec.hosts}'
oc get virtualservice canary-demo -o jsonpath='{.spec.gateways}'
```

### Circuit breaker not tripping

The outlier detection settings in the DestinationRule only apply when there are multiple endpoints (pods). With a single pod per subset, there is nothing to eject. Scale up:

```bash
oc scale deployment canary-demo-v2 --replicas=3 -n bookinfo-mesh
```

### Kiali shows "Unknown" traffic sources

This usually means requests are coming from outside the mesh (pods without sidecars). Ensure all communicating services are in the ServiceMeshMemberRoll and have sidecars injected.

## Cleanup

```bash
# Delete all resources created in this lesson
oc delete virtualservice canary-demo -n bookinfo-mesh
oc delete destinationrule canary-demo -n bookinfo-mesh
oc delete gateway canary-demo-gateway -n bookinfo-mesh
oc delete route canary-demo -n bookinfo-mesh
oc delete deployment canary-demo-v1 canary-demo-v2 -n bookinfo-mesh
oc delete service canary-demo -n bookinfo-mesh
oc delete deployment fortio -n bookinfo-mesh
oc delete service fortio -n bookinfo-mesh

# Or delete everything by label
oc delete all -l tutorial-level=2,tutorial-module=M3 -n bookinfo-mesh
oc delete virtualservice,destinationrule,gateway -l tutorial-level=2,tutorial-module=M3 -n bookinfo-mesh

# Optionally delete the project
oc delete project bookinfo-mesh
```

## Next Steps

In **L2-M3.3 -- OpenShift Serverless (Knative)**, you will install Knative Serving and Eventing operators and learn how to deploy services that scale to zero. Knative also supports traffic splitting between revisions -- you will see how it compares to the Istio-based approach you learned here.
