# L2-M5.2 — Pod Security & Admission

**Level:** Practitioner
**Duration:** 30 min

## Overview

In L1-M2.4 you learned that OpenShift uses Security Context Constraints (SCCs) to deny root containers by default. This lesson goes deeper: you will explore advanced SCC customization, understand how Kubernetes Pod Security Admission (PSA) labels interact with OpenShift's SCC model, and deploy OPA Gatekeeper to enforce custom admission policies that go far beyond what SCCs alone can do. By the end, you will have a working Gatekeeper ConstraintTemplate and Constraint that blocks containers running as root -- an enterprise-grade policy layer on top of SCCs.

## Prerequisites

- Completed: L1-M2.4 (Security Context Constraints)
- Completed: L2-M5.1 (Image Security & Compliance)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as both `developer` and `kubeadmin`
- `oc` CLI installed and on PATH

## K8s Context

In Kubernetes 1.25+, Pod Security Admission (PSA) replaced the deprecated PodSecurityPolicies. PSA uses namespace labels to enforce three profiles:

- **`privileged`** -- unrestricted, no checks applied.
- **`baseline`** -- prevents known privilege escalations (host networking, privileged containers, etc.).
- **`restricted`** -- heavily locked down (non-root, drop all capabilities, read-only root filesystem encouraged).

You apply PSA by labeling namespaces:

```yaml
metadata:
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
```

For custom policies beyond these three profiles, the K8s ecosystem relies on external admission controllers -- most commonly **OPA Gatekeeper** or **Kyverno**. These run as webhook-based admission controllers that evaluate policies before pods are created.

## Concepts

### SCCs vs. PSA: How They Coexist on OpenShift

OpenShift 4.x supports **both** SCCs and PSA, but they serve different roles:

| Mechanism | Scope | Granularity | Assignment |
|-----------|-------|-------------|------------|
| SCC | Cluster-wide resource | 8+ built-in profiles, custom SCCs | Bound to service accounts |
| PSA | Namespace labels | 3 fixed profiles (`privileged`, `baseline`, `restricted`) | Applied per namespace |

On OpenShift, SCCs are the **primary enforcement mechanism**. PSA labels are synchronized automatically by the Security Context Constraint Admission controller -- OpenShift reads the SCCs available in a namespace and sets the corresponding PSA label. You can override these labels, but SCCs still enforce independently.

**Key point:** PSA on OpenShift is additive. SCCs do the heavy lifting; PSA labels provide a K8s-standard audit trail and compatibility layer.

### Custom SCCs

In L1-M2.4 you used the built-in SCCs (`restricted-v2`, `anyuid`, etc.). In production, you often need a custom SCC that sits between these built-in profiles -- for example, allowing `NET_BIND_SERVICE` capability while still enforcing non-root. Custom SCCs let you define exactly what a workload is allowed to do.

### OPA Gatekeeper on OpenShift

OPA (Open Policy Agent) Gatekeeper is an admission controller that evaluates policies written in Rego. It uses two custom resources:

- **`ConstraintTemplate`** -- defines the policy logic (Rego code) and the parameters the policy accepts.
- **`Constraint`** (an instance of the template) -- applies the policy to specific resources with specific parameters.

Gatekeeper evaluates every API request against matching constraints and rejects requests that violate policy. This gives you arbitrary policy enforcement that goes far beyond what SCCs or PSA can express:

- "All containers must come from an approved registry"
- "No pod may run as root"
- "All deployments must have resource limits"
- "Labels `team` and `cost-center` are required on every namespace"

### Kyverno as an Alternative

Kyverno is another popular policy engine that uses YAML-native policies instead of Rego. It is easier to learn but less powerful for complex logic. On OpenShift, both Gatekeeper and Kyverno work well. This lesson focuses on Gatekeeper because it is the more widely adopted choice in enterprise environments and has a larger policy library.

## Step-by-Step

### Step 1: Create a Test Project

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc new-project pod-security-demo
```

### Step 2: Inspect PSA Labels on Your Namespace

OpenShift automatically synchronizes PSA labels based on the SCCs available in the namespace. Check what labels were applied:

```bash
oc get namespace pod-security-demo -o jsonpath='{.metadata.labels}' | python3 -m json.tool
```

Expected output (the exact values depend on your cluster version):

```json
{
    "kubernetes.io/metadata.name": "pod-security-demo",
    "pod-security.kubernetes.io/audit": "restricted",
    "pod-security.kubernetes.io/audit-version": "v1.24",
    "pod-security.kubernetes.io/warn": "restricted",
    "pod-security.kubernetes.io/warn-version": "v1.24"
}
```

Notice that OpenShift sets `audit` and `warn` labels but typically does not set `enforce` -- because SCCs handle enforcement. If you try to manually set `enforce: restricted`, SCCs still apply independently.

### Step 3: Test PSA Warnings

Deploy a pod that violates the `restricted` PSA profile to see warnings (but note that the SCC, not PSA, is what actually blocks it):

```bash
oc apply -f manifests/psa-test-pod.yaml
```

You may see a warning like:

```
Warning: would violate PodSecurity "restricted:v1.24": ...
```

The pod may still be created (PSA is in `warn` mode, not `enforce`), but it will fail because the `restricted-v2` SCC rejects root containers. Check the pod:

```bash
oc get pods -l app=psa-test
```

Expected output:

```
NAME       READY   STATUS             RESTARTS   AGE
psa-test   0/1     CrashLoopBackOff   1          10s
```

This demonstrates the layered model: PSA warns, SCCs enforce.

### Step 4: Create a Custom SCC

Let us create an SCC that allows `NET_BIND_SERVICE` and `NET_RAW` capabilities (useful for applications that bind to ports below 1024 or need raw sockets) while still enforcing non-root.

Log in as `kubeadmin`:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

Apply the custom SCC:

```bash
oc apply -f manifests/custom-scc.yaml
```

Verify it was created:

```bash
oc get scc custom-network-v2
```

Expected output:

```
NAME                 PRIV    CAPS                              SELINUX     RUNASUSER          FSGROUP     SUPGROUP    PRIORITY     READONLYROOTFS   VOLUMES
custom-network-v2    false   [NET_BIND_SERVICE NET_RAW]        MustRunAs   MustRunAsRange     MustRunAs   RunAsAny    <no value>   false            [configMap downwardAPI emptyDir persistentVolumeClaim projected secret]
```

### Step 5: Assign the Custom SCC and Test

Create a service account and grant it the custom SCC:

```bash
oc create serviceaccount network-app-sa -n pod-security-demo
oc adm policy add-scc-to-user custom-network-v2 -z network-app-sa -n pod-security-demo
```

Switch to the developer user and deploy a pod that uses the custom SCC:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc apply -f manifests/network-app-deployment.yaml -n pod-security-demo
```

Verify the pod is running and confirm the SCC:

```bash
oc get pods -l app=network-app -n pod-security-demo
oc get pod -l app=network-app -n pod-security-demo \
  -o jsonpath='{.items[0].metadata.annotations.openshift\.io/scc}' && echo
```

Expected output:

```
NAME                           READY   STATUS    RESTARTS   AGE
network-app-7c4d9f5b8-k3m2n   1/1     Running   0          12s
custom-network-v2
```

### Step 6: Install OPA Gatekeeper

Gatekeeper can be installed via the OLM OperatorHub on OpenShift. For this lesson, we install it from the official release manifests.

Log in as `kubeadmin`:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

Install Gatekeeper:

```bash
oc apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/v3.16.0/deploy/gatekeeper.yaml
```

Wait for the Gatekeeper pods to be ready:

```bash
oc get pods -n gatekeeper-system -w
```

Expected output (after a minute or two):

```
NAME                                            READY   STATUS    RESTARTS   AGE
gatekeeper-audit-6c4d5f7b9-abc12                1/1     Running   0          90s
gatekeeper-controller-manager-7d8e6f9c4-def34   1/1     Running   0          90s
gatekeeper-controller-manager-7d8e6f9c4-ghi56   1/1     Running   0          90s
gatekeeper-controller-manager-7d8e6f9c4-jkl78   1/1     Running   0          90s
```

Press `Ctrl+C` once all pods show `Running`.

> **Note on CRC:** Gatekeeper requires some resources. If your CRC instance is resource-constrained, you may need to increase CPU/memory: `crc config set cpus 6 && crc config set memory 14336`.

> **Troubleshooting:** If the Gatekeeper pods fail with SCC errors, grant the Gatekeeper service accounts the necessary SCCs:
> ```bash
> oc adm policy add-scc-to-user anyuid -z gatekeeper-admin -n gatekeeper-system
> oc adm policy add-scc-to-user anyuid -z gatekeeper-controller-manager -n gatekeeper-system
> oc delete pods --all -n gatekeeper-system
> ```

### Step 7: Create a ConstraintTemplate -- Block Root Containers

Apply the ConstraintTemplate that defines the policy logic:

```bash
oc apply -f manifests/constraint-template-disallow-root.yaml
```

This template defines a Rego policy that checks whether a container's `securityContext.runAsUser` is set to `0` or whether `runAsNonRoot` is not set to `true`. Let us verify:

```bash
oc get constrainttemplate k8sdisallowroot
```

Expected output:

```
NAME                AGE
k8sdisallowroot     15s
```

### Step 8: Create a Constraint -- Apply the Policy

Now instantiate the template with a Constraint that targets pods in the `pod-security-demo` namespace:

```bash
oc apply -f manifests/constraint-disallow-root.yaml
```

Verify:

```bash
oc get k8sdisallowroot
```

Expected output:

```
NAME                          ENFORCEMENT-ACTION   TOTAL-VIOLATIONS
disallow-root-pods            deny                 0
```

### Step 9: Test the Gatekeeper Policy

Try to create a pod that explicitly runs as root:

```bash
oc apply -f manifests/gatekeeper-test-root-pod.yaml -n pod-security-demo
```

Expected output -- the request is **rejected** by Gatekeeper before it even reaches the SCC admission:

```
Error from server (Forbidden): error when creating "manifests/gatekeeper-test-root-pod.yaml":
admission webhook "validation.gatekeeper.sh" denied the request:
[disallow-root-pods] Container "test-root" is attempting to run as root (runAsUser: 0).
Set runAsNonRoot: true and use a non-zero runAsUser.
```

Now create a compliant pod:

```bash
oc apply -f manifests/gatekeeper-test-nonroot-pod.yaml -n pod-security-demo
```

Expected output:

```
pod/test-nonroot created
```

Verify it is running:

```bash
oc get pod test-nonroot -n pod-security-demo
```

Expected output:

```
NAME           READY   STATUS    RESTARTS   AGE
test-nonroot   1/1     Running   0          8s
```

### Step 10: Create a ConstraintTemplate -- Require Resource Limits

A common enterprise policy is requiring all containers to have resource limits. Apply the second ConstraintTemplate:

```bash
oc apply -f manifests/constraint-template-require-limits.yaml
```

Apply the Constraint targeting the `pod-security-demo` namespace:

```bash
oc apply -f manifests/constraint-require-limits.yaml
```

Test with a pod that has no resource limits:

```bash
oc apply -f manifests/gatekeeper-test-no-limits-pod.yaml -n pod-security-demo
```

Expected output:

```
Error from server (Forbidden): error when creating "manifests/gatekeeper-test-no-limits-pod.yaml":
admission webhook "validation.gatekeeper.sh" denied the request:
[require-resource-limits] Container "no-limits" does not have resource limits set.
All containers must specify cpu and memory limits.
```

### Step 11: Audit Existing Violations

Gatekeeper can audit existing resources and report violations. Check the constraint status:

```bash
oc get k8sdisallowroot disallow-root-pods -o yaml | grep -A 20 'violations:'
```

This shows any existing pods that violate the policy. Gatekeeper's audit controller periodically scans the cluster and updates violation counts.

```bash
oc get k8srequireresourcelimits require-resource-limits -o yaml | grep -A 20 'violations:'
```

## Verification

Run these commands to confirm everything is working:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc project pod-security-demo

# 1. PSA labels are present on the namespace
oc get namespace pod-security-demo --show-labels | grep pod-security

# 2. Custom SCC exists and is assigned
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc get scc custom-network-v2
oc get scc custom-network-v2 -o jsonpath='{.users}' && echo

# 3. Gatekeeper is running
oc get pods -n gatekeeper-system

# 4. ConstraintTemplates exist
oc get constrainttemplate

# 5. Constraints are active
oc get k8sdisallowroot
oc get k8srequireresourcelimits

# 6. A root pod is rejected by Gatekeeper
oc apply -f manifests/gatekeeper-test-root-pod.yaml -n pod-security-demo 2>&1 | grep "denied"

# 7. A pod without limits is rejected
oc apply -f manifests/gatekeeper-test-no-limits-pod.yaml -n pod-security-demo 2>&1 | grep "denied"

# 8. The non-root pod is running
oc get pod test-nonroot -n pod-security-demo
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Primary pod security | PSA namespace labels (3 profiles) | SCCs bound to service accounts (8+ built-in) |
| Default security posture | Permissive (no PSA labels by default) | Restrictive (`restricted-v2` SCC enforced) |
| PSA support | Native, primary mechanism since K8s 1.25 | Supported but secondary to SCCs; labels auto-synced |
| Custom security profiles | Not possible with PSA alone | Custom SCCs with fine-grained controls |
| Policy enforcement (beyond built-in) | Install Gatekeeper/Kyverno yourself | Install Gatekeeper/Kyverno (same process, works on OpenShift) |
| Policy language | Rego (Gatekeeper) or YAML (Kyverno) | Same -- these are K8s-native tools |
| SCC-equivalent granularity | Requires Gatekeeper/Kyverno to match | Built-in with SCCs |
| Audit trail | PSA audit mode, Gatekeeper audit | PSA audit + SCC annotations on pods + Gatekeeper audit |

## Key Takeaways

- **SCCs are OpenShift's primary enforcement mechanism; PSA is a compatibility layer.** OpenShift auto-synchronizes PSA labels based on available SCCs, so you get both systems working together without manual configuration.
- **Custom SCCs bridge the gap between built-in profiles.** When the eight default SCCs do not match your workload requirements, create a custom SCC with exactly the capabilities you need -- no more, no less.
- **Gatekeeper and Kyverno extend policy enforcement beyond pod security.** SCCs control what a pod can do at the OS level; Gatekeeper lets you enforce arbitrary business rules (required labels, approved registries, mandatory resource limits) across any Kubernetes resource.
- **Defense in depth: use SCCs, PSA, and Gatekeeper together.** SCCs enforce the security baseline, PSA provides audit logging in a K8s-standard format, and Gatekeeper adds custom organizational policies. These layers complement each other.
- **Always test policies in `warn` or `dryrun` mode first.** Gatekeeper supports `enforcementAction: dryrun` so you can see what would be blocked before actually denying requests in production.

## Cleanup

```bash
# Delete Gatekeeper constraints and templates
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc delete k8sdisallowroot disallow-root-pods
oc delete k8srequireresourcelimits require-resource-limits
oc delete constrainttemplate k8sdisallowroot
oc delete constrainttemplate k8srequireresourcelimits

# Remove Gatekeeper
oc delete -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/v3.16.0/deploy/gatekeeper.yaml

# Remove custom SCC and its binding
oc adm policy remove-scc-from-user custom-network-v2 -z network-app-sa -n pod-security-demo
oc delete scc custom-network-v2

# Delete the test project (cleans up all resources in the namespace)
oc delete project pod-security-demo
```

## Next Steps

In **L2-M5.3 -- Secrets Management**, you will learn how to go beyond basic Kubernetes Secrets with Sealed Secrets, the External Secrets Operator, and HashiCorp Vault integration. These tools address a critical gap: Kubernetes Secrets are base64-encoded (not encrypted), and managing them securely in GitOps workflows requires specialized tooling.
