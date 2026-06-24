# L2-M3.1 --- OpenShift Service Mesh (Istio)

**Level:** Practitioner
**Duration:** 1 hr

## Overview

In Kubernetes, setting up Istio requires downloading `istioctl`, manually installing CRDs, and configuring each component yourself. OpenShift packages the entire service mesh as a set of operators that you install from OperatorHub --- and it adds opinionated defaults for security, multi-tenancy, and observability. In this lesson you will install the OpenShift Service Mesh operator and its dependencies (Kiali, Jaeger/Tempo), create a `ServiceMeshControlPlane`, enroll namespaces via `ServiceMeshMemberRoll`, inject Envoy sidecars, configure basic traffic management, and enable mutual TLS (mTLS) between services.

## Prerequisites

- Level 1 completed (especially L1-M4 Networking & Routes and L1-M2 Projects & RBAC)
- OpenShift cluster running (CRC with at least 16 GB RAM allocated, or Developer Sandbox)
- Logged in as `kubeadmin` (operator installation requires cluster-admin)
- `oc` CLI installed and configured

> **Resource note:** The Service Mesh control plane is memory-intensive. If using CRC, ensure you have allocated at least 16 GB of RAM (`crc config set memory 16384`). With less memory, pods may fail to schedule or get OOMKilled.

## K8s Context

In vanilla Kubernetes, service mesh adoption typically follows this path:

1. Download `istioctl` or use a Helm chart to install Istio.
2. Label namespaces with `istio-injection=enabled` for automatic sidecar injection.
3. Install add-ons separately --- Kiali for visualization, Jaeger for tracing, Prometheus/Grafana for metrics.
4. Define `VirtualService`, `DestinationRule`, `Gateway`, and `PeerAuthentication` resources.
5. Manage Istio upgrades yourself.

You own the entire lifecycle: installation, configuration, upgrade, and add-on management. There is no multi-tenancy model --- anyone with namespace access can affect mesh-wide settings.

## Concepts

### OpenShift Service Mesh vs Upstream Istio

OpenShift Service Mesh is based on the upstream Istio project but differs in several important ways:

| Aspect | Upstream Istio | OpenShift Service Mesh |
|--------|---------------|----------------------|
| Installation | `istioctl install` or Helm | Operator from OperatorHub |
| Multi-tenancy | Cluster-wide, single mesh | Multi-tenant: multiple meshes, each scoped to specific namespaces |
| Namespace enrollment | Label-based (`istio-injection=enabled`) | Explicit via `ServiceMeshMemberRoll` or `ServiceMeshMember` |
| Sidecar injection | Namespace label | Pod annotation (`sidecar.istio.io/inject: "true"`) |
| Observability | Install Kiali/Jaeger separately | Operators installed as dependencies |
| Upgrades | Manual | Operator-managed with OLM |
| Security defaults | Permissive mTLS | Configurable per control plane, with strict mTLS easy to enable |

### Key Custom Resources

- **ServiceMeshControlPlane (SMCP):** Defines the mesh configuration --- which Istio components to run, their settings, and security policies. This replaces `istioctl install` profiles.
- **ServiceMeshMemberRoll (SMMR):** Lists the namespaces that belong to the mesh. Only namespaces in this list get mesh functionality. This is the multi-tenancy boundary.
- **ServiceMeshMember (SMM):** An alternative to SMMR that lets namespace owners self-enroll their namespace into a mesh (requires RBAC permissions).

### Dependency Operators

The Service Mesh operator requires these operators to be installed first:

1. **OpenShift Distributed Tracing Platform (Jaeger)** or **Tempo Operator** --- provides distributed tracing.
2. **Kiali Operator** --- provides the service mesh observability dashboard.
3. **OpenShift Elasticsearch Operator** (optional) --- backend storage for Jaeger traces (not needed if using the in-memory or Tempo backend).

### Sidecar Injection

Unlike upstream Istio's namespace-label approach, OpenShift Service Mesh uses **pod-level annotations**:

```yaml
metadata:
  annotations:
    sidecar.istio.io/inject: "true"
```

This gives finer-grained control --- you can inject sidecars into specific Deployments rather than every pod in a namespace.

**Why the difference?** OpenShift's multi-tenant model means a single namespace could theoretically be enrolled in different meshes. Pod-level annotation avoids ambiguity and gives application teams explicit control.

## Step-by-Step

### Step 1: Install the Required Operators

You need cluster-admin privileges to install operators. Log in as `kubeadmin`:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

Install the three required operators. You can do this via the Web Console (OperatorHub) or via CLI. We will use the CLI.

First, install the OpenShift Distributed Tracing Platform (Jaeger) operator:

```bash
oc apply -f manifests/operator-jaeger.yaml
```

Next, install the Kiali operator:

```bash
oc apply -f manifests/operator-kiali.yaml
```

Finally, install the OpenShift Service Mesh operator:

```bash
oc apply -f manifests/operator-servicemesh.yaml
```

Wait for all operators to be ready:

```bash
oc get csv -n openshift-operators -w
```

Expected output (after a few minutes):

```
NAME                              DISPLAY                                    VERSION   PHASE
jaeger-operator.v1.51.0           Red Hat OpenShift distributed tracing...   1.51.0    Succeeded
kiali-operator.v1.73.0            Kiali Operator                             1.73.0    Succeeded
servicemeshoperator.v2.5.0        Red Hat OpenShift Service Mesh             2.5.0     Succeeded
```

Wait until all three operators show `PHASE: Succeeded` before continuing.

> **Tip:** You can also install these operators through the Web Console at **Operators > OperatorHub**. Search for "Service Mesh", "Kiali", and "Jaeger" respectively.

### Step 2: Create the Control Plane Namespace

The Service Mesh control plane runs in its own namespace (by convention, `istio-system`):

```bash
oc new-project istio-system
```

Expected output:

```
Now using project "istio-system" on server "https://api.crc.testing:6443".
```

### Step 3: Deploy the ServiceMeshControlPlane

Apply the control plane configuration:

```bash
oc apply -f manifests/smcp.yaml -n istio-system
```

The SMCP creates Istiod (the control plane), Envoy ingress/egress gateways, Kiali, and Jaeger instances. Watch the rollout:

```bash
oc get smcp -n istio-system -w
```

Expected output (takes 3-5 minutes):

```
NAME    READY   STATUS            PROFILES      VERSION   AGE
basic   9/9     ComponentsReady   ["default"]   2.5.0     4m
```

Wait for `READY` to show the full component count and `STATUS` to show `ComponentsReady`.

You can also inspect all the pods created:

```bash
oc get pods -n istio-system
```

Expected output:

```
NAME                                    READY   STATUS    RESTARTS   AGE
grafana-6f8b9c6d76-xk4j2               2/2     Running   0          3m
istio-egressgateway-7c8f9b6d4-m9kls     1/1     Running   0          3m
istio-ingressgateway-6d87b5c784-n2vqr   1/1     Running   0          3m
istiod-basic-7f6b9c4d68-lp5rt           1/1     Running   0          3m
jaeger-small-5c7d8b6f49-qr2wt          2/2     Running   0          3m
kiali-6b8c9d7f58-vn3xm                 1/1     Running   0          3m
prometheus-7d9c8b6f47-kj8np             2/2     Running   0          3m
```

### Step 4: Create the Application Namespace and Enroll It in the Mesh

Create a project for the sample application:

```bash
oc new-project mesh-demo
```

Now apply the `ServiceMeshMemberRoll` to enroll the `mesh-demo` namespace in the mesh:

```bash
oc apply -f manifests/smmr.yaml -n istio-system
```

Verify enrollment:

```bash
oc get smmr default -n istio-system -o wide
```

Expected output:

```
NAME      READY   STATUS       AGE   MEMBERS
default   1/1     Configured   10s   ["mesh-demo"]
```

> **Important:** The SMMR must be named `default` and live in the same namespace as the SMCP. This is an OpenShift Service Mesh convention.

### Step 5: Deploy the Sample Application

We will deploy a simple two-tier application: a **frontend** service and a **backend** service with two versions (v1 and v2). This setup lets us demonstrate sidecar injection and traffic management.

Note the `sidecar.istio.io/inject: "true"` annotation in each Deployment --- this is how OpenShift Service Mesh knows to inject the Envoy sidecar.

Deploy all application resources:

```bash
oc apply -f manifests/backend-v1-deployment.yaml -n mesh-demo
oc apply -f manifests/backend-v2-deployment.yaml -n mesh-demo
oc apply -f manifests/backend-service.yaml -n mesh-demo
oc apply -f manifests/frontend-deployment.yaml -n mesh-demo
oc apply -f manifests/frontend-service.yaml -n mesh-demo
```

Or deploy everything at once:

```bash
oc apply -f manifests/backend-v1-deployment.yaml \
         -f manifests/backend-v2-deployment.yaml \
         -f manifests/backend-service.yaml \
         -f manifests/frontend-deployment.yaml \
         -f manifests/frontend-service.yaml \
         -n mesh-demo
```

Wait for all pods to be ready:

```bash
oc get pods -n mesh-demo -w
```

Expected output (each pod should have `2/2` containers --- the app container plus the Envoy sidecar):

```
NAME                          READY   STATUS    RESTARTS   AGE
backend-v1-6d8b9c7f48-xk4j2  2/2     Running   0          45s
backend-v2-7c9d8b6f59-m2nls  2/2     Running   0          45s
frontend-5b7c8d6f47-qr3wt    2/2     Running   0          45s
```

If you see `1/1` instead of `2/2`, the sidecar was not injected. Verify:
- The namespace is in the SMMR (`oc get smmr default -n istio-system`)
- The pod has the annotation `sidecar.istio.io/inject: "true"`
- The SMCP is fully ready

### Step 6: Expose the Frontend via an OpenShift Route

Create a route for the frontend service:

```bash
oc apply -f manifests/frontend-route.yaml -n mesh-demo
```

Get the route URL:

```bash
oc get route frontend -n mesh-demo -o jsonpath='{.spec.host}'
```

Test the application:

```bash
curl -s http://$(oc get route frontend -n mesh-demo -o jsonpath='{.spec.host}')
```

Expected output:

```json
{"source": "frontend", "backend_response": {"source": "backend", "version": "v1 or v2"}}
```

### Step 7: Configure Traffic Management

Now let's control how traffic flows between services. We will use an Istio `DestinationRule` to define subsets (v1 and v2) and a `VirtualService` to route all traffic to v1 initially.

Apply the destination rule and virtual service:

```bash
oc apply -f manifests/destination-rule.yaml -n mesh-demo
oc apply -f manifests/virtualservice.yaml -n mesh-demo
```

The `DestinationRule` defines two subsets based on the `version` label:
- `v1` maps to pods with `version: v1`
- `v2` maps to pods with `version: v2`

The `VirtualService` routes 100% of traffic to the `v1` subset.

Test the routing (all requests should now hit v1):

```bash
for i in $(seq 1 10); do
  curl -s http://$(oc get route frontend -n mesh-demo -o jsonpath='{.spec.host}') | python3 -m json.tool
  echo "---"
done
```

Expected output (all requests return v1):

```json
{
    "source": "frontend",
    "backend_response": {
        "source": "backend",
        "version": "v1"
    }
}
```

Now update the VirtualService to split traffic 80/20 between v1 and v2:

```bash
oc patch virtualservice backend \
  -n mesh-demo \
  --type merge \
  -p '{
    "spec": {
      "http": [{
        "route": [
          {"destination": {"host": "backend", "subset": "v1"}, "weight": 80},
          {"destination": {"host": "backend", "subset": "v2"}, "weight": 20}
        ]
      }]
    }
  }'
```

Test again --- approximately 8 out of 10 requests should hit v1, and 2 should hit v2:

```bash
for i in $(seq 1 20); do
  curl -s http://$(oc get route frontend -n mesh-demo -o jsonpath='{.spec.host}') \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['backend_response']['version'])"
done
```

Expected output (roughly 80% v1, 20% v2):

```
v1
v1
v1
v2
v1
v1
v1
v1
v2
v1
...
```

### Step 8: Enable Strict mTLS

By default, OpenShift Service Mesh uses permissive mTLS --- services accept both plaintext and encrypted traffic. Let's enforce strict mTLS so that all inter-service communication must be encrypted.

Apply the PeerAuthentication policy:

```bash
oc apply -f manifests/peer-authentication.yaml -n mesh-demo
```

This `PeerAuthentication` resource sets `mtls.mode: STRICT` for all services in the `mesh-demo` namespace.

Verify mTLS is active by checking the Kiali dashboard or by inspecting the proxy configuration:

```bash
# Check mTLS status via istioctl (if available) or via proxy config
oc exec -n mesh-demo deployment/frontend -c istio-proxy -- \
  pilot-agent request GET /stats | grep ssl.handshake
```

Expected output (non-zero ssl handshake count confirms mTLS is active):

```
cluster.outbound|8080||backend.mesh-demo.svc.cluster.local.ssl.handshake: 15
```

You can also check mTLS status from Kiali. Get the Kiali route:

```bash
oc get route kiali -n istio-system -o jsonpath='{.spec.host}'
```

Open the URL in your browser, log in with your OpenShift credentials, navigate to the `mesh-demo` namespace, and look for the lock icon on the service graph edges indicating mTLS is active.

### Step 9: Explore the Observability Tools

OpenShift Service Mesh installs several observability tools. Let's access them.

**Kiali (Service Mesh Dashboard):**

```bash
echo "https://$(oc get route kiali -n istio-system -o jsonpath='{.spec.host}')"
```

Kiali provides:
- Service graph visualization showing how services communicate
- Traffic flow rates, error rates, and response times
- mTLS status indicators
- Istio configuration validation

**Jaeger (Distributed Tracing):**

```bash
echo "https://$(oc get route jaeger -n istio-system -o jsonpath='{.spec.host}')"
```

Jaeger shows:
- End-to-end request traces across services
- Latency breakdown per service hop
- Error identification in the call chain

**Grafana (Metrics Dashboards):**

```bash
echo "https://$(oc get route grafana -n istio-system -o jsonpath='{.spec.host}')"
```

Grafana provides pre-configured Istio dashboards:
- Mesh overview (requests/sec, error rates, latencies)
- Service-level dashboards
- Workload-level dashboards

Generate some traffic to populate the dashboards:

```bash
for i in $(seq 1 50); do
  curl -s http://$(oc get route frontend -n mesh-demo -o jsonpath='{.spec.host}') > /dev/null
  sleep 0.5
done
```

> **Tip:** In the Kiali dashboard, click on the **Graph** tab, select the `mesh-demo` namespace, and watch the service graph light up with traffic flow.

## Verification

Run through this checklist to confirm everything is working:

```bash
# 1. Control plane is ready
oc get smcp -n istio-system
# Expected: READY shows full count, STATUS is ComponentsReady

# 2. Namespace is enrolled
oc get smmr default -n istio-system -o jsonpath='{.status.configuredMembers}'
# Expected: ["mesh-demo"]

# 3. All pods have sidecars (2/2 containers)
oc get pods -n mesh-demo
# Expected: All pods show 2/2 READY

# 4. Traffic management is active
oc get virtualservice,destinationrule -n mesh-demo
# Expected: VirtualService "backend" and DestinationRule "backend" listed

# 5. mTLS is enforced
oc get peerauthentication -n mesh-demo
# Expected: PeerAuthentication "default" with mtls mode STRICT

# 6. Observability tools accessible
oc get routes -n istio-system
# Expected: Routes for kiali, jaeger, grafana
```

## Troubleshooting

### Pods stuck at 1/1 (no sidecar injected)

- Verify the namespace is listed in the SMMR: `oc get smmr default -n istio-system -o yaml`
- Check the pod annotation: `oc get pod <pod-name> -n mesh-demo -o jsonpath='{.metadata.annotations.sidecar\.istio\.io/inject}'`
- Make sure the annotation is on the pod template (inside `spec.template.metadata.annotations`), not on the Deployment metadata.
- Delete and recreate the pod (sidecar injection happens at pod creation time): `oc delete pod <pod-name> -n mesh-demo`

### SMCP stuck in "Reconciling" or not reaching ComponentsReady

- Check available resources: `oc describe nodes | grep -A5 "Allocated resources"`
- CRC may need more memory. Stop CRC, increase memory (`crc config set memory 16384`), and restart.
- Check operator logs: `oc logs deployment/istio-operator -n openshift-operators`

### Kiali/Jaeger/Grafana routes not created

- These routes are created by the SMCP. Verify the SMCP addons section includes these components.
- Check the SMCP status: `oc describe smcp basic -n istio-system`

### mTLS causing connection failures

- If an application outside the mesh tries to call a meshed service with strict mTLS, it will fail. Either enroll the calling namespace in the mesh, or create a `PeerAuthentication` exception for that service.
- Check Kiali for mTLS mismatches (yellow warning icons).

### Operator installation failures

- Ensure you are logged in as `kubeadmin` or another cluster-admin user.
- Check the subscription status: `oc get subscription -n openshift-operators`
- Check install plans: `oc get installplan -n openshift-operators`

## K8s vs OpenShift Comparison

| Aspect | Kubernetes + Istio | OpenShift Service Mesh |
|--------|-------------------|----------------------|
| Installation | `istioctl install` or Helm chart | Operator from OperatorHub (3 operators) |
| Lifecycle management | Manual upgrades with `istioctl upgrade` | OLM-managed, follows operator subscription channels |
| Multi-tenancy | Single mesh per cluster (workarounds exist) | Native multi-tenancy: multiple isolated meshes per cluster |
| Namespace enrollment | Namespace label `istio-injection=enabled` | Explicit `ServiceMeshMemberRoll` or `ServiceMeshMember` |
| Sidecar injection | Namespace-level label | Pod-level annotation (finer-grained control) |
| Observability add-ons | Manually install Kiali, Jaeger, Grafana | Installed as operator dependencies, configured in SMCP |
| Configuration entry point | `IstioOperator` CR or `istioctl` flags | `ServiceMeshControlPlane` CR with OpenShift-specific fields |
| Security defaults | Permissive mTLS by default | Configurable in SMCP, easy to set strict per namespace |
| Ingress | Istio `Gateway` + `VirtualService` | Can use Routes, Istio Gateway, or both |
| Web Console integration | None | Service Mesh visible in OpenShift console topology view |

## Key Takeaways

- OpenShift Service Mesh packages Istio, Kiali, Jaeger, and Grafana as a set of operators, eliminating manual installation and lifecycle management.
- The `ServiceMeshControlPlane` CR replaces `istioctl install` profiles and provides a single declarative configuration for the entire mesh.
- Namespace enrollment is explicit (via `ServiceMeshMemberRoll`), enabling true multi-tenancy --- unlike upstream Istio's cluster-wide approach.
- Sidecar injection uses pod annotations rather than namespace labels, giving teams fine-grained control over which workloads participate in the mesh.
- mTLS can be enforced per-namespace or mesh-wide using `PeerAuthentication`, ensuring all inter-service traffic is encrypted without application changes.

## Cleanup

```bash
# Remove application resources
oc delete project mesh-demo

# Remove the service mesh control plane
oc delete smcp basic -n istio-system
oc delete project istio-system

# (Optional) Remove the operators --- only if you won't use them in later lessons
# Keep them installed if you plan to continue with L2-M3.2 (Traffic Management & Canary)
oc delete subscription jaeger-product -n openshift-operators 2>/dev/null
oc delete subscription kiali-ossm -n openshift-operators 2>/dev/null
oc delete subscription servicemeshoperator -n openshift-operators 2>/dev/null

# Clean up the CSVs
oc delete csv -n openshift-operators -l operators.coreos.com/jaeger-product.openshift-operators
oc delete csv -n openshift-operators -l operators.coreos.com/kiali-ossm.openshift-operators
oc delete csv -n openshift-operators -l operators.coreos.com/servicemeshoperator.openshift-operators
```

> **Note:** If you are continuing to L2-M3.2 (Traffic Management & Canary), keep the operators installed and only remove the `mesh-demo` project. You will recreate the control plane with a fresh configuration.

## Next Steps

In **L2-M3.2 --- Traffic Management & Canary**, you will go deeper into Istio traffic management: advanced `VirtualService` routing rules, canary deployments with automated rollout, circuit breakers with `DestinationRule` outlier detection, fault injection for chaos testing, and the Kiali dashboard for visualizing traffic flow.
