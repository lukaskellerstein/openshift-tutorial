# L2-M6.4 — Application Health & Autoscaling

**Level:** Practitioner
**Duration:** 30 min

## Overview

You already know Kubernetes health probes and the Horizontal Pod Autoscaler. OpenShift uses the same primitives but adds platform-level integration: the Web Console surfaces probe status and autoscaler metrics in the Topology and Monitoring views, the Cluster Autoscaler ties into MachineSet-based node provisioning, and the Vertical Pod Autoscaler (VPA) operator is available through OperatorHub. This lesson configures all three probe types on a production-style deployment, then layers on HPA and VPA to build a complete autoscaling strategy.

## Prerequisites

- Completed: Level 1 (all modules)
- Completed: L2-M6.1 through L2-M6.3 (recommended)
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI authenticated (`oc whoami` succeeds)

## K8s Context

In Kubernetes you define three probe types on a container:

- **Liveness probe** — restarts the container if it fails (the process is stuck, deadlocked, or otherwise unhealthy).
- **Readiness probe** — removes the pod from Service endpoints when it fails (the app exists but cannot serve traffic yet).
- **Startup probe** — gates the other two probes during initial boot (useful for slow-starting apps so the liveness probe does not kill them prematurely).

For autoscaling, Kubernetes provides:

- **HPA (Horizontal Pod Autoscaler)** — scales replicas based on CPU, memory, or custom metrics.
- **VPA (Vertical Pod Autoscaler)** — adjusts resource requests/limits per pod (requires a separate install in upstream K8s).
- **Cluster Autoscaler** — adds or removes nodes (cloud-specific, configured outside K8s manifests).

All of this works identically on OpenShift at the API level. The differences are in platform integration, operator availability, and the developer experience around these features.

## Concepts

### Health Probes on OpenShift

OpenShift uses the exact same probe API fields as Kubernetes (`livenessProbe`, `readinessProbe`, `startupProbe`). The key OpenShift additions are:

1. **Web Console visualization** — The Developer Topology view shows pod health status with color-coded rings (green = healthy, yellow = degrading, red = failing). Clicking a pod surfaces probe configuration and recent restart events.
2. **`oc set probe`** — OpenShift extends the CLI with a convenience command to add or modify probes without editing YAML directly.
3. **SCC interaction** — If your probe uses `exec` to run a command, remember that the container runs under the `restricted` SCC by default. The probe command must work within that security context.

### Horizontal Pod Autoscaler (HPA)

The HPA API (`autoscaling/v2`) works identically on OpenShift. OpenShift pre-installs the metrics server (via the `openshift-monitoring` stack), so CPU and memory metrics are available out of the box without installing `metrics-server` separately as you would in upstream Kubernetes.

OpenShift also supports custom metrics-based autoscaling through the **Custom Metrics Autoscaler Operator** (based on KEDA — Kubernetes Event-Driven Autoscaling). This lets you scale on Prometheus metrics, Kafka lag, message queue depth, and other external signals.

### Vertical Pod Autoscaler (VPA)

In upstream Kubernetes, VPA requires a manual install of the `autoscaler` project components. On OpenShift, VPA is available as an operator from OperatorHub (the **VerticalPodAutoscaler** operator). Once installed, you create `VerticalPodAutoscaler` CRs to right-size your workloads.

VPA modes:
- **`Auto`** — applies recommendations and may evict pods to resize them.
- **`Recreate`** — same as Auto (evicts pods).
- **`Initial`** — only sets resources on pod creation, never evicts running pods.
- **`Off`** — computes recommendations only, does not apply them (useful for analysis).

**Important:** Do not use HPA and VPA on the same metric (e.g., both scaling on CPU). They will fight each other. The recommended pattern is HPA on CPU/memory for horizontal scaling and VPA on a different resource or in `Off` mode for right-sizing recommendations.

### Cluster Autoscaler

On OpenShift, the Cluster Autoscaler integrates with MachineSets. When the HPA wants more replicas but there are no schedulable nodes, the Cluster Autoscaler provisions new Machines via the MachineSet (in cloud environments). On CRC, the Cluster Autoscaler is not applicable since there is only one node.

## Step-by-Step

### Step 1: Create the Project

Create a dedicated project for this lesson:

```bash
oc new-project health-autoscale-demo
```

Expected output:
```
Now using project "health-autoscale-demo" on server "https://api.crc.testing:6443".
```

### Step 2: Deploy the Application with Health Probes

We will deploy an Nginx-based application with all three probe types configured. The deployment includes production-quality resource requests and limits.

Apply the deployment manifest:

```bash
oc apply -f manifests/deployment-with-probes.yaml
```

Review the key probe configuration in the manifest:

```yaml
startupProbe:
  httpGet:
    path: /
    port: 8080
  failureThreshold: 30
  periodSeconds: 2
readinessProbe:
  httpGet:
    path: /
    port: 8080
  initialDelaySeconds: 0
  periodSeconds: 5
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /
    port: 8080
  initialDelaySeconds: 0
  periodSeconds: 10
  failureThreshold: 3
```

The startup probe runs first, checking every 2 seconds for up to 30 attempts (60 seconds total). Only after the startup probe succeeds do the readiness and liveness probes begin. This prevents the liveness probe from killing a slow-starting container.

Expected output:
```
deployment.apps/probe-demo created
```

### Step 3: Expose the Application with a Service and Route

Apply the Service and Route so we can access the application:

```bash
oc apply -f manifests/service.yaml
oc apply -f manifests/route.yaml
```

Wait for the pod to become ready:

```bash
oc rollout status deployment/probe-demo --timeout=120s
```

Expected output:
```
deployment "probe-demo" successfully rolled out
```

Verify the pod is running with all probes passing:

```bash
oc get pods -l app=probe-demo
```

Expected output:
```
NAME                          READY   STATUS    RESTARTS   AGE
probe-demo-6f8b9c7d4f-xxxxx  1/1     Running   0          30s
```

The `1/1` in READY confirms both the startup and readiness probes have passed.

### Step 4: Use `oc set probe` to Modify Probes via CLI

OpenShift provides a convenience command to manage probes without editing YAML. This is useful for quick iterations:

```bash
# View current probe configuration
oc describe deployment probe-demo | grep -A 10 "Liveness\|Readiness\|Startup"
```

Add or modify a liveness probe using the CLI (this overwrites the existing one):

```bash
oc set probe deployment/probe-demo --liveness \
  --get-url=http://:8080/ \
  --period-seconds=15 \
  --failure-threshold=5
```

Expected output:
```
deployment.apps/probe-demo probes updated
```

This is equivalent to editing the YAML but faster for quick changes. Reset it back by reapplying the original manifest:

```bash
oc apply -f manifests/deployment-with-probes.yaml
```

### Step 5: Deploy the HPA

Now add horizontal autoscaling. The HPA will scale our deployment between 1 and 5 replicas based on CPU utilization:

```bash
oc apply -f manifests/hpa.yaml
```

Verify the HPA was created:

```bash
oc get hpa probe-demo-hpa
```

Expected output (metrics may show `<unknown>` for a few seconds until the metrics pipeline catches up):
```
NAME             REFERENCE               TARGETS         MINPODS   MAXPODS   REPLICAS   AGE
probe-demo-hpa   Deployment/probe-demo   <unknown>/60%   1         5         1          10s
```

Wait about 30 seconds and check again. The CPU target should show an actual value:

```bash
oc get hpa probe-demo-hpa
```

Expected output:
```
NAME             REFERENCE               TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
probe-demo-hpa   Deployment/probe-demo   2%/60%    1         5         1          45s
```

### Step 6: Generate Load to Trigger Autoscaling

Open a second terminal (or use `oc run`) to generate CPU load against the application:

```bash
# Get the route URL
ROUTE_URL=$(oc get route probe-demo -o jsonpath='{.spec.host}')

# Generate load using a temporary pod
oc run load-generator --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
  --restart=Never \
  --command -- /bin/bash -c \
  "while true; do curl -s http://${ROUTE_URL} > /dev/null; done"
```

Alternatively, use the `scripts/generate-load.sh` script:

```bash
bash scripts/generate-load.sh
```

Watch the HPA respond:

```bash
oc get hpa probe-demo-hpa --watch
```

After 1-2 minutes, you should see the replica count increase:
```
NAME             REFERENCE               TARGETS    MINPODS   MAXPODS   REPLICAS   AGE
probe-demo-hpa   Deployment/probe-demo   2%/60%     1         5         1          60s
probe-demo-hpa   Deployment/probe-demo   78%/60%    1         5         1          90s
probe-demo-hpa   Deployment/probe-demo   78%/60%    1         5         2          105s
probe-demo-hpa   Deployment/probe-demo   45%/60%    1         5         2          2m
```

Press `Ctrl+C` to stop watching.

> **Note:** On CRC with limited resources, the CPU increase may be small. The behavior is the same as upstream Kubernetes HPA.

### Step 7: Observe in the Web Console

Open the OpenShift Web Console and navigate to:

1. **Developer perspective > Topology** — Click the probe-demo application. The pod ring shows the number of replicas. During scaling, you will see new pods appearing.
2. **Administrator perspective > Workloads > HorizontalPodAutoscalers** — View the HPA details, current metrics, and scaling events.
3. **Administrator perspective > Workloads > Deployments > probe-demo > Pods** — See probe status and restart counts for each pod.

The Web Console provides richer visibility into health and autoscaling than `kubectl` alone.

### Step 8: Deploy a VPA Resource (Recommendation Mode)

Apply the VPA in `Off` mode to collect right-sizing recommendations without modifying the deployment:

```bash
oc apply -f manifests/vpa.yaml
```

> **Note:** The VPA operator must be installed from OperatorHub for this to work. On CRC, you may need to install it first: navigate to **OperatorHub > search "VerticalPodAutoscaler" > Install**. If the operator is not available, skip this step — the VPA manifest is included for reference.

Check recommendations after a few minutes:

```bash
oc get vpa probe-demo-vpa -o jsonpath='{.status.recommendation}' | python3 -m json.tool
```

Expected output (values will vary based on actual usage):
```json
{
  "containerRecommendations": [
    {
      "containerName": "nginx",
      "lowerBound": {
        "cpu": "10m",
        "memory": "20Mi"
      },
      "target": {
        "cpu": "25m",
        "memory": "50Mi"
      },
      "upperBound": {
        "cpu": "100m",
        "memory": "200Mi"
      }
    }
  ]
}
```

These recommendations help you right-size your resource requests for production deployments.

### Step 9: Clean Up the Load Generator

Stop the load generator pod:

```bash
oc delete pod load-generator --ignore-not-found
```

Watch the HPA scale back down (this takes about 5 minutes due to the default stabilization window):

```bash
oc get hpa probe-demo-hpa --watch
```

## Verification

Confirm the full setup is working:

```bash
# 1. Deployment is running with probes configured
oc get deployment probe-demo -o jsonpath='{.spec.template.spec.containers[0].livenessProbe.httpGet.path}'
# Expected: /

# 2. All pods are healthy (READY = 1/1)
oc get pods -l app=probe-demo
# Expected: STATUS=Running, READY=1/1

# 3. HPA is active and tracking metrics
oc get hpa probe-demo-hpa
# Expected: TARGETS shows a percentage (not <unknown>)

# 4. Route is accessible
curl -s -o /dev/null -w "%{http_code}" http://$(oc get route probe-demo -o jsonpath='{.spec.host}')
# Expected: 200

# 5. Probes are configured correctly
oc describe deployment probe-demo | grep -c "Probe"
# Expected: 3 (liveness, readiness, startup)
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Health probes | `livenessProbe`, `readinessProbe`, `startupProbe` | Identical API; `oc set probe` CLI shortcut; Web Console visualization |
| Metrics server | Install `metrics-server` manually | Pre-installed via `openshift-monitoring` |
| HPA | `autoscaling/v2` | Identical API; Web Console dashboard for HPA metrics |
| VPA | Install `autoscaler` project components manually | Install via OperatorHub (one click) |
| Custom metrics autoscaling | Install KEDA manually | Custom Metrics Autoscaler Operator via OperatorHub |
| Cluster Autoscaler | Cloud-specific controller, configured outside K8s | Integrated with MachineSets; `ClusterAutoscaler` and `MachineAutoscaler` CRDs |
| Probe debugging | `kubectl describe pod` | `oc describe pod` + Web Console probe status, events, and topology health rings |

## Key Takeaways

- **Health probes work identically** on OpenShift and Kubernetes at the API level. The OpenShift Web Console and `oc set probe` add convenience, not new functionality.
- **The metrics server is pre-installed** on OpenShift, so HPA works out of the box without installing `metrics-server` as you would in upstream K8s.
- **VPA is an operator install** on OpenShift (via OperatorHub), compared to a manual multi-component deployment in upstream Kubernetes. Use it in `Off` mode alongside HPA to get right-sizing recommendations without conflicts.
- **Do not use HPA and VPA on the same metric** (e.g., both targeting CPU). They will compete. Use HPA for horizontal scaling and VPA for resource right-sizing recommendations.
- **Startup probes are critical for production** — without them, slow-starting applications get killed by the liveness probe during initialization. Always configure `startupProbe` with a generous `failureThreshold`.

## Troubleshooting

### Probe-related issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Pod in `CrashLoopBackOff` | Liveness probe failing before app starts | Add a `startupProbe` or increase `initialDelaySeconds` on the liveness probe |
| Pod running but not receiving traffic | Readiness probe failing | Check the probe path/port; run `oc logs` to see if the app is listening |
| Probe works locally but fails on OpenShift | Probe command needs root or writes to restricted paths | Ensure probe works under `restricted` SCC; use HTTP probes over exec probes when possible |

### HPA-related issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| HPA shows `<unknown>` targets indefinitely | No resource requests defined on the container | Add `resources.requests.cpu` to the container spec |
| HPA never scales up | Target utilization set too high, or actual load is below threshold | Lower the `averageUtilization` target, or generate more load |
| HPA scales up but pods are Pending | Insufficient node resources | On CRC, lower `maxReplicas`; in production, configure Cluster Autoscaler |

## Cleanup

```bash
# Delete the load generator if still running
oc delete pod load-generator --ignore-not-found

# Delete all lesson resources
oc delete -f manifests/ --ignore-not-found

# Delete the project
oc delete project health-autoscale-demo
```

## Next Steps

Congratulations on completing Level 2! You have covered the full OpenShift practitioner experience — from CI/CD and operators to service mesh, security, and developer tooling.

Continue to **Level 3 — L3-M1.1: Installation Methods**, where you will explore production cluster operations, starting with the different ways to install OpenShift (IPI vs UPI) across bare metal, cloud, and edge environments.
