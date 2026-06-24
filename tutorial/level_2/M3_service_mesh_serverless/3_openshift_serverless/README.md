# L2-M3.3 — OpenShift Serverless (Knative)

**Level:** Practitioner
**Duration:** 1 hr

## Overview

In Kubernetes, running serverless workloads means installing and managing Knative yourself, configuring an ingress layer, and wiring up autoscaling. OpenShift Serverless wraps Knative Serving and Knative Eventing into fully supported operators that integrate with the platform's routing, monitoring, and security model out of the box. In this lesson you will install the OpenShift Serverless operator, deploy Knative Services that scale to zero, manage revisions with traffic splitting, and use the `kn` CLI to streamline the workflow.

## Prerequisites

- Level 1 completed (all modules)
- L2-M3.1 (OpenShift Service Mesh) completed — familiarity with operator installation patterns
- OpenShift cluster running (CRC with at least 4 CPUs and 16 GB RAM, or Developer Sandbox)
- Logged in as `kubeadmin` for operator installation, `developer` for workload deployment
- `kn` CLI installed ([download from the OpenShift Web Console or mirror.openshift.com](https://mirror.openshift.com/pub/openshift-v4/clients/serverless/))

## K8s Context

You already know how to deploy long-running workloads with Deployments and expose them through Services and Ingress. When demand fluctuates, you use a Horizontal Pod Autoscaler (HPA) to scale between a minimum and maximum replica count. But a standard HPA has hard limits:

- **No scale-to-zero** — you always pay for at least one running pod, even with zero traffic.
- **Manual configuration** — you wire up the HPA, define metrics, choose target utilization, and maintain it.
- **No built-in traffic splitting** — canary or blue-green releases require Ingress rewrites, service mesh rules, or manual Service label shuffling.
- **No revision model** — rolling updates replace pods in place; there is no first-class concept of "revision v1 vs v2" with independent scaling.

Knative Serving solves all of these. Knative Eventing (covered more deeply in L2-M3.4) adds event-driven glue. On vanilla Kubernetes you install Knative yourself; on OpenShift the Serverless operator handles installation, upgrades, and integration.

## Concepts

### Knative Serving — Core Resources

| Resource | Purpose |
|----------|---------|
| **Knative Service (ksvc)** | The top-level abstraction. Defines the container, environment, scaling parameters. Automatically creates Routes, Configurations, and Revisions. |
| **Configuration** | Tracks the desired state of the workload (container image, env, resources). Each update creates a new Revision. |
| **Revision** | An immutable, point-in-time snapshot of a Configuration. Think of it as a versioned Deployment that can independently scale, including to zero. |
| **Route** | Splits traffic across Revisions. This is a Knative Route (not an OpenShift Route), but OpenShift Serverless creates the corresponding OpenShift Route automatically. |

### Scale-to-Zero

Knative's autoscaler (KPA — Knative Pod Autoscaler) monitors concurrency or requests-per-second. When traffic drops to zero, it scales the Revision to zero pods. When a new request arrives, the activator component holds it briefly while a pod starts (cold start). This is the defining feature that separates Knative from a standard HPA.

Key autoscaling annotations:

| Annotation | Default | Description |
|------------|---------|-------------|
| `autoscaling.knative.dev/minScale` | `0` | Minimum replicas (set to `1` to disable scale-to-zero) |
| `autoscaling.knative.dev/maxScale` | `0` (unlimited) | Maximum replicas |
| `autoscaling.knative.dev/target` | `100` | Concurrent requests per pod (soft target) |
| `autoscaling.knative.dev/class` | `kpa.autoscaling.knative.dev` | Autoscaler class (`kpa` or `hpa`) |
| `autoscaling.knative.dev/metric` | `concurrency` | Metric for scaling (`concurrency` or `rps`) |
| `autoscaling.knative.dev/window` | `60s` | Stable window before scaling down |

### Revisions and Traffic Splitting

Every change to a Knative Service's `spec.template` creates a new Revision. The `spec.traffic` block controls how traffic is distributed across Revisions — enabling canary, blue-green, or gradual rollout patterns without any service mesh or ingress controller configuration.

### The `kn` CLI

The `kn` CLI is to Knative what `oc` is to OpenShift — a purpose-built tool that simplifies creating and managing Knative resources. While you can always use `oc apply -f`, `kn` provides concise imperative commands for rapid iteration.

### OpenShift Integration

OpenShift Serverless adds several platform-level integrations:

- **Automatic OpenShift Routes** — every Knative Service gets a URL via the OpenShift router, not a separate Ingress gateway.
- **SCC compatibility** — Knative components run under appropriate SCCs.
- **Monitoring** — Knative metrics flow into the built-in Prometheus stack.
- **Web Console** — Serverless workloads appear in the Developer perspective's Topology view with scale-to-zero indicators.

## Step-by-Step

### Step 1: Install the OpenShift Serverless Operator

Log in as `kubeadmin` to install the operator cluster-wide.

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

Create the operator namespace and install the Subscription:

```bash
oc apply -f manifests/serverless-operator-subscription.yaml
```

```yaml
# manifests/serverless-operator-subscription.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-serverless
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: serverless-operators
  namespace: openshift-serverless
spec: {}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: serverless-operator
  namespace: openshift-serverless
spec:
  channel: stable
  installPlanApproval: Automatic
  name: serverless-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

Wait for the operator to become available:

```bash
oc get csv -n openshift-serverless -w
```

Expected output (after 2-3 minutes):

```
NAME                          DISPLAY                     VERSION   PHASE
serverless-operator.v1.33.0   Red Hat OpenShift Serverless 1.33.0   Succeeded
```

> **Tip:** On CRC the installation may take several minutes due to limited resources. If the CSV stays in `Installing` for more than 5 minutes, check events: `oc get events -n openshift-serverless --sort-by='.lastTimestamp'`.

### Step 2: Install Knative Serving

With the operator running, create the KnativeServing instance to deploy the Serving control plane:

```bash
oc apply -f manifests/knative-serving.yaml
```

```yaml
# manifests/knative-serving.yaml
apiVersion: operator.knative.dev/v1beta1
kind: KnativeServing
metadata:
  name: knative-serving
  namespace: knative-serving
spec:
  ingress:
    kourier:
      enabled: false
  config:
    network:
      ingress-class: kourier.ingress.networking.knative.dev
```

> **Note:** On OpenShift, the Serverless operator automatically creates the `knative-serving` namespace and configures the OpenShift ingress integration. The manifest above uses the defaults; the operator handles the rest.

Verify the Serving components are ready:

```bash
oc get knativeserving knative-serving -n knative-serving
```

Expected output:

```
NAME              VERSION   READY   REASON
knative-serving   1.12      True
```

Check that all pods are running:

```bash
oc get pods -n knative-serving
```

You should see pods for `activator`, `autoscaler`, `controller`, `webhook`, and networking components, all in `Running` state.

### Step 3: Install Knative Eventing

Install the Eventing control plane for event-driven workloads (we will use it more in L2-M3.4, but installing it now prepares the cluster):

```bash
oc apply -f manifests/knative-eventing.yaml
```

```yaml
# manifests/knative-eventing.yaml
apiVersion: operator.knative.dev/v1beta1
kind: KnativeEventing
metadata:
  name: knative-eventing
  namespace: knative-eventing
```

Verify:

```bash
oc get knativeeventing knative-eventing -n knative-eventing
```

Expected output:

```
NAME               VERSION   READY   REASON
knative-eventing   1.12      True
```

### Step 4: Create a Project and Deploy Your First Knative Service

Switch to the `developer` user and create a project:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc new-project serverless-tutorial
```

Deploy a simple Knative Service using a manifest:

```bash
oc apply -f manifests/hello-ksvc.yaml
```

```yaml
# manifests/hello-ksvc.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: hello
  namespace: serverless-tutorial
  labels:
    app: hello
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  template:
    metadata:
      labels:
        app: hello
        tutorial-level: "2"
        tutorial-module: "M3"
      annotations:
        autoscaling.knative.dev/target: "10"
        autoscaling.knative.dev/minScale: "0"
        autoscaling.knative.dev/maxScale: "5"
    spec:
      containers:
        - image: gcr.io/knative-samples/helloworld-go
          ports:
            - containerPort: 8080
          env:
            - name: TARGET
              value: "OpenShift Serverless v1"
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
```

Alternatively, use the `kn` CLI for the same result:

```bash
kn service create hello \
  --image gcr.io/knative-samples/helloworld-go \
  --port 8080 \
  --env TARGET="OpenShift Serverless v1" \
  --annotation autoscaling.knative.dev/target=10 \
  --annotation autoscaling.knative.dev/minScale=0 \
  --annotation autoscaling.knative.dev/maxScale=5 \
  --request cpu=50m,memory=64Mi \
  --limit cpu=200m,memory=128Mi
```

Expected output:

```
Creating service 'hello' in namespace 'serverless-tutorial':

  0.034s The Configuration is still working to reflect the latest desired specification.
  3.234s Traffic is not yet migrated to the latest revision.
  3.278s Ingress has not yet been reconciled.
  3.355s Waiting for load balancer to be ready
  4.587s Ready to serve.

Service 'hello' created to latest revision 'hello-00001' is available at URL:
http://hello-serverless-tutorial.apps-crc.testing
```

### Step 5: Test the Service and Observe Scale-to-Zero

Get the service URL:

```bash
kn service list
```

Expected output:

```
NAME    URL                                                 LATEST        AGE   CONDITIONS   READY
hello   http://hello-serverless-tutorial.apps-crc.testing   hello-00001   30s   3 OK / 3     True
```

Send a request:

```bash
curl http://hello-serverless-tutorial.apps-crc.testing
```

Expected output:

```
Hello OpenShift Serverless v1!
```

Now watch the pods. After roughly 60 seconds of inactivity, the pod scales to zero:

```bash
oc get pods -n serverless-tutorial -w
```

Expected behavior:

```
NAME                                      READY   STATUS    RESTARTS   AGE
hello-00001-deployment-7f8b6c5d9f-x2k4j  2/2     Running   0          45s
hello-00001-deployment-7f8b6c5d9f-x2k4j  2/2     Terminating   0      90s
hello-00001-deployment-7f8b6c5d9f-x2k4j  0/2     Terminating   0      92s
```

After termination, running `oc get pods` returns no pods. Send another request and watch a pod spin up (cold start):

```bash
# In one terminal, watch pods
oc get pods -n serverless-tutorial -w

# In another terminal, send a request
curl http://hello-serverless-tutorial.apps-crc.testing
```

The cold start typically takes 2-5 seconds on CRC.

### Step 6: Explore Revisions

List the current revisions:

```bash
kn revision list
```

Expected output:

```
NAME          SERVICE   TRAFFIC   TAGS   GENERATION   AGE   CONDITIONS   READY
hello-00001   hello     100%             1            5m    4 OK / 4     True
```

Now update the service to create a new revision:

```bash
kn service update hello --env TARGET="OpenShift Serverless v2"
```

Expected output:

```
Updating Service 'hello' in namespace 'serverless-tutorial':

  0.029s The Configuration is still working to reflect the latest desired specification.
  3.412s Traffic is not yet migrated to the latest revision.
  3.550s Ingress has not yet been reconciled.
  3.712s Ready to serve.

Service 'hello' updated to latest revision 'hello-00002' is available at URL:
http://hello-serverless-tutorial.apps-crc.testing
```

List revisions again:

```bash
kn revision list
```

Expected output:

```
NAME          SERVICE   TRAFFIC   TAGS   GENERATION   AGE   CONDITIONS   READY
hello-00002   hello     100%             2            15s   4 OK / 4     True
hello-00001   hello                      1            6m    4 OK / 4     True
```

Notice that 100% of traffic now goes to `hello-00002`. The old revision `hello-00001` still exists and can be targeted for traffic splitting.

Test the update:

```bash
curl http://hello-serverless-tutorial.apps-crc.testing
```

Expected output:

```
Hello OpenShift Serverless v2!
```

### Step 7: Traffic Splitting Between Revisions

Split traffic 80/20 between the new and old revisions — a canary deployment pattern:

```bash
kn service update hello \
  --traffic hello-00002=80 \
  --traffic hello-00001=20
```

Alternatively, apply the declarative manifest:

```bash
oc apply -f manifests/hello-ksvc-traffic-split.yaml
```

```yaml
# manifests/hello-ksvc-traffic-split.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: hello
  namespace: serverless-tutorial
  labels:
    app: hello
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  template:
    metadata:
      labels:
        app: hello
        tutorial-level: "2"
        tutorial-module: "M3"
      annotations:
        autoscaling.knative.dev/target: "10"
        autoscaling.knative.dev/minScale: "0"
        autoscaling.knative.dev/maxScale: "5"
    spec:
      containers:
        - image: gcr.io/knative-samples/helloworld-go
          ports:
            - containerPort: 8080
          env:
            - name: TARGET
              value: "OpenShift Serverless v2"
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
  traffic:
    - revisionName: hello-00002
      percent: 80
    - revisionName: hello-00001
      percent: 20
```

Verify the traffic split:

```bash
kn service describe hello
```

Expected output (partial):

```
Name:       hello
Namespace:  serverless-tutorial
URL:        http://hello-serverless-tutorial.apps-crc.testing

Traffic Targets:
   80%  hello-00002
   20%  hello-00001
```

Test by sending multiple requests:

```bash
for i in $(seq 1 20); do
  curl -s http://hello-serverless-tutorial.apps-crc.testing
done
```

You should see roughly 16 responses with "v2" and 4 with "v1" (80/20 split).

### Step 8: Tag Revisions for Direct Access

Tags create named URLs for specific revisions, useful for testing a canary revision directly before routing production traffic:

```bash
kn service update hello \
  --tag hello-00001=v1 \
  --tag hello-00002=v2
```

Each tagged revision gets its own URL:

```bash
kn service describe hello
```

Expected output (partial):

```
Traffic Targets:
   80%  @v2 (hello-00002)
        http://v2-hello-serverless-tutorial.apps-crc.testing
   20%  @v1 (hello-00001)
        http://v1-hello-serverless-tutorial.apps-crc.testing
```

Test the tagged URLs directly:

```bash
curl http://v1-hello-serverless-tutorial.apps-crc.testing
# Hello OpenShift Serverless v1!

curl http://v2-hello-serverless-tutorial.apps-crc.testing
# Hello OpenShift Serverless v2!
```

### Step 9: Deploy a Production-Style Knative Service

Deploy a more realistic service with probes, concurrency limits, and scaling parameters:

```bash
oc apply -f manifests/production-ksvc.yaml
```

```yaml
# manifests/production-ksvc.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: web-api
  namespace: serverless-tutorial
  labels:
    app: web-api
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  template:
    metadata:
      labels:
        app: web-api
        tutorial-level: "2"
        tutorial-module: "M3"
      annotations:
        autoscaling.knative.dev/target: "50"
        autoscaling.knative.dev/minScale: "1"
        autoscaling.knative.dev/maxScale: "10"
        autoscaling.knative.dev/window: "30s"
        autoscaling.knative.dev/metric: "concurrency"
    spec:
      containerConcurrency: 100
      timeoutSeconds: 30
      containers:
        - image: gcr.io/knative-samples/helloworld-go
          ports:
            - containerPort: 8080
          env:
            - name: TARGET
              value: "Production API"
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
          readinessProbe:
            httpGet:
              path: /
              port: 8080
            initialDelaySeconds: 1
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
```

Key production settings:
- **`minScale: "1"`** — always keep at least one pod running, eliminating cold starts for latency-sensitive APIs.
- **`maxScale: "10"`** — cap scaling to control resource usage.
- **`containerConcurrency: 100`** — hard limit on concurrent requests per container.
- **`target: "50"`** — soft target; the autoscaler adds pods when concurrency exceeds 50.
- **`window: "30s"`** — shorter stabilization window for faster scale-down.
- **Resource requests/limits** — sized for actual workload needs.
- **Probes** — readiness and liveness probes for health monitoring.

Verify:

```bash
kn service list
```

Expected output:

```
NAME      URL                                                    LATEST         AGE   CONDITIONS   READY
hello     http://hello-serverless-tutorial.apps-crc.testing      hello-00002    10m   3 OK / 3     True
web-api   http://web-api-serverless-tutorial.apps-crc.testing    web-api-00001  30s   3 OK / 3     True
```

### Step 10: Compare with Standard Deployment + HPA

For comparison, here is the equivalent setup using a standard Kubernetes Deployment and HPA:

```bash
oc apply -f manifests/k8s-deployment-hpa.yaml
```

```yaml
# manifests/k8s-deployment-hpa.yaml
# Standard Kubernetes approach — Deployment + Service + HPA
# Compare with production-ksvc.yaml for the Knative equivalent
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-api-traditional
  namespace: serverless-tutorial
  labels:
    app: web-api-traditional
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web-api-traditional
  template:
    metadata:
      labels:
        app: web-api-traditional
        tutorial-level: "2"
        tutorial-module: "M3"
    spec:
      containers:
        - name: web-api
          image: gcr.io/knative-samples/helloworld-go
          ports:
            - containerPort: 8080
          env:
            - name: TARGET
              value: "Traditional Deployment"
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
          readinessProbe:
            httpGet:
              path: /
              port: 8080
            initialDelaySeconds: 1
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: web-api-traditional
  namespace: serverless-tutorial
  labels:
    app: web-api-traditional
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  selector:
    app: web-api-traditional
  ports:
    - port: 80
      targetPort: 8080
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: web-api-traditional
  namespace: serverless-tutorial
  labels:
    app: web-api-traditional
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  to:
    kind: Service
    name: web-api-traditional
  port:
    targetPort: 8080
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: web-api-traditional
  namespace: serverless-tutorial
  labels:
    app: web-api-traditional
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web-api-traditional
  minReplicas: 1
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

Notice how the traditional approach requires four separate resources (Deployment, Service, Route, HPA), while the Knative Service is a single resource that handles all of it. The HPA also cannot scale to zero and uses CPU utilization rather than request concurrency.

## Verification

Run through this checklist to confirm everything is working:

```bash
# 1. Operator is running
oc get csv -n openshift-serverless | grep -i serverless

# 2. Knative Serving is ready
oc get knativeserving -n knative-serving

# 3. Knative Eventing is ready
oc get knativeeventing -n knative-eventing

# 4. Both Knative Services are ready
kn service list -n serverless-tutorial

# 5. Revisions are available
kn revision list -n serverless-tutorial

# 6. Traffic split is configured
kn service describe hello -n serverless-tutorial | grep -A5 "Traffic"

# 7. Scale-to-zero works (wait ~60s after last request to hello)
oc get pods -n serverless-tutorial -l serving.knative.dev/service=hello

# 8. Cold start works
curl http://hello-serverless-tutorial.apps-crc.testing

# 9. Traditional deployment is running for comparison
oc get deployment web-api-traditional -n serverless-tutorial
oc get hpa web-api-traditional -n serverless-tutorial
```

You can also verify in the **Web Console**: navigate to the Developer perspective, select the `serverless-tutorial` project, and open the Topology view. Knative Services appear with a special icon and show their scaling status (including "Scaled to 0").

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| **Knative installation** | Install Knative CRDs, controller, networking layer (Istio/Kourier/Contour) manually | Install OpenShift Serverless operator from OperatorHub; it handles everything |
| **Ingress for serverless** | Configure Istio gateway or Kourier separately | Automatic OpenShift Route creation for every Knative Service |
| **Scale-to-zero** | Not possible with HPA alone; requires Knative or KEDA | Built into Knative Serving via the operator |
| **Autoscaling metric** | HPA uses CPU/memory utilization | Knative uses request concurrency or RPS (more meaningful for HTTP workloads) |
| **Revisions** | No native concept; rolling update replaces pods in place | Immutable Revisions with independent scaling and traffic routing |
| **Traffic splitting** | Requires Ingress annotations, service mesh, or manual Service changes | Declarative `spec.traffic` block on the Knative Service |
| **CLI** | `kubectl` only | `kn` CLI for fast iteration, plus `oc`/`kubectl` for YAML-based workflows |
| **Resources needed** | Deployment + Service + Ingress + HPA = 4 resources | Knative Service = 1 resource (auto-creates Route, Configuration, Revision) |
| **Monitoring** | Install and configure Prometheus for Knative metrics | Metrics flow into built-in OpenShift monitoring stack |
| **Web Console** | No Knative-aware UI | Topology view shows serverless workloads with scale-to-zero indicators |
| **Upgrades** | Manual Knative version management | Operator manages upgrades through OLM |

## Key Takeaways

- **OpenShift Serverless is managed Knative** — the operator handles installation, configuration, and upgrades of Knative Serving and Eventing, removing significant operational overhead compared to vanilla Kubernetes.
- **Scale-to-zero is the defining capability** — unlike HPA, Knative can reduce replicas to zero pods when there is no traffic, saving resources for bursty or low-traffic workloads. Set `minScale: "1"` for latency-sensitive services that cannot tolerate cold starts.
- **Revisions provide immutable deployment snapshots** — every change to a Knative Service creates a new Revision. Traffic can be split declaratively across Revisions, enabling canary deployments without a service mesh or complex Ingress rules.
- **One resource replaces four** — a single Knative Service (ksvc) replaces the Deployment + Service + Route + HPA combination, reducing configuration surface and potential for drift.
- **Use `kn` for fast iteration, YAML for GitOps** — the `kn` CLI excels at rapid development workflows; for production GitOps pipelines, commit Knative Service manifests to Git and let ArgoCD sync them (as covered in L2-M1.3).

## Troubleshooting

### Knative Service stuck in "NotReady"

```bash
kn service describe <name> -n serverless-tutorial
oc get ksvc <name> -n serverless-tutorial -o yaml | grep -A10 "status:"
```

Common causes:
- **Image pull error** — verify the image exists and is accessible. On CRC, external registries may be slow.
- **SCC violation** — if the container image requires root, you will see pod creation failures. Use images built for non-root (UBI-based images work well).
- **Resource pressure** — CRC has limited resources. Check `oc describe node` for memory/CPU pressure.

### Cold start is too slow

- Increase `minScale` to `1` or higher to keep warm pods.
- Use smaller, faster-starting container images (Go and Node.js start faster than Java).
- Set a shorter readiness probe `initialDelaySeconds`.

### Pods don't scale to zero

- Check `autoscaling.knative.dev/minScale` — if set to `1` or higher, scale-to-zero is disabled.
- Verify no continuous traffic is reaching the service (health checks from external monitors count as traffic).
- Check the scale-down window: `autoscaling.knative.dev/window` defaults to 60 seconds.

### Traffic split not working

- Revision names must match exactly. List revisions with `kn revision list` and use the exact names.
- Traffic percentages must sum to 100.
- After applying a traffic split, the Route update may take a few seconds to propagate.

### Operator installation fails on CRC

- Ensure CRC has sufficient resources: `crc config set memory 16384` and `crc config set cpus 6`.
- Check the operator pod logs: `oc logs -n openshift-serverless -l name=knative-openshift`.

## Cleanup

```bash
# Remove Knative Services and traditional deployment
oc delete all -l tutorial-level=2,tutorial-module=M3 -n serverless-tutorial

# Or remove individual resources
kn service delete hello -n serverless-tutorial
kn service delete web-api -n serverless-tutorial
oc delete -f manifests/k8s-deployment-hpa.yaml

# Delete the project
oc delete project serverless-tutorial

# (Optional) Remove the Knative Serving and Eventing instances
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc delete knativeserving knative-serving -n knative-serving
oc delete knativeeventing knative-eventing -n knative-eventing

# (Optional) Remove the Serverless operator
oc delete subscription serverless-operator -n openshift-serverless
oc delete csv -n openshift-serverless -l operators.coreos.com/serverless-operator.openshift-serverless
```

> **Note:** Keep the Serverless operator installed if you plan to continue with L2-M3.4 (Event-Driven Architecture), which builds on the Knative Eventing components installed here.

## Next Steps

In **L2-M3.4 — Event-Driven Architecture**, you will use the Knative Eventing components installed in this lesson to build event-driven workflows. You will work with Brokers, Triggers, Channels, and Subscriptions to connect event sources (including Kafka) to Knative Services, creating loosely coupled architectures where services react to CloudEvents rather than direct HTTP calls.
