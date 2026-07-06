# L1-M2.4 — Autoscaling Model Endpoints

**Level:** Foundations
**Duration:** 30 min

## Overview

LLM inference is GPU-bound and expensive. You want pods to scale up under load to maintain latency and scale down (or to zero) when idle to free GPU resources. If you have used the Kubernetes Horizontal Pod Autoscaler (HPA) to scale Deployments based on CPU or memory, the same primitive works on OpenShift AI -- but CPU and memory are poor proxies for LLM load. This lesson covers HPA as a baseline, then introduces KEDA (Kubernetes Event Driven Autoscaling) which scales on actual vLLM metrics like queued requests.

## Prerequisites

- Completed: [L1-M2.2 — Deploying Gemma4-e4b](../2_deploying_gemma/) — the `gemma-4-e4b` InferenceService is running in the `gemma-model` namespace
- Completed: [L1-M2.3 — OpenAI-Compatible API](../3_openai_compatible_api/) — you know how to send inference requests
- OpenShift cluster running with `oc` CLI authenticated
- KEDA operator installed from OperatorHub (search for "Custom Metrics Autoscaler" -- this is Red Hat's KEDA distribution)

## K8s Context

On vanilla Kubernetes, the HPA scales Deployments based on CPU or memory utilization (or custom metrics if you configure the metrics pipeline). KEDA is a CNCF project that adds event-driven autoscaling and scale-to-zero on top of HPA. Neither is specific to OpenShift -- both work identically on any Kubernetes cluster. What OpenShift adds is the built-in Prometheus/Thanos monitoring stack that KEDA can query without installing a separate metrics server, and the OperatorHub experience for installing KEDA itself.

## Concepts

### Why CPU and Memory Are Poor Metrics for LLMs

An HPA that scales on CPU utilization works well for web applications -- more requests means more CPU. For LLM inference, the bottleneck is the GPU, not the CPU. A vLLM pod can be fully saturated (100% GPU utilization, requests queuing) while reporting only 20% CPU usage. Scaling on CPU would not trigger until the pod is already overwhelmed with queued requests and latency has degraded.

The right metrics for LLM autoscaling are the ones that vLLM itself exposes:

| Metric | What It Measures | Scaling Signal |
|--------|-----------------|----------------|
| `vllm:num_requests_waiting` | Requests queued, waiting for a free slot | Best primary trigger -- directly measures demand |
| `vllm:num_requests_running` | Requests currently being processed | Measures current load |
| `vllm:gpu_cache_usage_perc` | Percentage of GPU KV cache in use | Measures memory pressure |

### Two Autoscaling Approaches

**HPA (Horizontal Pod Autoscaler)** -- Built into Kubernetes. Scales on CPU or memory. Works with RawDeployment mode by targeting the predictor Deployment that KServe creates. Limitations: cannot scale to zero, and CPU/memory do not reflect GPU load. Use when: you need basic scaling without installing extra operators.

**KEDA (Kubernetes Event Driven Autoscaling)** -- Scales on Prometheus metrics, including vLLM's own counters. Supports scale-to-zero. Installed from OperatorHub as the "Custom Metrics Autoscaler" operator (Red Hat's distribution of the KEDA project). Uses a `ScaledObject` CRD that wraps the underlying Deployment. This is the recommended approach for LLM workloads.

| Capability | HPA | KEDA |
|-----------|-----|------|
| Scale on CPU/memory | Yes | Yes |
| Scale on custom metrics | Requires custom metrics adapter | Yes (built-in Prometheus trigger) |
| Scale to zero | No (minimum 1 replica) | Yes |
| Install required | None (built into K8s) | Custom Metrics Autoscaler operator |
| Configuration | `HorizontalPodAutoscaler` CRD | `ScaledObject` CRD |

### Understanding Stabilization Windows

GPU pods are expensive to start -- the vLLM container must download model weights (if not cached) and load them into GPU memory, which can take 5-15 minutes. This makes scaling behavior for LLMs different from typical web workloads:

- **Scale-up stabilization** — Wait before adding replicas to confirm the load increase is sustained, not a brief spike. Too short and you create pods that sit idle after the spike passes.
- **Scale-down stabilization** — Wait before removing replicas to avoid removing a pod that cost 10 minutes to start, only to need it again moments later. Set this longer than scale-up (300 seconds is a reasonable starting point).
- **Cooldown period (KEDA)** — Time after the last trigger activation before KEDA scales to zero. This is separate from the scale-down stabilization window.

### Scale-to-Zero Tradeoff

KEDA can scale the predictor Deployment to zero replicas when there are no requests. This saves GPU resources but introduces a cold start penalty -- the first request after scale-to-zero must wait for the pod to start, download (or load from cache) the model weights, and initialize the GPU. For a model like Gemma4-e4b this can take several minutes. Consider whether your use case tolerates this latency.

## Step-by-Step

### Step 1: Identify the Predictor Deployment

KServe creates a Deployment for each InferenceService predictor. The Deployment name follows the pattern `{inferenceservice-name}-predictor`. Confirm it exists:

```bash
oc get deployment gemma-4-e4b-predictor -n gemma-model
```

Expected output:

```
NAME                     READY   UP-TO-DATE   AVAILABLE   AGE
gemma-4-e4b-predictor    1/1     1            1           1d
```

This is the Deployment that both HPA and KEDA target for scaling.

### Step 2: Apply the HPA (Baseline Approach)

Create an HPA that scales the predictor Deployment based on CPU utilization. This is the simpler option and does not require any additional operators:

```bash
oc apply -f manifests/hpa.yaml
```

Review what was applied:

```bash
oc get hpa gemma-4-e4b-hpa -n gemma-model
```

Expected output:

```
NAME               REFERENCE                          TARGETS         MINPODS   MAXPODS   REPLICAS   AGE
gemma-4-e4b-hpa    Deployment/gemma-4-e4b-predictor   <unknown>/80%   1         3         1          10s
```

The `<unknown>` in TARGETS is normal -- it takes a minute for the metrics server to report the first CPU reading. After 60 seconds, re-run the command and you should see an actual percentage (e.g., `12%/80%`).

Key configuration choices in `manifests/hpa.yaml`:

- `minReplicas: 1` — HPA cannot scale to zero; the minimum is always 1.
- `maxReplicas: 3` — Cap at 3 replicas (3 GPUs).
- `averageUtilization: 80` — Scale up when average CPU exceeds 80%.
- `scaleUp.stabilizationWindowSeconds: 60` — Wait 60 seconds before scaling up.
- `scaleDown.stabilizationWindowSeconds: 300` — Wait 5 minutes before scaling down (GPU pods are expensive to restart).
- `scaleUp/scaleDown.policies` — Add at most 1 pod per 120 seconds (scale-up) or remove at most 1 pod per 300 seconds (scale-down), preventing rapid oscillation.

### Step 3: Test the HPA with a Load Test

Run the load test script to send concurrent requests:

```bash
chmod +x scripts/load_test.sh
./scripts/load_test.sh
```

Expected output:

```
Sending 20 concurrent requests to https://gemma-4-e4b-gemma-model.apps.<cluster>...
Waiting for requests to complete...
Done. Check scaling with: oc get pods -n gemma-model -w
```

Watch the HPA status while the load test runs:

```bash
oc get hpa gemma-4-e4b-hpa -n gemma-model -w
```

You may or may not see the HPA trigger -- remember, CPU utilization is a poor proxy for LLM load. The GPU will be saturated long before CPU reaches 80%. This demonstrates the limitation.

### Step 4: Remove the HPA

Before setting up KEDA, remove the HPA to avoid conflicts (both would try to scale the same Deployment):

```bash
oc delete hpa gemma-4-e4b-hpa -n gemma-model
```

### Step 5: Verify KEDA Is Installed

Confirm the Custom Metrics Autoscaler operator is installed and running:

```bash
oc get pods -n openshift-keda -l app=keda-operator
```

Expected output (pod names will differ):

```
NAME                                      READY   STATUS    RESTARTS   AGE
keda-operator-abc123-xyz                  1/1     Running   0          1d
```

If the namespace or pods do not exist, install the "Custom Metrics Autoscaler" operator from OperatorHub first.

Verify the KEDA CRDs are available:

```bash
oc get crd | grep keda
```

Expected output (partial):

```
scaledobjects.keda.sh                    2024-01-01T00:00:00Z
triggerauthentications.keda.sh           2024-01-01T00:00:00Z
```

### Step 6: Set Up Prometheus Authentication for KEDA

OpenShift's Prometheus (exposed through the Thanos querier) requires authentication. KEDA needs a ServiceAccount with the right permissions and a `TriggerAuthentication` resource to pass the bearer token:

Create a ServiceAccount for KEDA to use:

```bash
oc create serviceaccount keda-metrics-reader -n gemma-model
```

Grant it permission to read cluster monitoring metrics:

```bash
oc adm policy add-cluster-role-to-user cluster-monitoring-view -z keda-metrics-reader -n gemma-model
```

Get the ServiceAccount token (KEDA will use this to authenticate with Thanos):

```bash
oc create token keda-metrics-reader -n gemma-model --duration=8760h
```

Save the token and create a Secret for KEDA:

```bash
TOKEN=$(oc create token keda-metrics-reader -n gemma-model --duration=8760h)

oc create secret generic keda-prometheus-token \
  --from-literal=token="${TOKEN}" \
  -n gemma-model
```

Create the `TriggerAuthentication` resource that references this secret:

```bash
cat <<EOF | oc apply -f -
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: keda-prometheus-auth
  namespace: gemma-model
  labels:
    app: gemma-4-e4b
spec:
  secretTargetRef:
    - parameter: bearerToken
      name: keda-prometheus-token
      key: token
EOF
```

### Step 7: Apply the KEDA ScaledObject

Apply the ScaledObject that scales based on vLLM's `num_requests_waiting` metric:

```bash
oc apply -f manifests/keda-scaledobject.yaml
```

Check the ScaledObject status:

```bash
oc get scaledobject gemma-4-e4b-scaler -n gemma-model
```

Expected output:

```
NAME                   SCALETARGETKIND      SCALETARGETNAME          MIN   MAX   TRIGGERS     AUTHENTICATION            READY   ACTIVE   AGE
gemma-4-e4b-scaler     apps/v1.Deployment   gemma-4-e4b-predictor    0     3     prometheus   keda-prometheus-auth      True    False    10s
```

- `READY: True` means KEDA can connect to Prometheus and evaluate the trigger.
- `ACTIVE: False` means the trigger condition is not met (no requests waiting), so no scaling action is needed.

KEDA automatically creates an HPA behind the scenes. You can see it:

```bash
oc get hpa -n gemma-model
```

Expected output:

```
NAME                              REFERENCE                          TARGETS     MINPODS   MAXPODS   REPLICAS   AGE
keda-hpa-gemma-4-e4b-scaler       Deployment/gemma-4-e4b-predictor   0/5 (avg)   1         3         1          10s
```

Key configuration in `manifests/keda-scaledobject.yaml`:

- `minReplicaCount: 0` — Scale to zero when no requests are waiting (KEDA-exclusive feature).
- `maxReplicaCount: 3` — Maximum 3 replicas.
- `pollingInterval: 15` — KEDA checks the Prometheus metric every 15 seconds.
- `cooldownPeriod: 300` — Wait 5 minutes after the last trigger activation before scaling to zero.
- `triggers.prometheus.query` — Queries `vllm:num_requests_waiting` from OpenShift's Thanos querier.
- `threshold: "5"` — Scale up when more than 5 requests are waiting in the queue.
- `authenticationRef` — References the `TriggerAuthentication` created in Step 6.

### Step 8: Test KEDA Scaling

Run the load test again to generate queued requests:

```bash
./scripts/load_test.sh
```

Watch the pods in a separate terminal:

```bash
oc get pods -n gemma-model -w
```

Check the ScaledObject status:

```bash
oc get scaledobject gemma-4-e4b-scaler -n gemma-model
```

When requests are queuing, `ACTIVE` changes to `True` and KEDA triggers scale-up.

You can also query the vLLM metrics directly to see the queue depth:

```bash
ROUTE_URL=$(oc get route -l serving.kserve.io/inferenceservice=gemma-4-e4b -n gemma-model -o jsonpath='{.items[0].spec.host}')
curl -sk "https://${ROUTE_URL}/metrics" | grep "vllm:num_requests"
```

Expected output (during load):

```
# HELP vllm:num_requests_waiting Number of requests waiting to be processed.
# TYPE vllm:num_requests_waiting gauge
vllm:num_requests_waiting{model_name="gemma-4-e4b"} 8.0
# HELP vllm:num_requests_running Number of requests currently being processed.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{model_name="gemma-4-e4b"} 4.0
```

## Verification

1. Confirm the KEDA ScaledObject is ready:

```bash
oc get scaledobject gemma-4-e4b-scaler -n gemma-model -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
```

Expected: `True`.

2. Confirm KEDA created an HPA:

```bash
oc get hpa -n gemma-model --no-headers | grep keda | wc -l
```

Expected: `1`.

3. Confirm the TriggerAuthentication exists:

```bash
oc get triggerauthentication keda-prometheus-auth -n gemma-model -o name
```

Expected: `triggerauthentication.keda.sh/keda-prometheus-auth`.

4. Verify KEDA can query Prometheus (check the ScaledObject for errors):

```bash
oc describe scaledobject gemma-4-e4b-scaler -n gemma-model | grep -A 5 "Conditions:"
```

If `Ready` is `False`, check the Events section at the bottom for authentication errors. The most common issue is an expired or missing token in the `keda-prometheus-token` secret.

## Troubleshooting

**KEDA ScaledObject shows `Ready: False`**

Check events for authentication failures:

```bash
oc describe scaledobject gemma-4-e4b-scaler -n gemma-model
```

Common causes:
- The `keda-prometheus-token` secret is missing or the token expired. Recreate it (Step 6).
- The `keda-metrics-reader` ServiceAccount does not have `cluster-monitoring-view`. Re-run the `oc adm policy` command from Step 6.
- The Thanos querier address is wrong. Verify it:

```bash
oc get svc thanos-querier -n openshift-monitoring
```

**Scaling is too slow or too aggressive**

Adjust the parameters in `manifests/keda-scaledobject.yaml`:
- Increase `pollingInterval` to check metrics less frequently.
- Increase `cooldownPeriod` to delay scale-to-zero.
- Increase `threshold` to tolerate more queued requests before scaling.
- Increase `stabilizationWindowSeconds` under `behavior.scaleUp` / `behavior.scaleDown`.

**Pods stuck in `Pending` after scale-up**

Not enough GPUs available on the cluster. Check node resources:

```bash
oc describe nodes | grep -A 5 "nvidia.com/gpu"
```

Scale-up can only succeed if the cluster has available GPU resources. Set `maxReplicaCount` to the number of GPUs available.

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| **HPA** | Built-in, same behavior | Identical -- HPA works the same way |
| **KEDA** | Install KEDA from Helm chart or YAML manifests | Install "Custom Metrics Autoscaler" from OperatorHub (Red Hat's KEDA) |
| **Prometheus access** | Set up Prometheus + configure ServiceMonitors | Prometheus/Thanos pre-installed; KEDA queries `thanos-querier.openshift-monitoring.svc` |
| **Metrics authentication** | Varies by Prometheus setup | Requires ServiceAccount with `cluster-monitoring-view` role + TriggerAuthentication |
| **vLLM metrics** | Same metrics exposed on `/metrics` | Same -- vLLM metrics are not OpenShift-specific |
| **Scale-to-zero** | KEDA or Knative | KEDA (Knative/Serverless mode is deprecated in OpenShift AI) |
| **Model serving integration** | Manual Deployment management | KServe manages the predictor Deployment; HPA/KEDA target it by name |

## Key Takeaways

- **CPU and memory are poor scaling signals for LLMs.** GPU utilization and request queue depth (e.g., `vllm:num_requests_waiting`) are the metrics that actually reflect LLM load.
- **KEDA is the recommended autoscaler for LLM endpoints.** It queries Prometheus for vLLM-native metrics and supports scale-to-zero, which HPA cannot do.
- **Stabilization windows matter more for GPU workloads.** Model pods take minutes to start, so premature scale-down wastes expensive startup time and premature scale-up creates pending pods when GPUs are scarce.
- **Scale-to-zero saves resources but adds cold start latency.** The first request after scaling to zero must wait for model download and GPU initialization -- evaluate whether your use case tolerates this.
- **KEDA is not part of OpenShift AI.** It is installed separately from OperatorHub as the "Custom Metrics Autoscaler" operator (Red Hat's distribution of the CNCF KEDA project).

## Cleanup

Remove the autoscaling resources created in this lesson:

```bash
# Delete the KEDA ScaledObject
oc delete scaledobject gemma-4-e4b-scaler -n gemma-model

# Delete the TriggerAuthentication
oc delete triggerauthentication keda-prometheus-auth -n gemma-model

# Delete the KEDA Prometheus token secret
oc delete secret keda-prometheus-token -n gemma-model

# Delete the ServiceAccount
oc delete serviceaccount keda-metrics-reader -n gemma-model

# Remove the cluster role binding
oc adm policy remove-cluster-role-from-user cluster-monitoring-view -z keda-metrics-reader -n gemma-model
```

This is the last lesson in Module 2. If you are done with the Gemma4-e4b deployment, you can optionally clean up the model resources:

```bash
# Optional: remove the model deployment entirely
# oc delete inferenceservice gemma-4-e4b -n gemma-model
# oc delete servingruntime gemma-4-e4b -n gemma-model
# oc delete project gemma-model
```

## Next Steps

In [L1-M3.1 — Fine-Tuning Concepts](../../M3_fine_tuning/1_fine_tuning_concepts/), you will learn about fine-tuning LLMs on OpenShift AI -- when to fine-tune vs. prompt engineer, LoRA and QLoRA techniques, and how the training workflow integrates with KServe serving.
