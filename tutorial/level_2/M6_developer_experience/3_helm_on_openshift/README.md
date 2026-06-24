# L2-M6.3 — Helm on OpenShift

**Level:** Practitioner
**Duration:** 30 min

## Overview

You already use Helm to package and deploy applications on Kubernetes. OpenShift fully supports Helm, but goes further: the Web Console has built-in Helm chart browsing, Red Hat certifies charts that work out of the box, and OpenShift exposes a `HelmChartRepository` CRD to manage chart sources declaratively. This lesson walks through installing, upgrading, and troubleshooting Helm releases on OpenShift, including the gotchas that catch every K8s user -- SCC failures, Route vs Ingress, and hardcoded UIDs. You will also build a simple Helm chart designed to run cleanly on OpenShift.

## Prerequisites

- Level 1 completed (especially L1-M2.4 on SCCs and L1-M4.2 on Routes vs Ingress)
- OpenShift cluster running (CRC or Developer Sandbox)
- Helm 3 CLI installed (`helm version`)
- `oc` CLI authenticated to the cluster

## K8s Context

On vanilla Kubernetes, Helm is a standalone tool. You add repos with `helm repo add`, search with `helm search`, and install with `helm install`. Charts typically create Ingress resources for external access, hardcode `runAsUser: 0` (root) or specific UIDs in their security contexts, and assume a permissive pod security posture. There is no built-in UI for browsing charts -- you use ArtifactHub or the CLI.

## Concepts

### Helm on OpenShift -- What Is Different

OpenShift supports Helm 3 natively, but adds several features and imposes constraints you need to understand:

**1. Console Integration**

The Developer perspective in the OpenShift Web Console has a built-in Helm chart catalog under **+Add > Helm Chart**. Users can browse, install, and manage releases without touching the CLI. This catalog is populated from `HelmChartRepository` custom resources.

**2. HelmChartRepository CRD**

OpenShift defines a cluster-scoped `HelmChartRepository` resource (and a project-scoped `ProjectHelmChartRepository`) that tells the console where to find charts. Administrators can add, remove, or disable chart repositories declaratively:

```yaml
apiVersion: helm.openshift.io/v1beta1
kind: HelmChartRepository
metadata:
  name: bitnami
spec:
  connectionConfig:
    url: https://charts.bitnami.com/bitnami
```

**3. Red Hat Certified Helm Charts**

Red Hat tests and certifies a catalog of Helm charts that are guaranteed to work on OpenShift -- correct SCCs, proper non-root execution, Routes instead of Ingress. These appear by default in the console. The certification program validates charts against OpenShift's security model.

**4. Common Gotchas**

Most Helm charts from the general ecosystem (ArtifactHub, Bitnami, etc.) are built for vanilla Kubernetes and hit these issues on OpenShift:

- **SCC failures**: Charts that set `runAsUser: 0` or hardcode a UID will fail because OpenShift's `restricted` SCC assigns UIDs from the project's range. You must override the security context or grant a permissive SCC.
- **Route vs Ingress**: Charts create Kubernetes Ingress resources. OpenShift supports Ingress, but Routes are the native, more capable option. You often need to disable Ingress and create a Route instead (or add a Route template to the chart).
- **Docker Hub images**: Many charts reference images that expect root. Swap to Red Hat UBI-based images or grant the `anyuid` SCC.

## Step-by-Step

### Step 1: Set Up the Project

Create a dedicated project for this lesson.

```bash
oc new-project helm-demo --display-name="Helm on OpenShift Demo"
```

Expected output:

```
Now using project "helm-demo" on server "https://api.crc.testing:6443".
```

Verify Helm is working with your cluster:

```bash
helm version
helm list
```

Expected output:

```
version.BuildInfo{Version:"v3.x.x", ...}
NAME    NAMESPACE    REVISION    UPDATED    STATUS    CHART    APP VERSION
```

### Step 2: Browse Helm Charts in the Web Console

Open the OpenShift Web Console and switch to the **Developer** perspective:

1. Navigate to **+Add** in the left sidebar.
2. Click **Helm Chart**.
3. Browse the catalog of available charts -- these come from the default `HelmChartRepository` resources.
4. Notice the **Red Hat** and **Certified** badges on some charts. These have been tested to work on OpenShift.
5. Try searching for "Node.js" or "httpd" to see certified options.

This is a key difference from vanilla K8s: chart discovery and installation are integrated into the platform UI.

### Step 3: Add a Custom Helm Chart Repository

Add a chart repo using both the CLI and the OpenShift CRD approach.

**CLI approach** (same as Kubernetes):

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

**OpenShift CRD approach** (makes the repo visible in the Web Console):

```bash
oc apply -f manifests/helm-chartrepo.yaml
```

The `HelmChartRepository` resource is cluster-scoped, so you need cluster-admin privileges:

```bash
# Log in as kubeadmin to create the cluster-scoped resource
oc login -u kubeadmin -p $(cat ~/.crc/machines/crc/kubeadmin-password) \
  https://api.crc.testing:6443

oc apply -f manifests/helm-chartrepo.yaml

# Switch back to developer
oc login -u developer -p developer https://api.crc.testing:6443
oc project helm-demo
```

For project-scoped repos (no admin required), use `ProjectHelmChartRepository`:

```bash
oc apply -f manifests/project-helmchartrepo.yaml
```

Verify the repos are registered:

```bash
# CLI repos
helm repo list

# OpenShift CRD repos (need admin for cluster-scoped)
oc get helmchartrepositories
```

Expected output:

```
NAME        URL
bitnami     https://charts.bitnami.com/bitnami

NAME       AGE
bitnami    30s
```

After applying the `HelmChartRepository`, refresh the Web Console and navigate to **+Add > Helm Chart** -- you should see Bitnami charts in the catalog.

### Step 4: Experience SCC Issues with a Community Chart

This step deliberately shows what goes wrong when you install a chart designed for vanilla Kubernetes. Install the Bitnami NGINX chart:

```bash
helm install nginx-test bitnami/nginx --set service.type=ClusterIP
```

Watch the pods:

```bash
oc get pods -w
```

You will likely see the pod stuck in `CrashLoopBackOff` or `CreateContainerConfigError`. Check why:

```bash
oc describe pod -l app.kubernetes.io/name=nginx | grep -A 5 "Warning"
```

Expected output (typical SCC failure):

```
Warning  Failed     ...  Error: container has runAsNonRoot and image will run as root
```

Or check events:

```bash
oc get events --sort-by='.lastTimestamp' | tail -5
```

The Bitnami NGINX chart sets `runAsUser` to a specific UID and the image expects to bind to port 80 (a privileged port). Both conflict with OpenShift's `restricted` SCC.

**This is the most common Helm gotcha on OpenShift.** In L1-M2.4 you learned that OpenShift enforces the `restricted` SCC by default -- here you see it in action with real-world charts.

Clean up the failed release:

```bash
helm uninstall nginx-test
```

### Step 5: Fix SCC Issues with Value Overrides

The correct fix is to override the chart's security settings. Look at the `manifests/scc-fix-values.yaml` file for a template of common overrides:

```bash
cat manifests/scc-fix-values.yaml
```

For the NGINX chart specifically, use these overrides:

```bash
helm install nginx-test bitnami/nginx \
  --set service.type=ClusterIP \
  --set containerSecurityContext.runAsUser=null \
  --set podSecurityContext.enabled=false \
  --set containerSecurityContext.enabled=false \
  --set image.registry=registry.access.redhat.com \
  --set image.repository=ubi9/httpd-24 \
  --set image.tag=latest \
  --set containerPorts.http=8080
```

Alternatively, if you trust the chart and just need to bypass SCC (not recommended for production):

```bash
# Grant anyuid SCC to the default service account (requires admin)
oc adm policy add-scc-to-user anyuid -z default -n helm-demo
```

The preferred approach is always to fix the chart values rather than weakening security. Clean up before continuing:

```bash
helm uninstall nginx-test 2>/dev/null || true
# Remove the SCC grant if you applied it
oc adm policy remove-scc-from-user anyuid -z default -n helm-demo 2>/dev/null || true
```

### Step 6: Build an OpenShift-Compatible Helm Chart

Now create a chart that works cleanly on OpenShift from the start. The chart is in `manifests/openshift-compatible-chart/`. Examine its structure:

```bash
ls manifests/openshift-compatible-chart/
ls manifests/openshift-compatible-chart/templates/
```

Expected output:

```
Chart.yaml  templates/  values.yaml

_helpers.tpl  deployment.yaml  ingress.yaml  route.yaml  service.yaml
```

Key design decisions that make this chart OpenShift-compatible:

**1. Security context -- no hardcoded UID:**

```yaml
# values.yaml
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
  runAsNonRoot: true
  seccompProfile:
    type: RuntimeDefault
```

Notice there is no `runAsUser` field. OpenShift assigns a UID from the project's allocated range, so hardcoding a UID will conflict with the `restricted` SCC.

**2. Route instead of Ingress (with toggle):**

```yaml
# values.yaml
route:
  enabled: true        # OpenShift Route (default)
  tls:
    termination: edge

ingress:
  enabled: false       # K8s Ingress (disabled by default)
```

The chart includes both `route.yaml` and `ingress.yaml` templates, controlled by values. This makes the chart portable: enable `ingress` and disable `route` for vanilla K8s.

**3. Non-privileged port and UBI base image:**

```yaml
service:
  port: 8080
  targetPort: 8080

image:
  repository: registry.access.redhat.com/ubi9/httpd-24
```

Port 8080 does not require root privileges. The UBI (Universal Base Image) is designed to run as non-root on OpenShift.

### Step 7: Install Your Chart

Install the chart from the local directory:

```bash
helm install my-web-app manifests/openshift-compatible-chart/
```

Expected output:

```
NAME: my-web-app
LAST DEPLOYED: ...
NAMESPACE: helm-demo
STATUS: deployed
REVISION: 1
```

Verify the release:

```bash
helm list
```

Expected output:

```
NAME          NAMESPACE    REVISION  UPDATED                   STATUS    CHART                    APP VERSION
my-web-app    helm-demo    1         2024-...                  deployed  openshift-web-app-0.1.0  1.0.0
```

Check that pods are running:

```bash
oc get pods -l app=openshift-web-app
```

Expected output:

```
NAME                                              READY   STATUS    RESTARTS   AGE
my-web-app-openshift-web-app-xxxxx-yyyyy          1/1     Running   0          30s
my-web-app-openshift-web-app-xxxxx-zzzzz          1/1     Running   0          30s
```

Check the Route:

```bash
oc get route
```

Expected output:

```
NAME                             HOST/PORT                                           PATH   SERVICES                         PORT   TERMINATION   WILDCARD
my-web-app-openshift-web-app     my-web-app-openshift-web-app-helm-demo.apps-...            my-web-app-openshift-web-app     http   edge          None
```

### Step 8: Upgrade the Release

Upgrade the release to change replica count and resource limits:

```bash
helm upgrade my-web-app manifests/openshift-compatible-chart/ \
  --set replicaCount=3 \
  --set resources.requests.cpu=100m \
  --set resources.requests.memory=128Mi \
  --set resources.limits.cpu=500m \
  --set resources.limits.memory=256Mi
```

Expected output:

```
Release "my-web-app" has been upgraded. Happy Helming!
NAME: my-web-app
...
REVISION: 2
```

Verify the upgrade:

```bash
helm history my-web-app
```

Expected output:

```
REVISION    UPDATED                     STATUS        CHART                    APP VERSION    DESCRIPTION
1           ...                         superseded    openshift-web-app-0.1.0  1.0.0          Install complete
2           ...                         deployed      openshift-web-app-0.1.0  1.0.0          Upgrade complete
```

Check that three pods are now running:

```bash
oc get pods -l app=openshift-web-app
```

### Step 9: Rollback a Release

Roll back to revision 1 (2 replicas):

```bash
helm rollback my-web-app 1
```

Expected output:

```
Rollback was a success! Happy Helming!
```

Verify:

```bash
helm history my-web-app
oc get pods -l app=openshift-web-app
```

You should see revision 3 (the rollback) and 2 pods running again.

### Step 10: Manage Releases in the Web Console

The Web Console provides a visual interface for Helm releases:

1. Switch to the **Developer** perspective.
2. Navigate to **Helm** in the left sidebar.
3. You should see the `my-web-app` release with its status, revision, and chart version.
4. Click on the release to see:
   - **Resources** tab: all K8s/OpenShift resources created by the chart
   - **Revision History** tab: all revisions with rollback options
   - **Release Notes** tab: chart documentation
5. You can **Upgrade** or **Uninstall** directly from the console.

This integrated management is something you do not get on vanilla Kubernetes without a separate tool like Lens or Rancher.

## Verification

Run these checks to confirm the lesson is working:

```bash
# 1. Helm release is deployed
helm status my-web-app

# 2. Pods are running (not CrashLoopBackOff)
oc get pods -l app=openshift-web-app

# 3. Route is created and accessible
ROUTE_URL=$(oc get route my-web-app-openshift-web-app -o jsonpath='{.spec.host}')
echo "Route: https://${ROUTE_URL}"
curl -sk "https://${ROUTE_URL}" | head -5

# 4. Security context is correct (no root, OpenShift-assigned UID)
oc get pod -l app=openshift-web-app -o jsonpath='{.items[0].spec.containers[0].securityContext}' | python3 -m json.tool

# 5. HelmChartRepository exists (if created with admin)
oc get helmchartrepositories 2>/dev/null || echo "Need admin access to list cluster-scoped HelmChartRepositories"
```

## Troubleshooting

**Problem: Pod fails with `CreateContainerConfigError` or `CrashLoopBackOff`**

This almost always means the chart's security context conflicts with OpenShift's SCC. Check:

```bash
oc describe pod <pod-name> | grep -A 10 "Events"
oc get events --sort-by='.lastTimestamp'
```

Fix: Override `runAsUser`, `fsGroup`, and `securityContext` in chart values to remove hardcoded UIDs.

**Problem: Route not created**

Check that the chart includes a Route template and that `route.enabled=true` in values. Many upstream charts only create Ingress resources.

```bash
helm get values my-web-app
helm get manifest my-web-app | grep "kind: Route"
```

**Problem: `helm install` succeeds but app returns 503**

The readiness probe may be failing. Check:

```bash
oc logs -l app=openshift-web-app
oc describe pod -l app=openshift-web-app | grep -A 5 "Readiness"
```

Common cause: the container listens on port 80 (requires root) but the chart specifies 8080.

**Problem: HelmChartRepository not appearing in console**

The CRD is cluster-scoped -- you need `kubeadmin` to create it. Use `ProjectHelmChartRepository` for project-level repos without admin access.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Helm support | Full (CLI only) | Full (CLI + Web Console integration) |
| Chart browsing | ArtifactHub (external) | Built-in catalog in Developer perspective |
| Chart repo management | `helm repo add` (CLI only) | `HelmChartRepository` CRD + CLI |
| Project-scoped repos | Not available | `ProjectHelmChartRepository` CRD |
| Certified charts | None | Red Hat Certified charts catalog |
| Default security | Permissive (no PSA by default) | `restricted-v2` SCC enforced (charts must not require root) |
| External access | Ingress resource | Route resource (Ingress also supported) |
| Image sources | Docker Hub typical | Red Hat registry / UBI images preferred |
| Release management UI | None built-in | Web Console Helm section |
| Chart gotchas | Generally works as-is | SCC, Route, non-root UID issues common |

## Key Takeaways

- OpenShift fully supports Helm 3 and adds Web Console integration for browsing, installing, and managing releases -- a significant UX improvement over vanilla Kubernetes.
- The `HelmChartRepository` and `ProjectHelmChartRepository` CRDs let you manage chart sources declaratively and make them visible in the console.
- The most common Helm gotcha on OpenShift is SCC failures: charts that hardcode `runAsUser`, expect root, or bind to privileged ports will fail under the default `restricted` SCC. Fix chart values rather than weakening security.
- When building charts for OpenShift, use Routes instead of Ingress, omit `runAsUser` (let OpenShift assign from the project range), use non-privileged ports (8080+), and prefer UBI-based images.
- Red Hat Certified Helm charts are pre-tested to work on OpenShift -- prefer them when available to avoid SCC and compatibility issues.

## Cleanup

```bash
# Uninstall Helm releases
helm uninstall my-web-app

# Remove the HelmChartRepository (requires kubeadmin)
oc delete helmchartrepository bitnami 2>/dev/null || true

# Remove project-scoped chart repo
oc delete projecthelmchartrepository team-charts 2>/dev/null || true

# Remove Helm CLI repos
helm repo remove bitnami

# Delete the project
oc delete project helm-demo
```

Or use the cleanup script:

```bash
./scripts/cleanup.sh
```

## Next Steps

In **L2-M6.4 -- Application Health & Autoscaling**, you will configure liveness, readiness, and startup probes (familiar from K8s) and then use HPA, VPA, and the Cluster Autoscaler on OpenShift to automatically scale your applications based on load.
