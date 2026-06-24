# L2-M4.1 — Egress & Ingress Control

**Level:** Practitioner
**Duration:** 30 min

## Overview

In Kubernetes, controlling outbound (egress) traffic is limited to basic NetworkPolicy rules that filter by IP CIDR and port -- you cannot filter by DNS name, and there is no native way to assign a stable source IP for outbound connections. OpenShift extends egress control significantly with three purpose-built resources: EgressFirewall for namespace-level outbound filtering (including DNS-based rules), EgressIP for assigning stable source IP addresses to a namespace's outbound traffic, and EgressRouter for proxying traffic through a dedicated pod. In this lesson you will create EgressFirewall rules to restrict what external services your pods can reach, assign an EgressIP so external systems see a predictable source address, and understand when EgressRouter is appropriate.

## Prerequisites

- Completed: L1-M4 (Networking & Routes) -- especially L1-M4.4 on Network Policies
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI installed and logged in
- Cluster-admin access for EgressIP configuration (log in as `kubeadmin` for those steps)
- OVN-Kubernetes CNI (default on OpenShift 4.x)

## K8s Context

In vanilla Kubernetes, egress control comes from NetworkPolicy objects with `policyTypes: ["Egress"]`. These policies let you:

- Allow or deny traffic to specific CIDR ranges.
- Restrict egress to certain ports.
- Select which pods the policy applies to via `podSelector`.

However, Kubernetes NetworkPolicy has significant limitations for egress:

1. **No DNS-based filtering.** You cannot write "allow traffic to `api.github.com`" -- you must know and maintain the IP ranges.
2. **No stable source IP.** Outbound traffic uses the node's IP, which changes if the pod is rescheduled. External firewalls cannot reliably allow-list your cluster.
3. **No namespace-level egress policy.** NetworkPolicy targets pods, not the entire namespace.
4. **CNI-dependent.** Not all CNI plugins fully implement egress rules.

If you have dealt with enterprise firewalls requiring a known source IP from your Kubernetes workloads, you know the pain: you end up NATing through a dedicated proxy or maintaining a wide IP allow-list covering all your nodes. OpenShift solves these problems natively.

## Concepts

### EgressFirewall

An EgressFirewall is a namespace-scoped resource that controls which external hosts pods in that namespace can connect to. It is evaluated **before** Kubernetes NetworkPolicy and applies to all pods in the namespace.

Key capabilities:
- **CIDR-based rules**: allow or deny traffic to specific IP ranges.
- **DNS-based rules**: allow or deny traffic to specific domain names (e.g., `api.github.com`, `*.redhat.com`). The OVN-Kubernetes CNI resolves these names and maintains the rules as IPs change.
- **Port filtering**: restrict which ports are allowed per rule.
- **Ordered evaluation**: rules are processed in order; the first match wins.
- **One per namespace**: exactly one EgressFirewall named `default` is allowed per namespace.

The EgressFirewall runs at the network level (OVN/OVS), so it is enforced regardless of what is running inside the pod. Applications cannot bypass it.

> **API:** The resource is `k8s.ovn.org/v1 EgressFirewall` on OpenShift 4.x with OVN-Kubernetes.

### EgressIP

An EgressIP assigns one or more stable IP addresses to all outbound traffic from pods in selected namespaces. When a pod connects to an external service, the external service sees the EgressIP instead of the node's IP.

Key characteristics:
- **Namespace-scoped via label selectors**: you label a namespace and reference that label in the EgressIP spec.
- **Node assignment**: the EgressIP must live on a node labeled with `k8s.ovn.org/egress-assignable`. The OVN-Kubernetes CNI automatically assigns the IP to a suitable node.
- **High availability**: if the hosting node goes down, the EgressIP fails over to another labeled node (requires multiple labeled nodes).
- **Multiple IPs**: you can specify multiple egress IPs for load distribution across nodes.

This is essential in enterprise environments where external firewalls, SaaS APIs, or partner networks require allow-listing by source IP.

### EgressRouter

An EgressRouter is a pod that acts as a bridge between the cluster's SDN and an external system. It is assigned a secondary IP on the node's physical network and forwards traffic from pods to external destinations. There are two modes:

- **Redirect mode**: all traffic to specific external IPs is redirected through the router pod.
- **HTTP proxy mode**: the router pod runs an HTTP proxy (Squid) that pods use explicitly.

EgressRouter is more complex to configure than EgressFirewall or EgressIP and is typically used when you need fine-grained per-connection control or when the external network topology requires a dedicated proxy. For most use cases, EgressFirewall + EgressIP is sufficient, so this lesson focuses on those and covers EgressRouter conceptually.

## Step-by-Step

### Step 1: Create a Project for Egress Testing

Log in and create a dedicated project for this lesson.

```bash
# Log in as developer for most steps
oc login -u developer -p developer https://api.crc.testing:6443

# Create the lesson project
oc new-project egress-demo
```

Expected output:
```
Now using project "egress-demo" on server "https://api.crc.testing:6443".
```

### Step 2: Deploy a Test Pod

Deploy a pod you can exec into to test outbound connectivity. We use Red Hat's UBI (Universal Base Image) which is compatible with the `restricted` SCC.

```bash
oc apply -f manifests/test-pod.yaml
```

```yaml
# manifests/test-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: egress-test
  labels:
    app: egress-test
    tutorial-level: "2"
    tutorial-module: "M4"
spec:
  containers:
    - name: egress-test
      image: registry.access.redhat.com/ubi9/ubi-minimal:latest
      command:
        - sleep
        - "3600"
      resources:
        requests:
          cpu: 100m
          memory: 64Mi
        limits:
          cpu: 200m
          memory: 128Mi
  restartPolicy: Never
```

Wait for the pod to be running:

```bash
oc wait --for=condition=Ready pod/egress-test --timeout=120s
```

Expected output:
```
pod/egress-test condition met
```

### Step 3: Verify Default Egress Behavior (No Restrictions)

Before applying any firewall rules, confirm the pod can reach external services:

```bash
# Test connectivity to an external HTTPS service
oc exec egress-test -- curl -s -o /dev/null -w "%{http_code}" https://api.github.com

# Test connectivity to another external site
oc exec egress-test -- curl -s -o /dev/null -w "%{http_code}" https://httpbin.org/get
```

Expected output (both should succeed):
```
200
200
```

Note the source IP that external services see:

```bash
# Check what source IP external services see
oc exec egress-test -- curl -s https://httpbin.org/ip
```

Expected output (the IP will be your node's external IP):
```json
{
  "origin": "203.0.113.42"
}
```

### Step 4: Apply an EgressFirewall (Allow-List Approach)

Now apply a restrictive EgressFirewall that only allows DNS and HTTPS traffic to specific domains.

> **Important:** You need to be a project admin or cluster admin to create EgressFirewall resources.

```bash
oc apply -f manifests/egressfirewall-allow-dns-http.yaml
```

```yaml
# manifests/egressfirewall-allow-dns-http.yaml
apiVersion: k8s.ovn.org/v1
kind: EgressFirewall
metadata:
  name: default
  labels:
    app: egress-demo
    tutorial-level: "2"
    tutorial-module: "M4"
spec:
  egress:
    # Rule 1: Allow DNS resolution
    - type: Allow
      to:
        cidrSelector: 0.0.0.0/0
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # Rule 2: Allow HTTPS to GitHub API
    - type: Allow
      to:
        dnsName: api.github.com
      ports:
        - protocol: TCP
          port: 443
    # Rule 3: Allow HTTPS to Red Hat registries
    - type: Allow
      to:
        dnsName: "*.redhat.com"
      ports:
        - protocol: TCP
          port: 443
    # Rule 4: Deny everything else
    - type: Deny
      to:
        cidrSelector: 0.0.0.0/0
```

Verify the EgressFirewall was created:

```bash
oc get egressfirewall
```

Expected output:
```
NAME      EGRESSFIREWALL STATUS
default   EgressFirewall Rules applied
```

### Step 5: Test the EgressFirewall Rules

Test that allowed traffic still works and blocked traffic is denied:

```bash
# This should SUCCEED — api.github.com is allowed
oc exec egress-test -- curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://api.github.com

# This should FAIL — httpbin.org is not in the allow list
oc exec egress-test -- curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://httpbin.org/get
```

Expected output:
```
200
000
```

The `000` (or a connection timeout/refused error) confirms the EgressFirewall is blocking traffic to destinations not in the allow list. The pod cannot reach `httpbin.org` but can still reach `api.github.com`.

```bash
# Verify DNS still works (allowed by Rule 1)
oc exec egress-test -- nslookup httpbin.org
```

Expected output (DNS resolves, but TCP connection would be blocked):
```
Server:    172.30.0.10
Address:   172.30.0.10#53

Non-authoritative answer:
Name:      httpbin.org
Address:   52.XX.XX.XX
```

### Step 6: Explore the Deny-List Approach

Delete the current EgressFirewall and apply a deny-list variant that blocks specific ranges instead:

```bash
# Delete the existing firewall (only one "default" allowed per namespace)
oc delete egressfirewall default

# Apply the deny-list approach
oc apply -f manifests/egressfirewall-deny-ranges.yaml
```

```yaml
# manifests/egressfirewall-deny-ranges.yaml
apiVersion: k8s.ovn.org/v1
kind: EgressFirewall
metadata:
  name: default
spec:
  egress:
    # Block cloud provider metadata service (security best practice)
    - type: Deny
      to:
        cidrSelector: 169.254.169.254/32
    # Block internal corporate range
    - type: Deny
      to:
        cidrSelector: 10.0.0.0/8
    # Allow everything else
    - type: Allow
      to:
        cidrSelector: 0.0.0.0/0
```

Test that the metadata service is blocked but general internet access works:

```bash
# This should SUCCEED — general internet is allowed
oc exec egress-test -- curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://httpbin.org/get

# This should FAIL — metadata service is blocked
oc exec egress-test -- curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://169.254.169.254/latest/meta-data/
```

Expected output:
```
200
000
```

> **Security tip:** Blocking the cloud metadata service (169.254.169.254) is a well-known security hardening step. On cloud providers (AWS, GCP, Azure), this endpoint exposes instance credentials. Even on CRC, applying this rule is good practice for production-ready manifests.

### Step 7: Configure EgressIP for Stable Source Addresses

EgressIP requires cluster-admin privileges. Switch to `kubeadmin`:

```bash
# Switch to cluster-admin
oc login -u kubeadmin -p $(cat ~/.crc/machines/crc/kubeadmin-password) https://api.crc.testing:6443
```

First, label the node to host egress IP addresses:

```bash
# In CRC there is only one node — label it as egress-assignable
NODE=$(oc get nodes -o jsonpath='{.items[0].metadata.name}')
oc label node "$NODE" k8s.ovn.org/egress-assignable=""
```

Expected output:
```
node/crc-xxxx labeled
```

Next, label the namespace so the EgressIP selector matches it:

```bash
oc label namespace egress-demo egress-ip=demo
```

Now apply the EgressIP resource:

```bash
oc apply -f manifests/egressip.yaml
```

```yaml
# manifests/egressip.yaml
apiVersion: k8s.ovn.org/v1
kind: EgressIP
metadata:
  name: egress-demo-ip
  labels:
    app: egress-demo
    tutorial-level: "2"
    tutorial-module: "M4"
spec:
  egressIPs:
    - 192.168.126.100
  namespaceSelector:
    matchLabels:
      egress-ip: "demo"
```

Verify the EgressIP assignment:

```bash
oc get egressip egress-demo-ip -o yaml
```

Look for the `status` section, which shows which node the IP was assigned to:

```yaml
status:
  items:
    - egressIP: 192.168.126.100
      node: crc-xxxx
```

> **CRC limitation:** On CRC (single-node), the EgressIP must be in the node's subnet (typically `192.168.126.0/24`). In a production cluster with multiple worker nodes, the EgressIP fails over between labeled nodes automatically. The specific IP (`192.168.126.100`) may need adjustment for your CRC setup -- check your node's subnet with `oc get node -o jsonpath='{.items[0].status.addresses}'`.

### Step 8: Verify the EgressIP

Switch back to the developer user and test that outbound traffic now uses the assigned EgressIP:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc project egress-demo

# Check the source IP as seen externally
oc exec egress-test -- curl -s https://httpbin.org/ip
```

Expected output (if EgressIP is correctly assigned and routable):
```json
{
  "origin": "192.168.126.100"
}
```

The source IP is now the EgressIP you configured instead of the node's primary IP. External firewalls can now reliably allow-list this single IP address.

### Step 9: Compare with Kubernetes NetworkPolicy (Optional)

For reference, review how a standard Kubernetes NetworkPolicy handles egress. This manifest is included in `manifests/networkpolicy-egress-restrict.yaml`:

```yaml
# manifests/networkpolicy-egress-restrict.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: restrict-egress
spec:
  podSelector:
    matchLabels:
      app: egress-test
  policyTypes:
    - Egress
  egress:
    - ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - ports:
        - protocol: TCP
          port: 443
```

This K8s NetworkPolicy allows DNS and HTTPS to **any** destination. It cannot:
- Filter by DNS name (only by IP CIDR).
- Apply at the namespace level (must use podSelector).
- Assign a stable source IP.

You can apply it alongside the EgressFirewall -- they are complementary. The EgressFirewall applies at the namespace level first, then the NetworkPolicy applies per-pod:

```bash
oc apply -f manifests/networkpolicy-egress-restrict.yaml
```

## Verification

Run these checks to confirm everything is working:

```bash
# 1. EgressFirewall is applied
oc get egressfirewall
# Expected: NAME=default, STATUS=EgressFirewall Rules applied

# 2. EgressIP is assigned (requires cluster-admin to view)
oc get egressip egress-demo-ip 2>/dev/null || echo "Switch to kubeadmin to verify EgressIP"

# 3. Test pod is running
oc get pod egress-test
# Expected: STATUS=Running

# 4. Egress rules are enforced (if using allow-list firewall)
oc exec egress-test -- curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://api.github.com
# Expected: 200 (allowed)

# 5. Verify source IP (if EgressIP is configured and routable)
oc exec egress-test -- curl -s https://httpbin.org/ip
# Expected: Shows the EgressIP address
```

**Web Console verification:**

1. Navigate to **Networking** in the Administrator perspective.
2. Check **EgressFirewall** entries under your project.
3. Under **Networking > EgressIP**, verify the IP assignment and node binding.

## Troubleshooting

**EgressFirewall shows "EgressFirewall Rules applied" but traffic is not blocked:**
- Rules are evaluated in order. Ensure your `Deny` rule comes after specific `Allow` rules, or that a broader `Allow` rule earlier in the list is not matching first.
- Verify the pod is in the correct namespace. EgressFirewall is namespace-scoped.
- Check that you are using the OVN-Kubernetes CNI: `oc get network.operator cluster -o jsonpath='{.spec.defaultNetwork.type}'` should return `OVNKubernetes`.

**"only one egressfirewall object is allowed per namespace":**
- Delete the existing EgressFirewall before creating a new one: `oc delete egressfirewall default`.

**EgressIP not working (outbound IP does not change):**
- Verify nodes are labeled: `oc get nodes -l k8s.ovn.org/egress-assignable`.
- Verify the namespace has the matching label: `oc get namespace egress-demo --show-labels`.
- Check the EgressIP status: `oc get egressip egress-demo-ip -o yaml` -- the `status.items` field must show a node assignment.
- On CRC, the EgressIP must be in the node's subnet. Check with: `oc get hostsubnet` (OpenShift SDN) or `oc get nodes -o jsonpath='{.items[0].status.addresses}'` (OVN-Kubernetes).

**DNS-based rules not resolving:**
- OVN-Kubernetes resolves DNS names periodically. There may be a short delay after applying rules before DNS-based entries take effect.
- Wildcard patterns (`*.redhat.com`) must use the `dnsName` field, not `cidrSelector`.

**curl returns 000 or "connection refused" for blocked destinations:**
- This is expected behavior. A `000` HTTP code from curl means the TCP connection was refused or timed out, which is exactly what the EgressFirewall does.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Egress filtering | NetworkPolicy with CIDR and port rules | EgressFirewall: CIDR + DNS-based rules, namespace-scoped |
| DNS-based rules | Not supported natively | Supported via `dnsName` and wildcard patterns |
| Policy scope | Per-pod (via podSelector) | Per-namespace (EgressFirewall) + per-pod (NetworkPolicy) |
| Stable source IP | Not supported natively; requires custom NAT/proxy | EgressIP: assign fixed IPs to namespaces |
| Source IP failover | N/A | EgressIP fails over between labeled nodes |
| Egress proxy | Run your own proxy pod | EgressRouter provides managed proxy with dedicated IP |
| Metadata service blocking | Manual NetworkPolicy CIDR rule | EgressFirewall CIDR rule (same, but with namespace scope) |
| Default posture | Allow all (unless NetworkPolicy is created) | Allow all by default; EgressFirewall adds namespace-level deny |
| Rule evaluation | All matching policies are ANDed | EgressFirewall: first match wins (ordered rules) |

## Key Takeaways

- **EgressFirewall** provides namespace-level outbound traffic control with support for both CIDR-based and DNS-based filtering -- something Kubernetes NetworkPolicy cannot do natively.
- **EgressIP** assigns stable source IP addresses to a namespace's outbound traffic, solving the common enterprise problem of external firewall allow-listing.
- Rules are evaluated in order (first match wins), so place specific Allow rules before a broad Deny rule in allow-list configurations.
- EgressFirewall and Kubernetes NetworkPolicy are complementary: the firewall applies at the namespace level, then NetworkPolicy adds per-pod granularity.
- Always block the cloud metadata service (`169.254.169.254/32`) in production as a security hardening measure.

## Cleanup

Remove all resources created in this lesson:

```bash
# Run the cleanup script
./scripts/cleanup.sh

# Or manually:
oc delete pod egress-test --ignore-not-found
oc delete egressfirewall default --ignore-not-found
oc delete networkpolicy restrict-egress --ignore-not-found

# These require cluster-admin:
oc login -u kubeadmin -p $(cat ~/.crc/machines/crc/kubeadmin-password) https://api.crc.testing:6443
oc delete egressip egress-demo-ip --ignore-not-found
NODE=$(oc get nodes -o jsonpath='{.items[0].metadata.name}')
oc label node "$NODE" k8s.ovn.org/egress-assignable-
oc delete project egress-demo
```

## Next Steps

In **L2-M4.2 -- Multi-Cluster Networking**, you will explore Submariner for cross-cluster service discovery and communication. While this lesson focused on controlling traffic leaving a single cluster, the next lesson addresses connecting multiple OpenShift clusters and enabling workloads to communicate across cluster boundaries -- essential for hybrid cloud and disaster recovery architectures.
