# L1-M4.4 — Network Policies

**Level:** Foundations
**Duration:** 20 min

## Overview

In Kubernetes, NetworkPolicy resources let you control pod-to-pod traffic at the IP and port level -- but they only work if your CNI plugin supports them, and by default all traffic is allowed. OpenShift ships with OVN-Kubernetes (or OpenShift SDN) which enforces NetworkPolicy out of the box. In multi-tenant mode, OpenShift defaults to deny-by-default between projects, giving you isolation without writing a single policy. This lesson teaches you how to write NetworkPolicy manifests that deny all ingress, allow traffic from specific pods, allow traffic from specific namespaces, and introduces OpenShift's EgressFirewall CRD for controlling outbound traffic.

## Prerequisites

- Completed: L1-M4.1 (Services & Pod Networking)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`
- A project created for this lesson (we will create one in Step 1)

## K8s Context

You already know Kubernetes NetworkPolicy. It uses label selectors to define which pods can talk to which other pods, on which ports. A few things to remember about the K8s model:

- **No policy = allow all**: By default, every pod can reach every other pod in the cluster, across all namespaces.
- **CNI-dependent**: NetworkPolicy is part of the K8s API, but it only works if the CNI plugin supports it. Flannel (the default in many clusters) does not enforce them. Calico, Cilium, and Weave do.
- **Additive**: Policies are unioned -- you cannot write a "deny" rule. Instead, selecting a pod with any policy implicitly denies all traffic not explicitly allowed by that policy.
- **Egress control is limited**: K8s NetworkPolicy can restrict egress by IP CIDR and port, but there is no way to filter by DNS name or apply cluster-wide egress rules.

## Concepts

### NetworkPolicy on OpenShift

Standard Kubernetes NetworkPolicy works identically on OpenShift -- the same `apiVersion: networking.k8s.io/v1` manifests you use in vanilla K8s apply without modification. The key difference is that OpenShift's CNI (OVN-Kubernetes) always enforces them. You never need to wonder "does my CNI support this?" -- it does.

### Multi-Tenant Network Isolation

OpenShift can run in multi-tenant mode with the OpenShift SDN plugin, where each project (namespace) is isolated by default -- pods in one project cannot reach pods in another project unless explicitly allowed. With OVN-Kubernetes (the default in OpenShift 4.12+), you achieve the same isolation by applying a deny-all NetworkPolicy to each namespace. Many organizations apply a default deny-all policy to every new project via a project template.

### How Deny-All Works

In Kubernetes and OpenShift, the moment you apply any NetworkPolicy that selects a pod, all traffic to that pod is denied except what the policy explicitly allows. A policy with an empty `ingress: []` array selects all pods and allows nothing -- this is the deny-all pattern.

### EgressFirewall -- OpenShift's Egress Control

Standard K8s NetworkPolicy can restrict egress by IP CIDR, but it cannot filter by DNS name and it applies per-pod. OpenShift adds the **EgressFirewall** CRD (`k8s.ovn.org/v1`), which provides namespace-level egress rules that can match by:

- **IP CIDR**: Allow or deny traffic to specific IP ranges
- **DNS name**: Allow or deny traffic to specific hostnames (e.g., `api.example.com`)

This is valuable for compliance scenarios where workloads must only connect to approved external services.

## Step-by-Step

### Step 1: Create a Project and Deploy Test Workloads

Create a dedicated project and deploy two simple applications so we can test network policies between them:

```bash
oc new-project l1-m4-netpol --display-name="L1-M4: Network Policies"
```

Deploy a web application and a client pod:

```bash
oc apply -f manifests/deployment-web.yaml
oc apply -f manifests/service-web.yaml
oc apply -f manifests/deployment-client.yaml
```

Wait for the pods to be ready:

```bash
oc get pods -w
```

Expected output (wait until both show `Running`):
```
NAME                          READY   STATUS    RESTARTS   AGE
client-app-7d8f9b6c5-abc12   1/1     Running   0          15s
web-app-5c4d3e2f1-xyz34      1/1     Running   0          20s
```

Press `Ctrl+C` to stop watching once both pods are running.

Verify that the client can reach the web app (no policies applied yet):

```bash
oc exec deploy/client-app -- curl -s --max-time 5 http://web-app:8080
```

Expected output:
```
Hello from web-app!
```

This confirms that by default, pods within the same project can communicate freely -- just like vanilla Kubernetes.

### Step 2: Apply a Deny-All Ingress Policy

Now apply a policy that denies all incoming traffic to every pod in the namespace:

```bash
oc apply -f manifests/netpol-deny-all-ingress.yaml
```

Test connectivity again:

```bash
oc exec deploy/client-app -- curl -s --max-time 5 http://web-app:8080
```

Expected output (the connection will time out):
```
curl: (28) Connection timed out after 5001 milliseconds
command terminated with exit code 28
```

The deny-all policy selected all pods (via an empty `podSelector: {}`) and specified an empty `ingress: []` list, which means no ingress traffic is allowed to any pod.

Let's examine the policy:

```bash
oc get networkpolicy deny-all-ingress -o yaml
```

Key fields:
```yaml
spec:
  podSelector: {}        # Selects ALL pods in the namespace
  policyTypes:
    - Ingress            # Only affects ingress (incoming) traffic
  ingress: []            # Empty = no ingress allowed
```

### Step 3: Allow Traffic from Specific Pods

In practice, you want to deny all by default and then selectively allow traffic. Apply a policy that allows the client app (identified by its label) to reach the web app:

```bash
oc apply -f manifests/netpol-allow-client-to-web.yaml
```

Test connectivity from the allowed client:

```bash
oc exec deploy/client-app -- curl -s --max-time 5 http://web-app:8080
```

Expected output:
```
Hello from web-app!
```

The client can reach the web app again because the new policy explicitly allows ingress from pods with the label `app: client-app` to pods with the label `app: web-app` on port 8080.

To verify that the deny-all still blocks other traffic, deploy a second client without the allowed label:

```bash
oc run test-pod --image=busybox --restart=Never -- sleep 3600
```

Wait for it to be ready, then test:

```bash
oc wait --for=condition=Ready pod/test-pod --timeout=60s
oc exec test-pod -- wget -qO- --timeout=5 http://web-app:8080
```

Expected output (blocked):
```
wget: download timed out
command terminated with exit code 1
```

The `test-pod` does not have the `app: client-app` label, so the deny-all policy blocks it.

Clean up the test pod:

```bash
oc delete pod test-pod
```

### Step 4: Allow Traffic from a Specific Namespace

In multi-tenant clusters, you often need to allow traffic from another namespace -- for example, allowing a monitoring namespace to scrape metrics from your application. Apply a policy that allows ingress from any pod in a namespace labeled `purpose: monitoring`:

```bash
oc apply -f manifests/netpol-allow-from-namespace.yaml
```

Examine the policy:

```bash
oc get networkpolicy allow-from-monitoring -o yaml
```

Key fields:
```yaml
spec:
  podSelector:
    matchLabels:
      app: web-app              # Applies to the web-app pods
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              purpose: monitoring   # Allow from namespaces with this label
      ports:
        - protocol: TCP
          port: 8080
```

To test this, you would need a second namespace labeled `purpose: monitoring` with a pod that tries to reach the web app. The namespace label must be set by a cluster admin:

```bash
# These commands require cluster-admin (oc login as kubeadmin in CRC)
oc new-project monitoring-test
oc label namespace monitoring-test purpose=monitoring
oc run monitor-pod --image=busybox --restart=Never -- sleep 3600
oc wait --for=condition=Ready pod/monitor-pod -n monitoring-test --timeout=60s
oc exec -n monitoring-test monitor-pod -- wget -qO- --timeout=5 http://web-app.l1-m4-netpol.svc.cluster.local:8080
```

Expected output:
```
Hello from web-app!
```

Clean up the monitoring test namespace:

```bash
oc delete project monitoring-test
```

Switch back to our lesson project:

```bash
oc project l1-m4-netpol
```

### Step 5: Apply an EgressFirewall (OpenShift-Specific)

Standard K8s NetworkPolicy handles egress by IP CIDR, but OpenShift's EgressFirewall CRD lets you create namespace-wide egress rules that can match DNS names. Apply an EgressFirewall that allows traffic only to specific external destinations:

```bash
oc apply -f manifests/egressfirewall.yaml
```

Examine the EgressFirewall:

```bash
oc get egressfirewall default -o yaml
```

Key fields:
```yaml
spec:
  egress:
    - type: Allow
      to:
        cidrSelector: 10.0.0.0/8       # Allow internal cluster traffic
    - type: Allow
      to:
        dnsName: api.github.com         # Allow GitHub API by DNS name
    - type: Deny
      to:
        cidrSelector: 0.0.0.0/0         # Deny everything else
```

> **Note:** EgressFirewall requires the OVN-Kubernetes network plugin (default in OpenShift 4.12+). Only one EgressFirewall resource is allowed per namespace, and it must be named `default`. The rules are evaluated in order -- the first match wins.

> **Important:** EgressFirewall is a cluster-level feature that may require admin privileges to create, depending on your cluster's RBAC configuration. On CRC, the `developer` user may not have permission -- use `kubeadmin` if needed.

### Step 6: Review All Active Policies

List all NetworkPolicies in the current namespace to see the full picture:

```bash
oc get networkpolicy
```

Expected output:
```
NAME                     POD-SELECTOR   AGE
deny-all-ingress         <none>         10m
allow-client-to-web      app=web-app    8m
allow-from-monitoring    app=web-app    5m
```

Check for EgressFirewall:

```bash
oc get egressfirewall
```

Expected output:
```
NAME      EGRESSFIREWALL STATUS
default   EgressFirewall Rules applied
```

Remember that NetworkPolicies are additive. The web-app pods are affected by all three policies:
1. `deny-all-ingress` -- denies all ingress by default
2. `allow-client-to-web` -- allows ingress from `client-app` pods on port 8080
3. `allow-from-monitoring` -- allows ingress from namespaces labeled `purpose: monitoring` on port 8080

Traffic is allowed if **any** policy permits it.

## Verification

Run these commands to verify your setup is working correctly:

```bash
# 1. Confirm both app pods are running
oc get pods -l 'app in (web-app, client-app)'
```

Expected output:
```
NAME                          READY   STATUS    RESTARTS   AGE
client-app-7d8f9b6c5-abc12   1/1     Running   0          15m
web-app-5c4d3e2f1-xyz34      1/1     Running   0          15m
```

```bash
# 2. Confirm client-app CAN reach web-app (allowed by policy)
oc exec deploy/client-app -- curl -s --max-time 5 http://web-app:8080
```

Expected output: `Hello from web-app!`

```bash
# 3. Confirm an unlabeled pod CANNOT reach web-app (blocked by deny-all)
oc run verify-pod --image=busybox --restart=Never -- sleep 60
oc wait --for=condition=Ready pod/verify-pod --timeout=60s
oc exec verify-pod -- wget -qO- --timeout=5 http://web-app:8080 2>&1 || true
oc delete pod verify-pod
```

Expected output: `wget: download timed out`

```bash
# 4. List all network policies
oc get networkpolicy
```

```bash
# 5. List EgressFirewall
oc get egressfirewall
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| NetworkPolicy support | Depends on CNI plugin (Calico, Cilium, etc.) | Always enforced (OVN-Kubernetes built-in) |
| Default traffic policy | Allow all (no isolation) | Allow all within project; deny between projects in multi-tenant mode |
| NetworkPolicy API | `networking.k8s.io/v1` | Same API, fully compatible |
| Egress control | NetworkPolicy with IP CIDR only | NetworkPolicy + EgressFirewall CRD (supports DNS names) |
| Namespace isolation | Must manually apply deny-all policies | Can be enforced via project templates or multi-tenant SDN mode |
| Per-namespace egress rules | Not available | EgressFirewall CRD (one per namespace, named `default`) |
| DNS-based egress filtering | Not supported | Supported via EgressFirewall `dnsName` field |
| CNI plugin installation | Manual (install Calico, Cilium, etc.) | Pre-installed and managed by the cluster |

## Key Takeaways

- **Standard K8s NetworkPolicy works unchanged on OpenShift**: The same `networking.k8s.io/v1` manifests you use in vanilla Kubernetes apply on OpenShift with no modifications. The difference is that OpenShift's CNI always enforces them -- you never need to worry about CNI plugin compatibility.
- **Start with deny-all, then allow selectively**: The recommended pattern is to apply a deny-all ingress policy to each namespace and then create specific allow policies for legitimate traffic flows. OpenShift's project templates can automate this for every new project.
- **EgressFirewall adds DNS-based egress control**: Standard K8s NetworkPolicy can only filter egress by IP CIDR. OpenShift's EgressFirewall CRD lets you allow or deny outbound traffic by DNS name, which is essential for compliance scenarios where workloads must only reach approved external services.
- **Policies are additive**: Multiple NetworkPolicies affecting the same pod are unioned. Traffic is allowed if any policy permits it. You cannot write a "deny this specific flow" rule -- you deny everything first, then allow what you need.
- **OpenShift provides namespace isolation out of the box**: In multi-tenant SDN mode, projects are isolated by default. With OVN-Kubernetes, you achieve the same result by applying deny-all policies, which can be automated via project templates.

## Cleanup

Remove all resources created in this lesson:

```bash
# Delete the entire project (removes all resources within it)
oc delete project l1-m4-netpol
```

If you prefer to delete resources selectively:

```bash
# Delete network policies
oc delete networkpolicy deny-all-ingress allow-client-to-web allow-from-monitoring

# Delete EgressFirewall
oc delete egressfirewall default

# Delete workloads
oc delete all -l tutorial-level=1,tutorial-module=M4
```

## Next Steps

In **L1-M5.1 -- Persistent Storage Basics**, you will learn how OpenShift handles persistent storage. You already know PersistentVolumes, PersistentVolumeClaims, and StorageClasses from Kubernetes -- the concepts are identical on OpenShift. You will explore the default storage provided by CRC, dynamic provisioning, and how to attach persistent storage to your workloads.
