# L1-M3.4 -- Deployment Strategies

**Level:** Foundations
**Duration:** 30 min

## Overview

You already know that Kubernetes Deployments manage ReplicaSets, which manage Pods. But how you configure the *strategy* for replacing old pods with new ones makes the difference between a seamless update and an outage. In this lesson you will deploy applications using both the **RollingUpdate** and **Recreate** strategies, tune `maxSurge` and `maxUnavailable`, perform rollbacks with `oc rollout undo`, inspect deployment history, and practice pausing and resuming rollouts -- all using standard Kubernetes Deployments on OpenShift.

> **Note on legacy resources:** Older OpenShift clusters may use DeploymentConfig (`apps.openshift.io/v1`), a legacy resource that predates mature Kubernetes Deployments. New workloads should always use standard Kubernetes Deployments.

## Prerequisites

- Completed: L1-M3.3 (ImageStreams & Image Management)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`

## K8s Context

In Kubernetes, the Deployment controller supports two strategies: `RollingUpdate` (the default) and `Recreate`. Rolling updates incrementally replace old pods with new ones, keeping the application available throughout. The `Recreate` strategy terminates all existing pods before creating new ones -- useful when running two versions simultaneously would cause problems (e.g., database schema conflicts). You control rolling update behavior with `maxSurge` (how many extra pods above the desired count) and `maxUnavailable` (how many pods can be unavailable during the update). All of this works identically on OpenShift.

## Concepts

### RollingUpdate Strategy

RollingUpdate is the default and the right choice for most workloads. During an update, the Deployment controller scales up a new ReplicaSet while scaling down the old one, keeping the total pod count within the bounds set by `maxSurge` and `maxUnavailable`. This means your application stays available throughout the update with no downtime.

Key parameters:

- **`maxSurge`** -- the maximum number of pods (or percentage) that can exist above the desired replica count during an update. Setting this higher speeds up rollouts but uses more resources.
- **`maxUnavailable`** -- the maximum number of pods (or percentage) that can be unavailable during an update. Setting this to `0` guarantees zero-downtime updates (paired with a `maxSurge` of at least `1`).

### Recreate Strategy

The Recreate strategy terminates all existing pods before creating new ones. This causes a brief downtime window but guarantees that two different versions of the application never run simultaneously. Use this when:

- Your application cannot tolerate running two versions at the same time (e.g., it performs database migrations on startup).
- You have a singleton workload that must not run in parallel.

### Readiness Gates and Probes

A rolling update only succeeds if new pods become *ready*. Without a readiness probe, Kubernetes considers a pod ready as soon as its containers start -- even if the application is not yet serving traffic. Always configure `readinessProbe` so the Deployment controller waits for your application to actually be healthy before proceeding with the rollout.

### Revision History and Rollback

Every time a Deployment's pod template changes, Kubernetes creates a new ReplicaSet and records the change as a *revision*. The `revisionHistoryLimit` field controls how many old ReplicaSets are retained. You can inspect history with `oc rollout history` and roll back to any previous revision with `oc rollout undo`.

### Pausing and Resuming Rollouts

You can pause a rollout mid-way with `oc rollout pause`. While paused, you can make multiple changes to the Deployment spec without triggering incremental rollouts for each change. When you resume with `oc rollout resume`, all accumulated changes are applied in a single rollout.

### What OpenShift Adds

On OpenShift, Deployments work exactly as they do on vanilla Kubernetes -- the `oc` CLI provides the same `rollout` subcommands as `kubectl`. OpenShift adds value around Deployments through:

- **Routes** that automatically route traffic to your Service, integrating with rolling updates seamlessly.
- **The Web Console**, which provides a visual rollout status view under Workloads > Deployments.
- **Triggers via ImageStreams** (when combined with additional tooling or Tekton pipelines) to automate rollouts when new images are available.

## Step-by-Step

### Step 1: Create a Project

Set up a dedicated project for this lesson.

```bash
oc new-project deploy-strategies --display-name="Deployment Strategies Lab"
```

Expected output:
```
Now using project "deploy-strategies" on server "https://api.crc.testing:6443".
```

### Step 2: Deploy with the RollingUpdate Strategy

Apply the rolling update Deployment. This manifest sets `maxSurge: 1` and `maxUnavailable: 0` -- meaning updates will add one new pod at a time and never drop below the desired count.

```bash
oc apply -f manifests/deployment-rolling.yaml
```

Wait for the rollout to complete:

```bash
oc rollout status deployment/nginx-rolling
```

Expected output:
```
deployment "nginx-rolling" successfully rolled out
```

Verify the pods and ReplicaSet:

```bash
oc get deployment nginx-rolling -o wide
oc get replicasets -l variant=rolling
```

Expected output (Deployment):
```
NAME            READY   UP-TO-DATE   AVAILABLE   AGE   CONTAINERS   IMAGES                                                  SELECTOR
nginx-rolling   3/3     3            3           30s   nginx        registry.access.redhat.com/ubi9/nginx-122:latest         app=deploy-strategies,variant=rolling
```

### Step 3: Deploy with the Recreate Strategy

Apply the Recreate Deployment. This one terminates all old pods before creating new ones.

```bash
oc apply -f manifests/deployment-recreate.yaml
```

Wait for the rollout:

```bash
oc rollout status deployment/nginx-recreate
```

Expected output:
```
deployment "nginx-recreate" successfully rolled out
```

### Step 4: Trigger a Rolling Update and Observe the Behavior

Update the rolling Deployment by setting an environment variable. This changes the pod template and triggers a new rollout.

```bash
oc set env deployment/nginx-rolling STRATEGY_DEMO=rolling-v2
```

Immediately watch the rollout in progress:

```bash
oc rollout status deployment/nginx-rolling
```

Expected output:
```
Waiting for deployment "nginx-rolling" rollout to finish: 1 out of 3 new replicas have been updated...
Waiting for deployment "nginx-rolling" rollout to finish: 2 out of 3 new replicas have been updated...
deployment "nginx-rolling" successfully rolled out
```

Check the ReplicaSets -- you should see two, with the old one scaled to 0:

```bash
oc get replicasets -l variant=rolling
```

Expected output:
```
NAME                       DESIRED   CURRENT   READY   AGE
nginx-rolling-6b8d4f7b9c   0         0         0       2m
nginx-rolling-7c9e5f8a1d   3         3         3       30s
```

### Step 5: Trigger a Recreate Update and Observe the Difference

Update the Recreate Deployment:

```bash
oc set env deployment/nginx-recreate STRATEGY_DEMO=recreate-v2
```

Watch the rollout:

```bash
oc rollout status deployment/nginx-recreate
```

Notice the difference: all old pods are terminated first, then new pods are created. There is a brief period where zero pods are ready.

### Step 6: Inspect Deployment History

Check the revision history for the rolling Deployment:

```bash
oc rollout history deployment/nginx-rolling
```

Expected output:
```
deployment.apps/nginx-rolling
REVISION  CHANGE-CAUSE
1         initial deployment
2         <none>
```

The first revision shows the `change-cause` annotation from the manifest. To annotate the second revision:

```bash
oc annotate deployment/nginx-rolling kubernetes.io/change-cause="added STRATEGY_DEMO=rolling-v2 env var" --overwrite
```

Check history again:

```bash
oc rollout history deployment/nginx-rolling
```

Expected output:
```
deployment.apps/nginx-rolling
REVISION  CHANGE-CAUSE
1         initial deployment
2         added STRATEGY_DEMO=rolling-v2 env var
```

View the details of a specific revision:

```bash
oc rollout history deployment/nginx-rolling --revision=1
```

### Step 7: Perform a Rollback

Roll back the rolling Deployment to the previous revision:

```bash
oc rollout undo deployment/nginx-rolling
```

Expected output:
```
deployment.apps/nginx-rolling rolled back
```

Verify the rollback:

```bash
oc rollout status deployment/nginx-rolling
```

Check that the environment variable is gone (rolled back to revision 1):

```bash
oc set env deployment/nginx-rolling --list
```

Expected output:
```
# deployment/nginx-rolling, container nginx
# (no environment variables)
```

You can also roll back to a specific revision:

```bash
# First, trigger another update to create revision 4
oc set env deployment/nginx-rolling STRATEGY_DEMO=rolling-v3

# Roll back to a specific revision number
oc rollout undo deployment/nginx-rolling --to-revision=1
```

### Step 8: Pause and Resume a Rollout

Pause the rolling Deployment so you can batch multiple changes without triggering individual rollouts for each one:

```bash
oc rollout pause deployment/nginx-rolling
```

Expected output:
```
deployment.apps/nginx-rolling paused
```

Make several changes while paused -- none of these trigger a rollout:

```bash
oc set env deployment/nginx-rolling APP_VERSION=v2
oc set env deployment/nginx-rolling ENVIRONMENT=staging
```

Verify the Deployment is paused (the `PAUSED` condition appears):

```bash
oc get deployment nginx-rolling -o jsonpath='{.spec.paused}{"\n"}'
```

Expected output:
```
true
```

Resume the rollout -- all accumulated changes deploy in a single rollout:

```bash
oc rollout resume deployment/nginx-rolling
```

Expected output:
```
deployment.apps/nginx-rolling resumed
```

Watch the combined rollout:

```bash
oc rollout status deployment/nginx-rolling
```

Verify both environment variables are present in the new pods:

```bash
oc set env deployment/nginx-rolling --list
```

Expected output:
```
# deployment/nginx-rolling, container nginx
APP_VERSION=v2
ENVIRONMENT=staging
```

### Step 9: View Rollout Status in the Web Console

Open the OpenShift Web Console (https://console-openshift-console.apps-crc.testing) and navigate to:

1. Switch to the **Developer** perspective.
2. Go to **Topology** -- you should see both Deployments represented as nodes.
3. Click on `nginx-rolling` and view the **Resources** tab to see the ReplicaSets and pod status.
4. Switch to the **Administrator** perspective and go to **Workloads > Deployments**.
5. Click on `nginx-rolling` and check the **ReplicaSets** tab to see the full revision history.

The Web Console provides a visual timeline of rollouts that complements the CLI workflow.

## Verification

Run these commands to confirm the lesson worked:

```bash
# 1. Verify the rolling Deployment is running with 3 replicas
oc get deployment nginx-rolling -o jsonpath='{.status.readyReplicas}{"\n"}'
# Expected: 3

# 2. Verify the recreate Deployment is running with 3 replicas
oc get deployment nginx-recreate -o jsonpath='{.status.readyReplicas}{"\n"}'
# Expected: 3

# 3. Confirm the rolling Deployment uses the RollingUpdate strategy
oc get deployment nginx-rolling -o jsonpath='{.spec.strategy.type}{"\n"}'
# Expected: RollingUpdate

# 4. Confirm the recreate Deployment uses the Recreate strategy
oc get deployment nginx-recreate -o jsonpath='{.spec.strategy.type}{"\n"}'
# Expected: Recreate

# 5. Check that multiple ReplicaSets exist (revision history) for the rolling Deployment
oc get replicasets -l variant=rolling --no-headers | wc -l
# Expected: a number greater than 1

# 6. Check rollout history has multiple revisions
oc rollout history deployment/nginx-rolling
# Expected: multiple revisions listed
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Deployment resource | `apps/v1 Deployment` | Same -- `apps/v1 Deployment` |
| RollingUpdate strategy | Supported | Identical behavior |
| Recreate strategy | Supported | Identical behavior |
| `maxSurge` / `maxUnavailable` | Configured in strategy spec | Same |
| Rollback | `kubectl rollout undo` | `oc rollout undo` (same behavior) |
| Pause / resume | `kubectl rollout pause/resume` | `oc rollout pause/resume` (same) |
| Rollout status | `kubectl rollout status` | `oc rollout status` (same) |
| Visual rollout monitoring | K8s Dashboard (limited) | Web Console with topology view and detailed ReplicaSet timeline |
| Traffic management during rollouts | Requires Ingress controller setup | Built-in HAProxy router with Routes handles traffic seamlessly |
| Automated image-triggered rollouts | Requires external tooling (ArgoCD, Flux) | Can integrate with ImageStreams and Tekton pipelines |

## Key Takeaways

- **RollingUpdate is the default and usually the right choice.** It keeps your application available throughout updates by incrementally replacing pods. Use `maxSurge` and `maxUnavailable` to control the pace and safety of the rollout.
- **Recreate is for workloads that cannot tolerate two versions running simultaneously.** It causes brief downtime but guarantees no overlap between old and new pods.
- **Always configure readiness probes.** Without them, Kubernetes may route traffic to pods that are not yet ready to serve, and rolling updates may proceed before the application is healthy.
- **Deployment history enables fast rollbacks.** Use `oc rollout undo` to revert to any previous revision. Annotate deployments with `kubernetes.io/change-cause` to make history meaningful.
- **Pause and resume lets you batch changes.** Pause a Deployment, make multiple spec changes, then resume to roll them all out at once -- avoiding unnecessary intermediate rollouts.

## Cleanup

```bash
# Delete all resources created in this lesson
oc delete all -l tutorial-level=1,tutorial-module=M3

# Delete the project entirely
oc delete project deploy-strategies
```

## Next Steps

In **L1-M3.5 -- Templates & Kustomize**, you will learn how to parameterize your OpenShift manifests using OpenShift Templates (with `oc process`) and how Kustomize and Helm provide portable alternatives for managing application configurations.
