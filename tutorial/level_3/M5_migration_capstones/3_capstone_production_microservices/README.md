# L3-M5.3 — Capstone: Production-Ready Microservices

**Level:** Expert
**Duration:** 2 hr

## Overview

This capstone brings together everything from Levels 1, 2, and 3 into a single, production-grade microservices deployment. You will deploy a four-service e-commerce application with a complete operational stack: Tekton CI/CD pipelines, ArgoCD GitOps, Istio service mesh with mTLS, Prometheus monitoring with custom metrics and alerts, HPA autoscaling, network policies for microsegmentation, per-service RBAC, PodDisruptionBudgets, and resource quotas. This is not a demo -- it is how you would actually run microservices on OpenShift in production.

In Kubernetes, assembling this stack requires installing and configuring a dozen independent tools (Prometheus, Grafana, Istio, ArgoCD, Tekton, cert-manager, an ingress controller, etc.). OpenShift provides all of these as pre-integrated operators. This lesson demonstrates how those pieces fit together.

## Prerequisites

- Completed: All Level 1 and Level 2 modules
- Completed: L3-M1 through L3-M4
- OpenShift 4.12+ cluster (CRC for single-node; multi-node recommended for full HA)
- `cluster-admin` access (logged in as `kubeadmin`) for operator and monitoring configuration
- Installed operators:
  - OpenShift Pipelines (Tekton) -- L2-M1.1
  - OpenShift GitOps (ArgoCD) -- L2-M1.3
  - OpenShift Service Mesh (with Kiali, Jaeger) -- L2-M3.1
- `oc` CLI and `curl` available on your workstation

> **CRC Note:** CRC can run all components in this lesson, but resource constraints may limit the number of concurrent pods. Consider reducing replica counts from 2 to 1 if CRC memory is limited. A multi-node cluster provides the full HA experience (topology spread, pod anti-affinity across hosts).

## K8s Context

In Kubernetes, deploying a production microservices application means assembling and integrating many independent components:

- **CI/CD**: Install Jenkins or configure GitHub Actions externally. No built-in build system.
- **GitOps**: Install ArgoCD via Helm, manage its lifecycle yourself.
- **Service mesh**: Install Istio manually, configure mTLS, manage Istio upgrades.
- **Monitoring**: Install the kube-prometheus-stack Helm chart, configure scrape targets in `prometheus.yml`.
- **Ingress**: Install an Ingress controller (NGINX, Traefik, etc.), create Ingress resources.
- **Security**: No default pod security enforcement. You must install and configure OPA Gatekeeper or Kyverno for admission control.
- **RBAC**: Manually create ServiceAccounts and bind them -- no defaults beyond the `default` SA.

Each tool has its own installation, configuration, upgrade lifecycle, and failure modes. Integrating them (e.g., making Prometheus scrape Istio metrics, or ArgoCD sync Tekton pipeline results) requires additional configuration glue.

OpenShift provides all of these as operators with standardized CRD-based configuration, pre-integrated and tested together as a platform.

## Concepts

### Architecture Overview

The application is a simplified e-commerce system with four microservices:

```
                                 +-------------------+
                                 |   OpenShift       |
                                 |   Route (TLS)     |
                                 +--------+----------+
                                          |
                                          v
                               +----------+----------+
                               |                     |
                               |    API Gateway      |
                               |    (Go, 2 replicas) |
                               |                     |
                               +--+------+-------+---+
                                  |      |       |
                    +-------------+  +---+---+   +-------------+
                    |                |       |                  |
                    v                v       v                  v
          +---------+-----+  +------+------+  +--------+------+
          |               |  |             |  |               |
          | Order Service |  |  Inventory  |  |    Payment    |
          | (Go, 2 repl.) |  |  Service    |  |    Service    |
          |               |  | (Go, 2 rep) |  |  (Go, 2 rep) |
          +-------+-------+  +-------------+  +---------------+
                  |                                   ^
                  +-----------------------------------+
                     (order -> payment for checkout)
```

### Full Platform Integration

This diagram shows how every OpenShift platform capability connects to the application:

```
+------------------------------------------------------------------+
|                        OpenShift Cluster                          |
|                                                                  |
|  +---------------------+     +-----------------------------+     |
|  | Tekton Pipelines    |     | ArgoCD (GitOps)             |     |
|  | clone -> build ->   |---->| watches Git repo            |     |
|  | test -> deploy      |     | syncs manifests to cluster  |     |
|  +---------------------+     +-----------------------------+     |
|                                          |                       |
|                                          v                       |
|  +-----------------------------------------------------------+  |
|  |                capstone-microservices project              |  |
|  |                                                           |  |
|  |  +-- Network Policies (microsegmentation) ------+         |  |
|  |  |                                              |         |  |
|  |  |  Route -> API GW -> Order -----> Payment     |         |  |
|  |  |                  -> Inventory                 |         |  |
|  |  |                                              |         |  |
|  |  +-- mTLS (Istio service mesh) -----------------+         |  |
|  |                                                           |  |
|  |  +-- Per-service RBAC (ServiceAccounts + Roles) --+       |  |
|  |  +-- HPAs (CPU-based autoscaling) ----------------+       |  |
|  |  +-- PDBs (disruption budgets for upgrades) ------+       |  |
|  |  +-- Resource Quotas & Limit Ranges ---------------+      |  |
|  +-----------------------------------------------------------+  |
|                              |                                   |
|                              v                                   |
|  +-----------------------------------------------------------+  |
|  |             Monitoring & Observability                     |  |
|  |                                                           |  |
|  |  Prometheus -----> ServiceMonitors (scrape /metrics)      |  |
|  |  AlertManager ---> PrometheusRules (alerts)               |  |
|  |  Kiali ----------> Service mesh topology & health         |  |
|  |  Jaeger ----------> Distributed traces                    |  |
|  +-----------------------------------------------------------+  |
+------------------------------------------------------------------+
```

### Communication Patterns and Trust Boundaries

Each service has strictly scoped access:

```
+------------------+     +------------------+     +------------------+
|   API Gateway    |     |  Order Service   |     | Payment Service  |
|                  |     |                  |     |                  |
|  Can talk to:    |     |  Can talk to:    |     |  Can talk to:    |
|  - order-svc     |     |  - inventory-svc |     |  - (nothing)     |
|  - inventory-svc |     |  - payment-svc   |     |                  |
|  - payment-svc   |     |                  |     |  Accepts from:   |
|                  |     |  Accepts from:   |     |  - api-gateway   |
|  Accepts from:   |     |  - api-gateway   |     |  - order-svc     |
|  - OpenShift     |     |                  |     |                  |
|    Router only   |     |  RBAC:           |     |  RBAC:           |
|                  |     |  - own configmap |     |  - own secrets   |
|  RBAC:           |     |  - own secrets   |     |    only          |
|  - read services |     |                  |     |                  |
|  - read endpoints|     +------------------+     +------------------+
+------------------+

+------------------+
| Inventory Service|
|                  |
|  Can talk to:    |
|  - (nothing)     |
|                  |
|  Accepts from:   |
|  - api-gateway   |
|  - order-svc     |
|                  |
|  RBAC:           |
|  - own configmap |
+------------------+
```

### Defense in Depth: The Security Layers

This deployment implements five overlapping security layers:

1. **SCC (restricted)** -- pods cannot run as root, cannot escalate privileges, drop all capabilities.
2. **RBAC** -- each service has its own ServiceAccount with minimal permissions. No shared identity.
3. **Network Policies** -- default deny-all, explicit allow per service pair. Prometheus scraping allowed from `openshift-user-workload-monitoring` namespace only.
4. **mTLS (Istio)** -- all inter-service traffic encrypted and mutually authenticated. STRICT mode means plaintext connections are rejected.
5. **Route TLS** -- external traffic is edge-terminated TLS with automatic certificate management.

### Circuit Breaker Strategy

The DestinationRules implement different circuit breaker policies per service based on business criticality:

| Service | Max Connections | Pending Requests | Retries | Ejection Trigger | Ejection Time |
|---------|:-:|:-:|:-:|---|---|
| API Gateway | 100 | 100 | 3 | 5 consecutive 5xx | 30s |
| Order Service | 50 | 50 | 3 | 3 consecutive 5xx | 30s |
| Inventory Service | 50 | 50 | 3 | 3 consecutive 5xx | 30s |
| Payment Service | 30 | 20 | **0** | 2 consecutive 5xx | 60s |

The payment service has **zero retries** and a stricter circuit breaker because payment operations are not idempotent -- retrying a payment could result in double charges.

## Step-by-Step

### Step 1: Verify Prerequisites

Confirm your cluster is ready and all required operators are installed.

```bash
# Check cluster status
oc login -u kubeadmin https://api.crc.testing:6443

# Verify operators
oc get csv -n openshift-operators | grep -E "pipeline|servicemesh"
oc get csv -n openshift-gitops | grep gitops

# Expected output (version numbers may differ):
#   openshift-pipelines-operator-rh.v1.x.x   ...   Succeeded
#   servicemeshoperator.v2.x.x               ...   Succeeded
#   openshift-gitops-operator.v1.x.x         ...   Succeeded
```

If any operator is missing, install it from OperatorHub:

```bash
# Example: install OpenShift Pipelines
oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-pipelines-operator
  namespace: openshift-operators
spec:
  channel: latest
  name: openshift-pipelines-operator-rh
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
```

### Step 2: Create the Project and Enable Monitoring

```bash
# Create the project
oc new-project capstone-microservices \
  --display-name="Capstone: Production Microservices" \
  --description="L3-M5.3 production-ready microservices capstone"

# Enable user workload monitoring (requires kubeadmin)
oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
EOF
```

In Kubernetes, you would install the entire Prometheus stack (prometheus-operator, grafana, alertmanager) and configure it yourself. In OpenShift, the monitoring stack is pre-installed -- you just enable user workload monitoring with a single ConfigMap.

### Step 3: Apply RBAC and ImageStreams

```bash
# Apply per-service RBAC
oc apply -f manifests/01-rbac.yaml

# Verify ServiceAccounts were created
oc get serviceaccounts -n capstone-microservices | grep -v default

# Apply ImageStreams
oc apply -f manifests/02-imagestreams.yaml

# Apply BuildConfigs
oc apply -f manifests/03-buildconfigs.yaml
```

Review the RBAC structure. Each service gets its own ServiceAccount with minimal permissions:

```yaml
# From manifests/01-rbac.yaml — the payment service can ONLY read its own secrets
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get"]
    resourceNames: ["payment-service-secrets"]
```

This is the principle of least privilege. If the payment service is compromised, the attacker cannot read the order service's secrets, list pods, or access the Kubernetes API beyond what is explicitly permitted.

### Step 4: Build the Microservice Images

OpenShift's built-in build system turns source code into container images without any external CI tool. The BuildConfigs use binary builds (upload source from local disk) with multi-stage Dockerfiles.

```bash
# Build each service (this takes 3-5 minutes per service)
for svc in api-gateway order-service inventory-service payment-service; do
  echo "Building ${svc}..."
  oc start-build ${svc} \
    --from-dir=app/${svc} \
    --follow \
    --wait \
    -n capstone-microservices
done

# Verify images are in the internal registry
oc get imagestreams -n capstone-microservices
```

Expected output:

```
NAME                IMAGE REPOSITORY                                                              TAGS      UPDATED
api-gateway         image-registry.openshift-image-registry.svc:5000/capstone-microservices/...   latest    ...
inventory-service   image-registry.openshift-image-registry.svc:5000/capstone-microservices/...   latest    ...
order-service       image-registry.openshift-image-registry.svc:5000/capstone-microservices/...   latest    ...
payment-service     image-registry.openshift-image-registry.svc:5000/capstone-microservices/...   latest    ...
```

> **Why UBI images?** The Dockerfiles use Red Hat Universal Base Images (UBI) instead of Alpine or Debian. UBI images are specifically designed to run on OpenShift -- they respect the non-root requirement, include proper CA certificates, and are supported by Red Hat.

### Step 5: Deploy Services

Apply the Deployments, Services, and Route:

```bash
oc apply -f manifests/04-deployments.yaml
oc apply -f manifests/05-services.yaml
oc apply -f manifests/06-route.yaml

# Watch the rollout
oc get pods -n capstone-microservices -w
```

Wait for all pods to reach `Running` state with `2/2` containers (the second container is the Istio sidecar, if the service mesh is active):

```
NAME                                 READY   STATUS    RESTARTS   AGE
api-gateway-7d8f9c6b4d-abc12        2/2     Running   0          45s
api-gateway-7d8f9c6b4d-def34        2/2     Running   0          45s
inventory-service-5f8c7d9b6e-ghi56  2/2     Running   0          42s
inventory-service-5f8c7d9b6e-jkl78  2/2     Running   0          42s
order-service-6c9d8e7f5a-mno90      2/2     Running   0          43s
order-service-6c9d8e7f5a-pqr12      2/2     Running   0          43s
payment-service-4b7a6c5d3e-stu34    2/2     Running   0          41s
payment-service-4b7a6c5d3e-vwx56    2/2     Running   0          41s
```

> **Without service mesh:** If the Service Mesh operator is not installed, pods will show `1/1` containers (no sidecar). The application still works; you just will not have mTLS or traffic management.

Examine the key production properties in the Deployment spec:

```yaml
# From manifests/04-deployments.yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1       # Add one new pod before removing old ones
      maxUnavailable: 0  # Never reduce below desired count during rollout
  template:
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname  # Spread across nodes
          whenUnsatisfiable: ScheduleAnyway
      securityContext:
        runAsNonRoot: true  # SCC enforcement
      containers:
        - resources:
            requests:        # Scheduling guarantees
              cpu: 100m
              memory: 128Mi
            limits:          # Hard ceilings
              cpu: 500m
              memory: 256Mi
          startupProbe: ...   # Separate from liveness — allows slow starts
          livenessProbe: ...  # Kills unhealthy containers
          readinessProbe: ... # Removes from Service endpoints when unhealthy
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
            seccompProfile:
              type: RuntimeDefault
```

### Step 6: Apply Network Policies

Network policies enforce microsegmentation -- each service can only communicate with the services it legitimately needs.

```bash
oc apply -f manifests/07-network-policies.yaml

# List all network policies
oc get networkpolicies -n capstone-microservices
```

Expected output:

```
NAME                              POD-SELECTOR           AGE
allow-api-gateway-egress          app=api-gateway        5s
allow-api-gateway-ingress         app=api-gateway        5s
allow-inventory-service-egress    app=inventory-service  5s
allow-inventory-service-ingress   app=inventory-service  5s
allow-order-service-egress        app=order-service      5s
allow-order-service-ingress       app=order-service      5s
allow-payment-service-egress      app=payment-service    5s
allow-payment-service-ingress     app=payment-service    5s
allow-prometheus-scrape           <none>                 5s
default-deny-egress               <none>                 5s
default-deny-ingress              <none>                 5s
```

The strategy is **default deny, explicit allow**:

1. `default-deny-ingress` and `default-deny-egress` block everything.
2. Per-service policies open only the specific connections needed.
3. `allow-prometheus-scrape` allows the monitoring namespace to reach `/metrics` on all pods.

Test that the network policies are working:

```bash
# This should work — API gateway can reach order service
oc exec deploy/api-gateway -n capstone-microservices -- \
  curl -s http://order-service:8080/healthz

# This should fail — inventory service cannot reach payment service
oc exec deploy/inventory-service -n capstone-microservices -- \
  curl -s --connect-timeout 3 http://payment-service:8080/healthz
# Expected: connection timeout (blocked by NetworkPolicy)
```

### Step 7: Configure the Service Mesh

Apply the service mesh configuration for mTLS, circuit breaking, and traffic management:

```bash
oc apply -f manifests/10-service-mesh.yaml

# Verify the namespace is enrolled in the mesh
oc get servicemeshmember -n capstone-microservices
```

Verify mTLS is active:

```bash
# Check if Istio sidecars are injected (look for 2/2 READY)
oc get pods -n capstone-microservices

# Verify PeerAuthentication
oc get peerauthentication -n capstone-microservices
```

Open Kiali to visualize the service mesh topology:

```bash
# Get the Kiali URL
oc get route kiali -n istio-system -o jsonpath='{.spec.host}'
```

Navigate to the Kiali dashboard and select the `capstone-microservices` namespace. You should see the traffic flow between services with padlock icons indicating mTLS is active.

### Step 8: Set Up Monitoring and Alerting

```bash
oc apply -f manifests/09-monitoring.yaml

# Verify ServiceMonitors are created
oc get servicemonitors -n capstone-microservices

# Verify PrometheusRules
oc get prometheusrules -n capstone-microservices
```

The monitoring configuration includes:

- **ServiceMonitors** for each microservice -- Prometheus scrapes `/metrics` every 15 seconds
- **PrometheusRules** with six alert rules:
  - `HighErrorRate` -- API gateway returning >5% errors
  - `SlowOrderProcessing` -- P99 order latency > 2 seconds
  - `HighPaymentFailureRate` -- Payment declines > 10%
  - `LowInventoryStock` -- Product stock below 10 units
  - `PodRestartingFrequently` -- Container restarts > 3 per hour
  - `HPAMaxedOut` -- Autoscaler at maximum replicas for 15 minutes

Check that Prometheus is scraping the services:

```bash
# Port-forward to Prometheus (or use the Web Console Monitoring tab)
# Navigate to: Monitoring -> Metrics in the Web Console

# Query custom metrics in the Web Console:
#   api_gateway_http_requests_total
#   order_service_orders_created_total
#   inventory_service_stock_level
#   payment_service_payments_processed_total
```

### Step 9: Configure Autoscaling

```bash
oc apply -f manifests/08-hpa.yaml
oc apply -f manifests/14-pod-disruption-budgets.yaml
oc apply -f manifests/11-resource-quotas.yaml

# Check HPA status
oc get hpa -n capstone-microservices
```

Expected output:

```
NAME                   REFERENCE                     TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
api-gateway-hpa        Deployment/api-gateway        10%/70%   2         8         2          30s
inventory-service-hpa  Deployment/inventory-service  8%/70%    2         6         2          30s
order-service-hpa      Deployment/order-service      12%/70%   2         10        2          30s
payment-service-hpa    Deployment/payment-service    9%/70%    2         6         2          30s
```

The HPA configuration includes stabilization windows to prevent flapping:

```yaml
behavior:
  scaleUp:
    stabilizationWindowSeconds: 60    # Wait 60s before scaling up
    policies:
      - type: Pods
        value: 2                       # Add at most 2 pods at a time
        periodSeconds: 60
  scaleDown:
    stabilizationWindowSeconds: 300   # Wait 5 min before scaling down
    policies:
      - type: Pods
        value: 1                       # Remove at most 1 pod at a time
        periodSeconds: 120
```

The asymmetric scaling (fast up, slow down) is intentional -- in production, you want to respond quickly to load spikes but avoid premature scale-down that could cause thrashing.

### Step 10: Set Up the Tekton CI/CD Pipeline

```bash
oc apply -f manifests/12-tekton-pipeline.yaml

# Verify the pipeline was created
oc get pipelines -n capstone-microservices
oc get tasks -n capstone-microservices
```

Trigger a pipeline run:

```bash
# Create a PersistentVolumeClaim for the pipeline workspace
oc apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pipeline-workspace
  namespace: capstone-microservices
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF

# Start a pipeline run (for manual builds — in production, this is triggered by webhooks)
tkn pipeline start build-and-deploy-all \
  -n capstone-microservices \
  -w name=shared-workspace,claimName=pipeline-workspace \
  -p git-url=https://github.com/your-org/capstone-microservices.git \
  -p git-revision=main \
  --showlog
```

View the pipeline run in the Web Console: **Pipelines -> Pipeline Runs**.

### Step 11: Configure ArgoCD GitOps (Optional)

> **Note:** This step requires your manifests to be in a Git repository. If you are working locally with CRC, you can skip this step and apply manifests directly with `oc apply`.

```bash
# Apply the ArgoCD Application
oc apply -f manifests/13-argocd-application.yaml

# Check sync status
oc get application capstone-microservices -n openshift-gitops
```

Access the ArgoCD dashboard:

```bash
# Get the ArgoCD URL
oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}'

# Get the admin password
oc extract secret/openshift-gitops-cluster -n openshift-gitops --to=-
```

The ArgoCD Application is configured with:

- **`selfHeal: true`** -- if someone makes a manual `oc edit` change, ArgoCD reverts it to match Git.
- **`prune: true`** -- if a manifest is removed from Git, the corresponding resource is deleted from the cluster.
- **`ignoreDifferences`** -- excludes fields that legitimately change at runtime (Route host, HPA-managed replica count).

### Step 12: Run Load Tests and Observe Scaling

Use the included load test script to generate traffic and trigger autoscaling:

```bash
# Run load test for 60 seconds with 10 concurrent workers
./scripts/03-load-test.sh 60 10

# In a separate terminal, watch the HPA react
oc get hpa -n capstone-microservices -w

# Watch pods scale
oc get pods -n capstone-microservices -w
```

While the load test runs, observe:

1. **Web Console -> Monitoring -> Metrics**: Query `rate(api_gateway_http_requests_total[1m])` to see request rate.
2. **Web Console -> Monitoring -> Alerts**: Check if any alerts are firing.
3. **Kiali**: Watch the traffic flow in the service mesh topology view.
4. **HPA**: Watch replica counts increase as CPU utilization exceeds the 70% threshold.

## Verification

Run the comprehensive verification script:

```bash
./scripts/02-verify.sh
```

This checks all 13 component categories:

1. Project exists
2. All Deployments have desired replicas ready
3. All Services exist
4. Route responds with HTTP 200
5. Per-service ServiceAccounts exist
6. NetworkPolicies are applied (>= 8 policies)
7. HPAs are configured for all services
8. ServiceMonitors are scraping metrics
9. PrometheusRules (alerting) are defined
10. PodDisruptionBudgets are in place
11. Service mesh enrollment and mTLS
12. Tekton pipeline exists
13. ResourceQuota and LimitRange are applied

Manual verification:

```bash
# Check all pods are running
oc get pods -n capstone-microservices

# Test the API gateway
ROUTE=$(oc get route api-gateway -n capstone-microservices -o jsonpath='{.spec.host}')
curl -sk https://${ROUTE}/healthz | python3 -m json.tool

# Test inter-service communication
curl -sk https://${ROUTE}/api/inventory | python3 -m json.tool
curl -sk -X POST https://${ROUTE}/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"widget-a","quantity":2}' | python3 -m json.tool

# Verify metrics are being scraped
curl -sk https://${ROUTE}/metrics | head -20

# Check resource quota usage
oc describe resourcequota capstone-compute-quota -n capstone-microservices
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| **Container builds** | External CI (Jenkins, GitHub Actions) pushes to external registry | Built-in BuildConfig with S2I/Docker strategy, internal registry, ImageStreams |
| **CI/CD pipelines** | Install Tekton or Argo Workflows manually | OpenShift Pipelines operator -- one-click install, integrated in Web Console |
| **GitOps** | Install ArgoCD via Helm, manage upgrades | OpenShift GitOps operator -- managed lifecycle, SSO with OpenShift OAuth |
| **Service mesh** | Install Istio manually, manage upgrades and CRDs | Service Mesh operator -- managed, includes Kiali and Jaeger, Maistra distribution |
| **Monitoring** | Install kube-prometheus-stack, configure scrape targets in `prometheus.yml` | Pre-installed, enable user workload monitoring with one ConfigMap, use ServiceMonitor CRDs |
| **Alerting** | Configure AlertManager rules in Helm values or raw config | PrometheusRule CRDs, viewable in Web Console Alerts tab |
| **Ingress/routing** | Install ingress controller, create Ingress resources | Pre-installed HAProxy router, Route CRDs with built-in TLS termination modes |
| **Pod security** | Install PSA/OPA Gatekeeper, configure policies | SCCs enforced by default -- `restricted` SCC blocks root, privilege escalation |
| **Network policies** | Requires CNI that supports NetworkPolicy (Calico, Cilium) | OVN-Kubernetes built-in, NetworkPolicy supported out of the box |
| **Autoscaling** | Install Metrics Server manually for HPA | Metrics Server pre-installed, HPA works immediately |
| **Container images** | Any base image (Alpine, Ubuntu, scratch) | UBI (Universal Base Image) recommended -- SCC-compatible, Red Hat-supported |
| **Developer experience** | `kubectl apply` and dashboards | Topology view, integrated pipeline visualization, in-console terminal, build logs |

## Key Takeaways

- **OpenShift is a platform, not just an orchestrator.** Where Kubernetes gives you primitives and says "assemble it yourself," OpenShift provides pre-integrated operators for CI/CD, GitOps, service mesh, monitoring, and security that work together out of the box. This capstone required installing zero additional Helm charts or manual tool configuration.

- **Defense in depth is achievable without bolt-on tools.** Five security layers (SCCs, per-service RBAC, network policies, mTLS, Route TLS) were configured entirely through platform-native resources. In vanilla Kubernetes, achieving the same posture requires installing and configuring Istio, OPA Gatekeeper, a network policy-capable CNI, and cert-manager independently.

- **Production readiness is about the operational properties, not just the application code.** The manifests in this lesson add resource limits, topology spread, PodDisruptionBudgets, startup/liveness/readiness probes, HPA scaling policies with stabilization windows, circuit breakers with per-service tuning, and comprehensive alerting rules. These are what keep a service running reliably under real-world conditions.

- **GitOps and CI/CD integration is seamless.** The Tekton-builds-images-then-ArgoCD-syncs-cluster pattern (L2-M1.4) requires no custom glue code on OpenShift. BuildConfigs push to ImageStreams, pipelines trigger rollouts, and ArgoCD watches Git for manifest changes. The full loop is declarative end to end.

- **Circuit breakers and retry policies must be tuned per service.** Not every service should have the same fault tolerance configuration. Payment processing with zero retries (idempotency protection) versus order service with three retries (safe to retry reads) demonstrates that production service mesh configuration requires understanding the business semantics of each service.

## Failure Modes and Recovery

### Scenario 1: A Pod Keeps Crashing (CrashLoopBackOff)

**Symptom:** `oc get pods` shows `CrashLoopBackOff` for a service.

**Diagnosis:**

```bash
# Check logs from the crashed container
oc logs deploy/order-service -n capstone-microservices --previous

# Check events for the namespace
oc get events -n capstone-microservices --sort-by='.lastTimestamp' | tail -20

# Debug with a temporary container
oc debug deploy/order-service -n capstone-microservices
```

**Common causes:**
- OOMKilled -- increase memory limits in the Deployment
- SCC violation -- check if the image tries to run as root or bind to port < 1024
- Missing environment variable -- check ConfigMaps and Secrets

**Recovery:** Fix the root cause, then `oc rollout restart deployment/order-service`.

### Scenario 2: Circuit Breaker Trips (503 Service Unavailable)

**Symptom:** API gateway returns 503 errors. Kiali shows red edges in the topology.

**Diagnosis:**

```bash
# Check if the upstream service is healthy
oc get pods -l app=payment-service -n capstone-microservices

# Check Istio proxy logs for circuit breaker events
oc logs deploy/api-gateway -c istio-proxy -n capstone-microservices | grep "overflow"

# Check DestinationRule configuration
oc get destinationrule payment-service-dr -n capstone-microservices -o yaml
```

**Recovery:** The circuit breaker auto-recovers after the `baseEjectionTime` (30-60s depending on the service). If the underlying service is genuinely unhealthy, fix it first. The circuit breaker protects the rest of the system from cascading failures while you do so.

### Scenario 3: HPA Maxed Out and Service is Still Slow

**Symptom:** `oc get hpa` shows current replicas equals max replicas. Response times are still high.

**Diagnosis:**

```bash
# Check HPA status
oc describe hpa order-service-hpa -n capstone-microservices

# Check resource usage
oc adm top pods -n capstone-microservices

# Check if ResourceQuota is the bottleneck
oc describe resourcequota capstone-compute-quota -n capstone-microservices
```

**Recovery:**
1. Increase `maxReplicas` in the HPA if the node has capacity.
2. Increase the ResourceQuota if it is the bottleneck.
3. If nodes are full, add worker nodes (L3-M1.3) or optimize the service code.

### Scenario 4: Network Policy Blocks Legitimate Traffic

**Symptom:** Service A cannot reach Service B, connection times out.

**Diagnosis:**

```bash
# List network policies affecting a pod
oc get networkpolicies -n capstone-microservices

# Test connectivity from inside a pod
oc exec deploy/api-gateway -n capstone-microservices -- \
  curl -s --connect-timeout 3 http://order-service:8080/healthz

# Check if the labels match the policy selectors
oc get pods -l app=order-service -n capstone-microservices --show-labels
```

**Recovery:** Add or modify the relevant NetworkPolicy to allow the connection. Ensure pod labels match the policy's `podSelector`.

### Scenario 5: Node Drain During Cluster Upgrade

**Symptom:** During a cluster upgrade, pods are evicted from a node.

**What should happen:** PodDisruptionBudgets ensure at least 1 replica of each service stays running. The drain process waits for new pods to become ready before evicting more.

```bash
# Simulate a drain (test your PDBs)
oc adm drain <node-name> --ignore-daemonsets --delete-emptydir-data --dry-run=server
```

**If PDBs block the drain for too long:** Check if pods are stuck in `Pending` (insufficient resources on remaining nodes) or if they have `terminationGracePeriodSeconds` set too high.

## Cleanup

Run the cleanup script to remove all resources:

```bash
./scripts/04-cleanup.sh
```

Or manually:

```bash
# Remove ArgoCD Application (if created)
oc delete application capstone-microservices -n openshift-gitops --ignore-not-found=true

# Remove Service Mesh membership
oc delete servicemeshmember default -n capstone-microservices --ignore-not-found=true

# Delete the entire project (removes all namespaced resources)
oc delete project capstone-microservices

# Verify cleanup
oc get project capstone-microservices
# Expected: Error from server (NotFound): namespaces "capstone-microservices" not found
```

Alternatively, use the tutorial labels for selective cleanup:

```bash
oc delete all -l tutorial-level=3,tutorial-module=M5 -n capstone-microservices
```

## Next Steps

In **L3-M5.4 -- Capstone: Multi-Cluster Platform**, you will take the microservices application from this lesson and deploy it across multiple clusters using Red Hat Advanced Cluster Management (RHACM). You will configure centralized policy governance, multi-cluster observability, and ApplicationSets in ArgoCD for automated multi-cluster deployment -- the final step toward a fully production enterprise platform.
