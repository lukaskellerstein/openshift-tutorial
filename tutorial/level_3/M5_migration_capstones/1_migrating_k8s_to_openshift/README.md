# L3-M5.1 -- Migrating from Kubernetes to OpenShift

**Level:** Expert
**Duration:** 1 hr

## Overview

You know Kubernetes inside and out. Now your organization is adopting OpenShift, and you need to move workloads from vanilla K8s clusters to OpenShift without downtime, security regressions, or operational surprises. This lesson covers every dimension of a K8s-to-OpenShift migration: security context constraints that will break your pods, Route objects that replace your Ingress resources, image policies that block Docker Hub pulls, and the Migration Toolkit for Containers (MTC/Crane) that automates the heavy lifting. You will walk through a production-grade migration checklist, execute a hands-on migration of a sample application, and practice diagnosing the most common failures.

## Prerequisites

- Completed all Level 1 and Level 2 lessons (particularly L1-M2.4 SCCs, L1-M4.2 Routes, L1-M3.3 ImageStreams)
- Completed L3-M1 through L3-M4 modules
- OpenShift cluster running (CRC or production cluster)
- Access to a Kubernetes cluster with a sample workload (or use the provided manifests)
- `oc` and `kubectl` CLIs installed
- Familiarity with Helm (L2-M6.3) and GitOps (L2-M1.3)

## K8s Context

In Kubernetes, you deploy workloads by writing Deployments, Services, and Ingress resources. Pods can run as root by default. You install whatever ingress controller you prefer (nginx, traefik, HAProxy). You pull images from any registry without restriction. Security is opt-in: PodSecurity Admission labels are namespace-level and often left at `baseline` or `privileged` during development. There is no built-in migration tooling -- moving workloads between clusters typically means re-applying manifests and migrating persistent data with Velero or manual PV snapshots.

OpenShift changes the defaults. Security is enforced from the start. The platform is opinionated about how workloads should run, and those opinions reflect enterprise security requirements. A naive `kubectl apply` of your K8s manifests on OpenShift will fail in ways that are predictable once you understand the differences, but surprising if you do not.

## Concepts

### The Five Pillars of K8s-to-OpenShift Migration

Every K8s-to-OpenShift migration touches five areas. Neglect any one and your workloads will break.

```
+------------------------------------------------------------------+
|                    MIGRATION PILLARS                              |
+------------------------------------------------------------------+
|                                                                   |
|  1. SECURITY       2. NETWORKING     3. IMAGES                   |
|  +------------+    +------------+    +------------+              |
|  | SCCs       |    | Routes vs  |    | UBI images |              |
|  | Non-root   |    | Ingress    |    | ImageStream|              |
|  | Restricted |    | HAProxy    |    | Pull       |              |
|  | SCC by     |    | TLS modes  |    | policies   |              |
|  | default    |    | Built-in   |    | Internal   |              |
|  +------------+    +------------+    | registry   |              |
|                                      +------------+              |
|  4. BUILDS         5. OPERATIONS                                 |
|  +------------+    +-------------------+                         |
|  | BuildConfig|    | Projects vs NS    |                         |
|  | S2I        |    | Resource quotas   |                         |
|  | Image      |    | LimitRanges       |                         |
|  | triggers   |    | RBAC differences  |                         |
|  +------------+    | Monitoring stack  |                         |
|                    +-------------------+                         |
+------------------------------------------------------------------+
```

### Pillar 1: Security Context Constraints (SCCs)

This is the number-one migration blocker. In Kubernetes, pods run as root unless you explicitly prevent it. In OpenShift, the `restricted` SCC is enforced by default, which means:

- Containers **cannot run as UID 0** (root)
- Containers **cannot use privileged ports** (< 1024)
- Containers **cannot mount hostPath volumes**
- Containers **cannot escalate privileges**
- The UID is assigned from a namespace-specific range

Most Docker Hub images assume root. Nginx listens on port 80. PostgreSQL writes to `/var/lib/postgresql` as root. All of these will fail with `CrashLoopBackOff` or `CreateContainerConfigError` on OpenShift.

**Remediation options (in order of preference):**

1. **Use UBI-based images** -- Red Hat Universal Base Images are designed for OpenShift. `registry.access.redhat.com/ubi9/nginx-122` listens on 8080, runs as non-root.
2. **Fix the Dockerfile** -- Change `USER` to a non-root user, bind to a non-privileged port, ensure the process can write to its data directories as any UID.
3. **Grant `anyuid` SCC** -- A last resort. Binds a ServiceAccount to the `anyuid` SCC so the pod can run as root. This weakens security and should be documented and audited.

### Pillar 2: Routes vs Ingress

OpenShift has its own ingress mechanism: **Routes**. The HAProxy-based router is pre-installed on every OpenShift cluster. You do not need to install an ingress controller.

Key differences:

| Aspect | K8s Ingress | OpenShift Route |
|--------|-------------|-----------------|
| Controller | Must install (nginx, traefik, etc.) | Pre-installed HAProxy |
| TLS termination | Depends on controller annotations | Native: edge, passthrough, re-encrypt |
| Certificate management | Manual or cert-manager | Auto-generated or custom |
| Wildcard routing | Annotation-dependent | Native `wildcardPolicy` |
| Rate limiting | Annotation-dependent | Native annotations |

OpenShift also supports standard Kubernetes Ingress objects. The router translates them to Routes automatically. However, controller-specific annotations (`nginx.ingress.kubernetes.io/*`) will be ignored. Migrate your annotations to the Route equivalent.

### Pillar 3: Image Policies and Registry

OpenShift introduces several image-related concepts that do not exist in vanilla K8s:

- **ImageStreams** abstract image references. Instead of hardcoding `docker.io/library/nginx:1.25` in a Deployment, you reference an ImageStream tag. This enables image change triggers (auto-redeploy when a new image is pushed) and registry pull-through caching.
- **Image pull policies** can restrict which registries are allowed. An OpenShift admin can block Docker Hub entirely, requiring all images to come from the internal registry or an approved mirror.
- The **internal registry** (`image-registry.openshift-image-registry.svc:5000`) stores images built by BuildConfigs and imported via ImageStreams.

### Pillar 4: Builds

Kubernetes has no built-in build system. You build images externally (CI/CD, Docker, Kaniko) and push them to a registry. OpenShift has **BuildConfigs** that can:

- Build from Git source using **S2I** (Source-to-Image) -- no Dockerfile required
- Build from a Dockerfile (**Docker strategy**)
- Run **custom builds** for specialized scenarios
- Trigger builds automatically on code push (webhooks), image updates (ImageStream triggers), or configuration changes

During migration, you can either continue using your external CI/CD or adopt BuildConfigs. Many teams adopt BuildConfigs for development builds and keep their external CI for production pipelines.

### Pillar 5: Operations

Several operational concepts change:

- **Namespaces become Projects** -- `oc new-project` creates a namespace with display name, description, and default RBAC. Self-provisioning allows developers to create their own projects.
- **ResourceQuotas and LimitRanges** are often enforced cluster-wide by admins. Your workloads need resource requests and limits, or they will be rejected.
- **Monitoring** is pre-installed (Prometheus + Grafana). You do not install your own monitoring stack; you configure ServiceMonitors and PrometheusRules.
- **RBAC** differs in defaults: OpenShift ships with `admin`, `edit`, and `view` ClusterRoles that map to project-level access. The `self-provisioner` ClusterRole allows users to create projects.

### Migration Toolkit for Containers (MTC/Crane)

For large-scale migrations, the **Migration Toolkit for Containers** (MTC, formerly Crane) automates the process:

```
+--------------------+                    +---------------------+
|  SOURCE CLUSTER    |                    |  TARGET CLUSTER     |
|  (Kubernetes)      |                    |  (OpenShift)        |
|                    |                    |                     |
|  +-------------+   |     MigPlan       |  +-------------+    |
|  | Workloads   |   |  +------------>   |  | Workloads   |    |
|  | PVs         |   |  | MigMigration   |  | PVs         |    |
|  | ConfigMaps  |   |  |                |  | ConfigMaps  |    |
|  | Secrets     |   |  |  Replication   |  | Secrets     |    |
|  +-------------+   |  |  Controller    |  +-------------+    |
|                    |  |                |                     |
|  MTC Controller    |  |  MigStorage    |  MTC Controller     |
|  (installed)       |  | (S3-compatible)|  (installed)        |
+--------------------+  +---------------+  +---------------------+
```

MTC handles:

- **Namespace migration** -- all resources in a namespace (Deployments, Services, ConfigMaps, Secrets, etc.)
- **Persistent volume migration** -- copies PV data via direct or indirect (S3-based) transfer
- **Image migration** -- copies images from the source registry to the OpenShift internal registry
- **Stage migrations** -- pre-copy PV data while the source is still running (minimize cutover downtime)
- **Rollback** -- revert a failed migration

MTC does NOT automatically fix SCC issues, convert Ingress to Routes, or adapt image references. Those are pre-migration tasks.

## Step-by-Step

### Step 1: Create the Migration Demo Project

Create a dedicated project for this migration exercise.

```bash
oc new-project migration-demo \
  --display-name="K8s Migration Demo" \
  --description="L3-M5.1: Kubernetes to OpenShift migration"
```

Apply resource quota and limit range to simulate production constraints:

```bash
oc apply -f manifests/resource-quota.yaml -n migration-demo
oc apply -f manifests/limit-range.yaml -n migration-demo
```

Verify they are in place:

```bash
oc describe quota migration-demo-quota -n migration-demo
oc describe limitrange migration-demo-limits -n migration-demo
```

### Step 2: Attempt to Deploy the Original K8s Manifest (Watch It Fail)

First, try deploying the original Kubernetes manifest without modifications. This is instructive -- you need to see how OpenShift rejects insecure workloads.

```bash
oc apply -f manifests/k8s-deployment.yaml -n migration-demo
```

Watch the pods:

```bash
oc get pods -n migration-demo -w
```

You will see the pods fail. Check why:

```bash
oc get events -n migration-demo --sort-by='.lastTimestamp' | tail -20
```

Expected error:

```
Warning  FailedCreate  ... Error creating: pods "demo-app-..." is forbidden:
unable to validate against any security context constraint:
[spec.containers[0].securityContext.runAsUser: Invalid value: 0:
must be in the ranges: [1000680000, 1000689999]]
```

This is the `restricted` SCC in action. The Deployment specifies `runAsUser: 0`, which OpenShift blocks.

Delete the failed deployment:

```bash
oc delete -f manifests/k8s-deployment.yaml -n migration-demo
```

### Step 3: Run the Pre-Migration Audit

If you have a Kubernetes cluster with the original workloads, run the audit script to identify all migration blockers:

```bash
# Against a K8s cluster (switch context if needed)
# kubectl config use-context my-k8s-cluster
./scripts/pre-migration-audit.sh <namespace>
```

The audit script checks for:

1. Containers running as root (UID 0)
2. Missing `securityContext` (defaults to root in many images)
3. Privileged ports below 1024
4. Ingress resources that need conversion to Routes
5. Docker Hub images that may not run as non-root
6. PersistentVolumeClaims with StorageClasses that may not exist on OpenShift
7. HostPath volumes (blocked by restricted SCC)
8. Missing resource requests/limits

Review the output and address each finding before proceeding.

### Step 4: Fix the Deployment for OpenShift

Review the differences between the original and migrated Deployment:

```bash
diff manifests/k8s-deployment.yaml manifests/openshift-deployment.yaml
```

Key changes in `manifests/openshift-deployment.yaml`:

1. **Image**: `nginx:1.25` (Docker Hub, runs as root, port 80) changed to `registry.access.redhat.com/ubi9/nginx-122:latest` (UBI, non-root, port 8080)
2. **Port**: `containerPort: 80` changed to `containerPort: 8080`
3. **securityContext**: Removed `runAsUser: 0`, added `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, dropped all capabilities, set `seccompProfile`
4. **Labels**: Added `tutorial-level` and `tutorial-module` for resource management

Deploy the corrected version:

```bash
oc apply -f manifests/openshift-deployment.yaml -n migration-demo
```

Watch the pods come up:

```bash
oc get pods -n migration-demo -w
```

All pods should reach `Running` status. Verify the SCC assigned:

```bash
oc get pods -n migration-demo -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.annotations.openshift\.io/scc}{"\n"}{end}'
```

Expected output shows `restricted-v2` (the default SCC):

```
demo-app-xxxxx-yyyyy   restricted-v2
demo-app-xxxxx-zzzzz   restricted-v2
demo-app-xxxxx-wwwww   restricted-v2
```

### Step 5: Deploy the Service

The Service manifest works identically on both platforms:

```bash
oc apply -f manifests/service.yaml -n migration-demo
```

Verify:

```bash
oc get svc -n migration-demo
```

### Step 6: Convert Ingress to Route

Instead of applying the K8s Ingress, deploy an OpenShift Route:

```bash
oc apply -f manifests/openshift-route.yaml -n migration-demo
```

Verify the Route is accessible:

```bash
oc get route demo-app -n migration-demo
ROUTE_URL=$(oc get route demo-app -n migration-demo -o jsonpath='{.spec.host}')
echo "Route URL: https://${ROUTE_URL}"
curl -sk "https://${ROUTE_URL}" | head -5
```

For automated Ingress-to-Route conversion across many resources, use the helper script:

```bash
# Against a K8s cluster with Ingress resources:
./scripts/migrate-ingress-to-route.sh <namespace> ./generated-routes
```

Review the generated Route YAMLs before applying them.

### Step 7: Set Up ImageStream (Optional)

For production workloads, use an ImageStream to decouple the image reference from the Deployment:

```bash
oc apply -f manifests/imagestream.yaml -n migration-demo
```

Verify the ImageStream imported the image:

```bash
oc get is demo-app -n migration-demo
oc describe is demo-app -n migration-demo
```

You can then update the Deployment to reference the ImageStream instead of the external registry:

```bash
oc set image deployment/demo-app \
  demo-app=image-registry.openshift-image-registry.svc:5000/migration-demo/demo-app:latest \
  -n migration-demo
```

### Step 8: Apply Network Policies

OpenShift clusters using OVN-Kubernetes enforce NetworkPolicy by default. Apply restrictive policies:

```bash
oc apply -f manifests/networkpolicy.yaml -n migration-demo
```

Verify the policy is active:

```bash
oc get networkpolicy -n migration-demo
oc describe networkpolicy demo-app-allow-http -n migration-demo
```

Test that the Route still works (traffic from the router namespace is explicitly allowed):

```bash
curl -sk "https://${ROUTE_URL}" | head -5
```

### Step 9: Handle the Escape Hatch -- anyuid SCC (When You Cannot Fix the Image)

Sometimes you have a third-party image that cannot be rebuilt. In that case, grant the `anyuid` SCC as a stopgap:

```bash
# Review the manifest first
cat manifests/scc-anyuid.yaml

# Apply the ServiceAccount and RoleBinding
oc apply -f manifests/scc-anyuid.yaml -n migration-demo
```

Then update the Deployment to use this ServiceAccount:

```bash
oc patch deployment demo-app -n migration-demo \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/serviceAccountName", "value": "demo-app-sa"}]'
```

**WARNING**: Granting `anyuid` weakens the security boundary. Always document why it is necessary, which pods use it, and set a timeline to remediate (switch to a non-root image). In production, use a custom SCC with the minimum privileges needed rather than the broad `anyuid`.

Revert the patch (use the non-root image instead):

```bash
oc patch deployment demo-app -n migration-demo \
  --type='json' \
  -p='[{"op": "remove", "path": "/spec/template/spec/serviceAccountName"}]'
```

### Step 10: Migration Toolkit for Containers (MTC)

For cluster-to-cluster migration, use MTC. Install the operator:

```bash
# Install the MTC operator (cluster-admin required)
oc login -u kubeadmin https://api.crc.testing:6443

# Create the operator subscription
cat <<'EOF' | oc apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: crane-operator
  namespace: openshift-migration
spec:
  channel: release-v1.8
  installPlanApproval: Automatic
  name: crane-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
```

Wait for the operator to install:

```bash
oc get csv -n openshift-migration -w
```

Once the operator is ready, review the MigPlan and MigMigration resources:

```bash
cat manifests/mtc-migplan.yaml
```

The MigPlan specifies:
- **Source cluster** -- your Kubernetes cluster (registered via MigCluster CR)
- **Target cluster** -- `host` (the OpenShift cluster where MTC runs)
- **Storage** -- S3-compatible storage for indirect migrations
- **Namespaces** -- which namespaces to migrate

Before creating the MigPlan, you must:
1. Register the source K8s cluster as a MigCluster
2. Configure S3 storage as a MigStorage
3. Ensure network connectivity between clusters

These steps require a real multi-cluster environment. In CRC, you can review the CRDs and the MTC web console:

```bash
oc get crd | grep migration
# Expected: migclusters, migmigrations, migplans, migstorages, etc.
```

Access the MTC web console from the OpenShift console under **Migration** in the left navigation.

### Step 11: Run Post-Migration Verification

After the migration (whether manual or via MTC), run the verification script:

```bash
# Switch back to developer user
oc login -u developer -p developer https://api.crc.testing:6443

./scripts/post-migration-verify.sh migration-demo
```

The script checks:
1. Project exists and is active
2. All pods are Running (no CrashLoopBackOff, no Pending)
3. SCC assignments (flags privileged SCCs as warnings)
4. Routes are created and accessible
5. Services are configured
6. PVCs are Bound
7. No warning events in the project
8. Route URLs return HTTP 200

## Verification

Run these commands to confirm the migration exercise is complete:

```bash
# All pods running
oc get pods -n migration-demo
# Expected: 3 pods in Running state

# Route accessible
ROUTE_URL=$(oc get route demo-app -n migration-demo -o jsonpath='{.spec.host}')
curl -sk "https://${ROUTE_URL}" -o /dev/null -w "HTTP %{http_code}\n"
# Expected: HTTP 200

# SCC is restricted (not anyuid or privileged)
oc get pods -n migration-demo -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.annotations.openshift\.io/scc}{"\n"}{end}'
# Expected: all pods show "restricted-v2"

# Network policy in place
oc get networkpolicy -n migration-demo
# Expected: demo-app-allow-http

# Resource quota enforced
oc describe quota -n migration-demo
# Expected: shows usage against hard limits

# Run the full verification script
./scripts/post-migration-verify.sh migration-demo
# Expected: PASSED
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| **Default pod security** | Permissive (root allowed) | Restricted SCC (no root, no privilege escalation) |
| **Ingress** | Ingress resource + external controller | Route (built-in HAProxy) + optional Ingress support |
| **TLS termination** | Controller-dependent annotations | Native edge/passthrough/re-encrypt on Route |
| **Container images** | Any registry, any UID | UBI-recommended; image policies can restrict registries |
| **Image management** | Direct references in manifests | ImageStreams with tags, triggers, pull-through caching |
| **Build system** | None (external CI/CD) | BuildConfig with S2I, Docker, Custom strategies |
| **Namespaces** | Plain namespaces | Projects (namespace + metadata + default RBAC) |
| **Resource enforcement** | Optional ResourceQuota/LimitRange | Often mandatory; cluster-admin sets defaults |
| **Monitoring** | Install Prometheus yourself | Pre-installed Prometheus + Grafana |
| **Migration tooling** | Velero (community) | MTC/Crane (supported) + Velero |
| **Port binding** | Any port | Non-root: ports >= 1024 only |
| **hostPath volumes** | Allowed | Blocked by restricted SCC |
| **CLI** | `kubectl` | `oc` (superset) -- `kubectl` also works |

## Failure Modes and Recovery

### CrashLoopBackOff After Migration

**Symptom**: Pods cycle between `Running` and `CrashLoopBackOff`.

**Diagnosis**:
```bash
oc logs <pod-name> -n migration-demo --previous
oc describe pod <pod-name> -n migration-demo
oc get events -n migration-demo --field-selector involvedObject.name=<pod-name>
```

**Common causes**:
1. **Permission denied writing to filesystem** -- The container runs as a random UID but the image expects root to own data directories. Fix: add an `initContainer` that sets permissions, or rebuild the image.
2. **Bind to privileged port** -- The app tries to bind to port 80 or 443. Fix: configure the app to use 8080 or higher.
3. **Missing config** -- ConfigMaps or Secrets were not migrated. Fix: verify all ConfigMaps and Secrets exist in the target namespace.

### CreateContainerConfigError

**Symptom**: Pod stays in `CreateContainerConfigError` state.

**Diagnosis**:
```bash
oc describe pod <pod-name> -n migration-demo | grep -A5 "Warning"
```

**Common causes**:
1. **SCC violation** -- The pod spec requests capabilities or UIDs that the SCC does not allow.
2. **Missing Secret** -- A Secret referenced in `envFrom` or `volumeMounts` does not exist.

**Recovery**:
```bash
# Check which SCC would admit the pod
oc adm policy scc-subject-review -f manifests/openshift-deployment.yaml
```

### ImagePullBackOff

**Symptom**: Pod stays in `ImagePullBackOff`.

**Diagnosis**:
```bash
oc describe pod <pod-name> -n migration-demo | grep -A10 "Events"
```

**Common causes**:
1. **Image policy blocks the registry** -- Admin has restricted allowed registries.
2. **Authentication required** -- Docker Hub rate limits or private registries need pull secrets.
3. **Image does not exist** -- Typo in image name or tag.

**Recovery**:
```bash
# Check image policy
oc get image.config.openshift.io/cluster -o yaml

# Create a pull secret for Docker Hub
oc create secret docker-registry dockerhub-pull \
  --docker-server=docker.io \
  --docker-username=<user> \
  --docker-password=<token> \
  -n migration-demo

# Link the secret to the default ServiceAccount
oc secrets link default dockerhub-pull --for=pull -n migration-demo
```

### Route Not Accessible (503 or Connection Refused)

**Symptom**: Route exists but returns 503 or connection is refused.

**Diagnosis**:
```bash
oc get route demo-app -n migration-demo -o yaml
oc get endpoints demo-app -n migration-demo
oc get svc demo-app -n migration-demo
```

**Common causes**:
1. **Port mismatch** -- The Route `targetPort` does not match the Service port or the container port.
2. **No endpoints** -- The Service selector does not match any running pods.
3. **NetworkPolicy blocking** -- A NetworkPolicy is blocking traffic from the router namespace.

**Recovery**: Verify the chain: Route (targetPort) -> Service (port/targetPort) -> Pod (containerPort). All three must match.

### PVC Pending After Migration

**Symptom**: PVCs stay in `Pending` state.

**Diagnosis**:
```bash
oc describe pvc <pvc-name> -n migration-demo
oc get sc
```

**Common causes**:
1. **StorageClass mismatch** -- The PVC references a StorageClass that does not exist on OpenShift. Fix: update the PVC to use an available StorageClass.
2. **Quota exhausted** -- The ResourceQuota for PVCs is reached. Fix: increase the quota or delete unused PVCs.

## Production Migration Checklist

Use this checklist for real-world migrations:

```
PRE-MIGRATION
  [ ] Run pre-migration-audit.sh on every namespace
  [ ] Identify all root containers -- plan UBI replacements or SCC grants
  [ ] Inventory all Ingress resources -- plan Route conversions
  [ ] Verify StorageClass compatibility for all PVCs
  [ ] Create pull secrets for external registries
  [ ] Document all required SCCs beyond restricted
  [ ] Set up ResourceQuotas and LimitRanges in target projects
  [ ] Test each workload individually on OpenShift (staging)
  [ ] Configure NetworkPolicies
  [ ] Set up monitoring (ServiceMonitors, PrometheusRules)

DURING MIGRATION
  [ ] Create target projects with proper RBAC
  [ ] Apply ResourceQuotas and LimitRanges
  [ ] Migrate ConfigMaps and Secrets first
  [ ] Migrate PVCs (MTC stage migration for minimal downtime)
  [ ] Deploy workloads with OpenShift-compatible manifests
  [ ] Create Routes (replace Ingress)
  [ ] Apply NetworkPolicies
  [ ] Verify all pods are Running under restricted SCC
  [ ] Test all Route endpoints

POST-MIGRATION
  [ ] Run post-migration-verify.sh on every project
  [ ] Verify monitoring is collecting metrics
  [ ] Validate alerting rules fire correctly
  [ ] Load test to verify performance parity
  [ ] Update DNS records (if switching from K8s Ingress endpoints)
  [ ] Decommission source workloads (after validation period)
  [ ] Document all anyuid/privileged SCC grants with remediation timeline
  [ ] Update CI/CD pipelines to target OpenShift
```

## Key Takeaways

- **Security is the biggest migration blocker**: OpenShift's restricted SCC rejects pods that run as root, use privileged ports, or mount hostPath volumes. Audit every workload before migration.
- **Routes replace Ingress**: OpenShift has a pre-installed HAProxy router with native TLS termination modes. Convert Ingress annotations to Route annotations; controller-specific annotations will be silently ignored.
- **UBI images prevent most SCC failures**: Replace Docker Hub images with Red Hat Universal Base Images (UBI) that are designed for non-root execution on OpenShift.
- **MTC automates cluster-to-cluster migration**: The Migration Toolkit for Containers handles namespace resources, PV data, and images, but you must fix SCC and Ingress issues separately.
- **Always run post-migration verification**: Pods in `Running` state is not enough -- verify SCC assignments, Route accessibility, NetworkPolicy enforcement, and monitoring integration.

## Cleanup

```bash
# Delete all resources created in this lesson
oc delete project migration-demo

# If you applied the MTC operator subscription (as kubeadmin):
oc login -u kubeadmin https://api.crc.testing:6443
oc delete subscription crane-operator -n openshift-migration 2>/dev/null || true
oc delete csv -l operators.coreos.com/crane-operator.openshift-migration -n openshift-migration 2>/dev/null || true

# Switch back to developer
oc login -u developer -p developer https://api.crc.testing:6443

# Clean up generated files
rm -rf ./generated-routes
rm -f migration-audit-*.txt
```

## Next Steps

In **L3-M5.2 -- Migrating Legacy Apps to OpenShift**, you will tackle the harder problem: containerizing applications that currently run on virtual machines. You will use S2I to build images from legacy source code, evaluate lift-and-shift vs. refactor strategies, and learn when OpenShift Virtualization (KubeVirt) is the right answer for workloads that cannot be containerized.
