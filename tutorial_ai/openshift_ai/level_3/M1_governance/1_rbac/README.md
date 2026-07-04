# L3-M1.1 -- RBAC and Network Policies for AI Workloads

**Level:** Expert
**Duration:** 1 hour

## Overview

In Levels 1 and 2 you deployed models, built pipelines, and ran agents -- all as a single user with broad permissions. In production, multiple teams share an OpenShift AI platform: platform admins manage infrastructure, data scientists build and deploy models, and automated agents consume inference endpoints. This lesson configures role-based access control (RBAC) and network policies to enforce least-privilege access across these personas. You will create custom roles scoped to OpenShift AI resources, bind them to users and service accounts, lock down model serving endpoints with NetworkPolicies, and verify the audit trail.

## Prerequisites

- Completed: [L2-M6.4 -- Spark on OpenShift AI](../../level_2/M6_distributed/4_spark/)
- OpenShift AI cluster with the Gemma4-e4b model deployed in namespace `gemma-model` (from [L1-M2.2](../../level_1/M2_model_serving/2_deploying_gemma/))
- `oc` CLI authenticated to the cluster with `cluster-admin` privileges (required for creating ClusterRoles and viewing audit logs)
- At least two test users available (e.g., `admin-user`, `scientist-user`) or the ability to create them

Verify your cluster-admin access:

```bash
oc auth can-i create clusterrole
```

Expected output:

```
yes
```

Verify the Gemma model is running:

```bash
oc get inferenceservice gemma-4-e4b -n gemma-model
```

Expected output:

```
NAME          URL                                                  READY   PREV   LATEST   AGE
gemma-4-e4b   https://gemma-4-e4b-gemma-model.apps.example.com     True                    2d
```

## Concepts

### OpenShift AI Role Hierarchy

You already know Kubernetes RBAC: Roles define permissions on API resources, RoleBindings grant those permissions to users or service accounts, and ClusterRoles/ClusterRoleBindings work cluster-wide. OpenShift AI builds a three-tier access model on top of this standard K8s RBAC:

**Tier 1 -- Cluster-level groups:**

| Group | Purpose | How it works |
|-------|---------|--------------|
| `rhods-admins` | Full administrative access to the OpenShift AI dashboard and all Data Science Projects | Members of this group see the Admin panel in the dashboard and can manage cluster-wide settings like serving runtimes, accelerator profiles, and user permissions |
| `rhods-users` | Basic access to the OpenShift AI dashboard | Members can create Data Science Projects and use features within their own projects. If this group is empty, all authenticated users get dashboard access |

These groups are standard OpenShift Groups (the same `user.openshift.io/v1 Group` resource you know from the main OpenShift tutorial). The OpenShift AI dashboard checks group membership to determine what UI elements to show.

**Tier 2 -- Project-level roles:**

When a user creates a Data Science Project through the dashboard, they automatically receive the `admin` role on the underlying OpenShift namespace. They can then add other users with `admin` or `edit` roles. This is standard OpenShift namespace RBAC -- the dashboard just provides a UI wrapper around `RoleBinding` creation.

**Tier 3 -- Model Registry roles:**

Each Model Registry instance automatically creates a set of Roles and Groups scoped to that registry. These control who can register models, update model versions, and promote models between stages. The registry operator manages these resources -- you do not create them manually.

### Why Custom Roles for AI Workloads?

The built-in OpenShift roles (`admin`, `edit`, `view`) operate on standard Kubernetes resources. But OpenShift AI introduces custom resource definitions (CRDs) that these roles know nothing about:

| CRD | API Group | What it controls |
|-----|-----------|-----------------|
| `InferenceService` | `serving.kserve.io` | Model deployments |
| `ServingRuntime` | `serving.kserve.io` | Inference engine configurations |
| `Notebook` | `kubeflow.org` | Workbenches (Jupyter, VS Code) |
| `PipelineRun` | `tekton.dev` | Pipeline executions |
| `ModelRegistry` | `modelregistry.opendatahub.io` | Model registration and versioning |

A user with the standard `edit` role can create Deployments and Services but cannot create an InferenceService or a Notebook. You need custom Roles that explicitly grant permissions on these API groups. In this lesson, you create three roles that represent the typical personas on an AI platform.

### Network Policies for AI Infrastructure

You know NetworkPolicy from Kubernetes -- it defines firewall rules at the pod level. The key difference on OpenShift: the OpenShift SDN (OVN-Kubernetes) enforces NetworkPolicies by default. On vanilla Kubernetes, NetworkPolicy resources are inert unless you install a CNI plugin that supports them (Calico, Cilium, etc.). Many K8s clusters have NetworkPolicy resources that do nothing because the CNI does not enforce them. On OpenShift, they always work.

For AI workloads, network policies address specific security concerns:

1. **Model endpoint isolation** -- not every namespace should be able to call your inference endpoints. A model serving sensitive financial data should only accept requests from authorized applications.
2. **MCP server access control** -- MCP servers provide tool access to AI agents. Without network policies, any pod in the cluster could call the MCP server and invoke tools (database queries, API calls, file operations).
3. **Agent containment** -- AI agents can behave unpredictably. Network policies provide a hard boundary that prevents an agent pod from reaching services it should not access, regardless of what the agent's code attempts to do.

### Default Deny Strategy

The production best practice is to start with a default-deny policy that blocks all ingress traffic to every pod in a namespace, then add explicit allow rules for each legitimate communication path. This is the network equivalent of least-privilege RBAC -- deny everything, then grant specific access.

Without default deny, any new pod deployed into the namespace can receive traffic from anywhere in the cluster. With default deny, a new pod is unreachable until an administrator creates a NetworkPolicy that explicitly allows the traffic it needs.

## Step-by-Step

### Step 1: Create the RBAC Roles

Review the three custom roles in `manifests/rbac-roles.yaml`. Each role is scoped to a different persona:

**ai-platform-admin** -- a ClusterRole for platform administrators who manage all OpenShift AI resources across the cluster. This includes full CRUD on InferenceServices, ServingRuntimes, Notebooks, PipelineRuns, and ModelRegistries.

**ai-data-scientist** -- a Role (namespace-scoped) for data scientists who build and deploy models within their assigned projects. They can create workbenches, deploy models, run pipelines, and register models -- but they cannot modify cluster-level settings like accelerator profiles or cluster-wide serving runtimes.

**ai-agent-consumer** -- a Role (namespace-scoped) for automated agents and consuming applications. They can only read InferenceService metadata (to discover endpoints) and call prediction URLs. They cannot deploy, modify, or delete anything.

Apply the roles:

```bash
oc apply -f manifests/rbac-roles.yaml
```

Expected output:

```
clusterrole.rbac.authorization.k8s.io/ai-platform-admin created
role.rbac.authorization.k8s.io/ai-data-scientist created
role.rbac.authorization.k8s.io/ai-agent-consumer created
```

Verify the ClusterRole was created:

```bash
oc get clusterrole ai-platform-admin
```

Expected output:

```
NAME                AGE
ai-platform-admin   5s
```

Inspect the permissions to confirm they look correct:

```bash
oc describe clusterrole ai-platform-admin
```

Expected output (abbreviated):

```
Name:         ai-platform-admin
Labels:       app=ai-rbac
              tutorial-level=3
              tutorial-module=M1
Annotations:  <none>
PolicyRule:
  Resources                                    Non-Resource URLs  Resource Names  Verbs
  ---------                                    -----------------  --------------  -----
  inferenceservices.serving.kserve.io           []                 []              [*]
  servingruntimes.serving.kserve.io             []                 []              [*]
  notebooks.kubeflow.org                        []                 []              [*]
  pipelineruns.tekton.dev                       []                 []              [*]
  ...
```

Verify the namespace-scoped roles:

```bash
oc get role -n gemma-model
```

Expected output:

```
NAME                  AGE
ai-data-scientist     10s
ai-agent-consumer     10s
```

### Step 2: Create Service Account for Agent Workloads

Before binding roles, create the service account and namespace that the agent consumer will use:

```bash
oc new-project agent-workloads
```

Expected output:

```
Now using project "agent-workloads" on server "https://api.example.com:6443".
```

```bash
oc create serviceaccount agent-sa -n agent-workloads
```

Expected output:

```
serviceaccount/agent-sa created
```

Switch back to the gemma-model namespace:

```bash
oc project gemma-model
```

### Step 3: Bind Roles to Users and Service Accounts

Review `manifests/rbac-rolebindings.yaml`. The bindings assign the three roles to specific subjects:

- `admin-user` receives the `ai-platform-admin` ClusterRole via a ClusterRoleBinding
- `scientist-user` receives the `ai-data-scientist` Role in the `gemma-model` namespace
- `agent-sa` service account in namespace `agent-workloads` receives the `ai-agent-consumer` Role in the `gemma-model` namespace

Apply the bindings:

```bash
oc apply -f manifests/rbac-rolebindings.yaml
```

Expected output:

```
clusterrolebinding.rbac.authorization.k8s.io/ai-platform-admin-binding created
rolebinding.rbac.authorization.k8s.io/ai-data-scientist-binding created
rolebinding.rbac.authorization.k8s.io/ai-agent-consumer-binding created
```

Verify the bindings:

```bash
oc get clusterrolebinding ai-platform-admin-binding
```

Expected output:

```
NAME                        ROLE                              AGE
ai-platform-admin-binding   ClusterRole/ai-platform-admin     5s
```

```bash
oc get rolebinding -n gemma-model
```

Expected output (showing the new bindings alongside any pre-existing ones):

```
NAME                          ROLE                         AGE
ai-data-scientist-binding     Role/ai-data-scientist       10s
ai-agent-consumer-binding     Role/ai-agent-consumer       10s
...
```

### Step 4: Test RBAC Permissions

Use `oc auth can-i` with `--as` impersonation to verify each role's access without switching users. This requires cluster-admin privileges.

**Test the platform admin:**

```bash
# Admin should be able to manage InferenceServices cluster-wide
oc auth can-i create inferenceservices.serving.kserve.io --as=admin-user -n gemma-model
```

Expected output:

```
yes
```

```bash
# Admin should be able to manage ServingRuntimes
oc auth can-i delete servingruntimes.serving.kserve.io --as=admin-user -n gemma-model
```

Expected output:

```
yes
```

**Test the data scientist:**

```bash
# Data scientist should be able to create InferenceServices in their namespace
oc auth can-i create inferenceservices.serving.kserve.io --as=scientist-user -n gemma-model
```

Expected output:

```
yes
```

```bash
# Data scientist should NOT be able to create cluster-scoped resources
oc auth can-i create clusterrole --as=scientist-user
```

Expected output:

```
no
```

**Test the agent consumer:**

```bash
# Agent SA should be able to read InferenceServices (discover endpoints)
oc auth can-i get inferenceservices.serving.kserve.io \
  --as=system:serviceaccount:agent-workloads:agent-sa -n gemma-model
```

Expected output:

```
yes
```

```bash
# Agent SA should NOT be able to create or delete InferenceServices
oc auth can-i create inferenceservices.serving.kserve.io \
  --as=system:serviceaccount:agent-workloads:agent-sa -n gemma-model
```

Expected output:

```
no
```

```bash
# Agent SA should NOT be able to create Notebooks (workbenches)
oc auth can-i create notebooks.kubeflow.org \
  --as=system:serviceaccount:agent-workloads:agent-sa -n gemma-model
```

Expected output:

```
no
```

### Step 5: Configure OpenShift AI Dashboard Access

The RBAC roles you created govern API-level access. The OpenShift AI dashboard uses Groups for its own access control. Set up the cluster-level groups:

```bash
# Create the rhods-admins group and add the admin user
oc adm groups new rhods-admins
oc adm groups add-users rhods-admins admin-user
```

Expected output:

```
group.user.openshift.io/rhods-admins created
group.user.openshift.io/rhods-admins added: "admin-user"
```

```bash
# Create the rhods-users group and add both users
oc adm groups new rhods-users
oc adm groups add-users rhods-users admin-user scientist-user
```

Expected output:

```
group.user.openshift.io/rhods-users created
group.user.openshift.io/rhods-users added: "admin-user" "scientist-user"
```

Verify group membership:

```bash
oc get groups
```

Expected output:

```
NAME           USERS
rhods-admins   admin-user
rhods-users    admin-user, scientist-user
```

With this configuration:
- `admin-user` sees the full Admin panel in the OpenShift AI dashboard
- `scientist-user` can access the dashboard and create Data Science Projects, but cannot see the Admin panel
- `agent-sa` (a service account) does not need dashboard access -- it interacts only via the API

### Step 6: Apply the Default Deny Network Policy

Start with the most restrictive policy: deny all ingress traffic to every pod in the `gemma-model` namespace. After applying this, no pod in the namespace can receive traffic from any source until you add explicit allow rules.

Review `manifests/network-policy-default-deny.yaml`, then apply it:

```bash
oc apply -f manifests/network-policy-default-deny.yaml -n gemma-model
```

Expected output:

```
networkpolicy.networking.k8s.io/default-deny-all-ingress created
```

Verify the policy:

```bash
oc get networkpolicy -n gemma-model
```

Expected output:

```
NAME                       POD-SELECTOR   AGE
default-deny-all-ingress   <none>         5s
```

The `<none>` pod selector means this policy applies to every pod in the namespace. At this point, the Gemma model endpoint is unreachable from anywhere in the cluster.

Test that the model is now blocked (from a pod in a different namespace):

```bash
# Create a temporary debug pod and try to reach the model
oc run test-curl --rm -it --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal \
  -n agent-workloads \
  -- curl -s --connect-timeout 5 \
  http://gemma-4-e4b-predictor.gemma-model.svc.cluster.local:8080/v1/models
```

Expected output (should timeout or be refused):

```
curl: (28) Connection timed out after 5000 milliseconds
pod "test-curl" deleted
```

### Step 7: Apply the Model Serving Network Policy

Now add an explicit allow rule for the model serving pods. This policy permits ingress to predictor pods only from namespaces labeled `access-model-serving: "true"` and from the OpenShift router (so external Routes still work).

Review `manifests/network-policy-model-serving.yaml`, then apply it:

```bash
oc apply -f manifests/network-policy-model-serving.yaml -n gemma-model
```

Expected output:

```
networkpolicy.networking.k8s.io/allow-model-serving-ingress created
```

Label the `agent-workloads` namespace to grant it access:

```bash
oc label namespace agent-workloads access-model-serving=true
```

Expected output:

```
namespace/agent-workloads labeled
```

Verify the label was applied:

```bash
oc get namespace agent-workloads --show-labels | grep access-model
```

Expected output:

```
agent-workloads   Active   5m   access-model-serving=true,...
```

Test that the model is now reachable from the authorized namespace:

```bash
oc run test-curl --rm -it --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal \
  -n agent-workloads \
  -- curl -s --connect-timeout 10 \
  http://gemma-4-e4b-predictor.gemma-model.svc.cluster.local:8080/v1/models
```

Expected output:

```json
{
  "object": "list",
  "data": [
    {
      "id": "gemma-4-e4b",
      "object": "model",
      "created": 1700000000,
      "owned_by": "vllm"
    }
  ]
}
```

Test that the model is still blocked from an unlabeled namespace:

```bash
oc new-project test-unauthorized
oc run test-curl --rm -it --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal \
  -n test-unauthorized \
  -- curl -s --connect-timeout 5 \
  http://gemma-4-e4b-predictor.gemma-model.svc.cluster.local:8080/v1/models
```

Expected output:

```
curl: (28) Connection timed out after 5000 milliseconds
pod "test-curl" deleted
```

The network policy is working: only namespaces with the `access-model-serving: "true"` label can reach the model.

### Step 8: Apply the MCP Server Network Policy

If you have MCP server pods running (from [L2-M2](../../level_2/M2_mcp_deployment/)), apply the MCP network policy to restrict access to only agent pods:

```bash
oc apply -f manifests/network-policy-mcp.yaml -n gemma-model
```

Expected output:

```
networkpolicy.networking.k8s.io/allow-mcp-server-ingress created
```

This policy ensures that only pods labeled `app: ai-agent` can reach pods labeled `app: mcp-server`. All other ingress to MCP server pods is denied (the default-deny policy handles that).

### Step 9: Verify the Complete Network Policy Stack

List all network policies in the namespace:

```bash
oc get networkpolicy -n gemma-model
```

Expected output:

```
NAME                          POD-SELECTOR          AGE
default-deny-all-ingress      <none>                10m
allow-model-serving-ingress   component=predictor   5m
allow-mcp-server-ingress      app=mcp-server        2m
```

Describe the model serving policy to see the full ingress rules:

```bash
oc describe networkpolicy allow-model-serving-ingress -n gemma-model
```

Expected output:

```
Name:         allow-model-serving-ingress
Namespace:    gemma-model
Created on:   ...
Labels:       app=ai-network-policy
              tutorial-level=3
              tutorial-module=M1
Annotations:  <none>
Spec:
  PodSelector:     component=predictor
  Allowing ingress traffic:
    To Port: 8080/TCP
    From:
      NamespaceSelector: access-model-serving=true
    ----------
    To Port: 8080/TCP
    From:
      NamespaceSelector: network.openshift.io/policy-group=ingress
  Not affecting egress traffic
  Policy Types: Ingress
```

### Step 10: Audit Logging

OpenShift records all API requests in audit logs. This is how you answer "who deployed that model?" or "who deleted that pipeline?" in an investigation.

View recent audit events related to InferenceService operations:

```bash
# Check who has accessed InferenceService resources recently
oc get events -n gemma-model --field-selector reason=Created --sort-by='.lastTimestamp'
```

Use `oc adm node-logs` to access the raw API server audit logs on a control plane node:

```bash
# Get the name of a master node
MASTER_NODE=$(oc get nodes -l node-role.kubernetes.io/master= -o jsonpath='{.items[0].metadata.name}')

# Search audit logs for InferenceService operations
oc adm node-logs $MASTER_NODE --path=kube-apiserver/ | \
  grep -i "inferenceservice" | \
  python3 -c "
import sys, json
for line in sys.stdin:
    try:
        entry = json.loads(line)
        print(f\"{entry.get('requestReceivedTimestamp', 'N/A')} | \
{entry.get('user', {}).get('username', 'N/A')} | \
{entry.get('verb', 'N/A')} | \
{entry.get('objectRef', {}).get('resource', 'N/A')}/{entry.get('objectRef', {}).get('name', 'N/A')}\")
    except json.JSONDecodeError:
        pass
" 2>/dev/null | tail -10
```

Expected output (format):

```
2024-01-15T10:30:00Z | admin-user | create | inferenceservices/gemma-4-e4b
2024-01-15T10:35:00Z | system:serviceaccount:redhat-ods-applications:kserve-controller | update | inferenceservices/gemma-4-e4b
```

For a simpler view, check who can access the model endpoint by reviewing current RBAC:

```bash
# List all subjects that can access InferenceServices in this namespace
oc auth can-i --list --as=admin-user -n gemma-model | grep inferenceservice
```

Expected output:

```
inferenceservices.serving.kserve.io             []       []       [*]
```

```bash
oc auth can-i --list --as=scientist-user -n gemma-model | grep inferenceservice
```

Expected output:

```
inferenceservices.serving.kserve.io             []       []       [create get list watch update patch delete]
```

```bash
oc auth can-i --list \
  --as=system:serviceaccount:agent-workloads:agent-sa -n gemma-model | grep inferenceservice
```

Expected output:

```
inferenceservices.serving.kserve.io             []       []       [get list watch]
```

This confirms the three-tier access model: admin has full wildcard access, data scientists have CRUD operations, and agent consumers have read-only access.

### Step 11: Service Account Token for Agent Authentication

In production, agents authenticate to the model endpoint using their service account token. Generate a token for the `agent-sa` service account:

```bash
# Create a bound token with a 1-hour expiry
oc create token agent-sa -n agent-workloads --duration=3600s
```

Expected output:

```
eyJhbGciOiJSUzI1NiIsImtpZCI6Ik...  (truncated JWT)
```

Save the token and use it to call the model endpoint:

```bash
TOKEN=$(oc create token agent-sa -n agent-workloads --duration=3600s)

# Use the token in a request header
# (Note: this token authenticates to the K8s API.
#  For model endpoint auth, see L3-M1.2 on Authorino.)
oc get inferenceservice gemma-4-e4b -n gemma-model \
  --as=system:serviceaccount:agent-workloads:agent-sa
```

Expected output:

```
NAME          URL                                                  READY   PREV   LATEST   AGE
gemma-4-e4b   https://gemma-4-e4b-gemma-model.apps.example.com     True                    2d
```

The service account can read the InferenceService to discover the endpoint URL, but cannot modify or delete it. This is the principle of least privilege in action -- the agent knows where the model is, but cannot change the deployment.

## Verification

Confirm the following before moving on:

| Check | How to verify |
|-------|---------------|
| ClusterRole created | `oc get clusterrole ai-platform-admin` returns the role |
| Namespace Roles created | `oc get role -n gemma-model` shows `ai-data-scientist` and `ai-agent-consumer` |
| ClusterRoleBinding created | `oc get clusterrolebinding ai-platform-admin-binding` returns the binding |
| RoleBindings created | `oc get rolebinding -n gemma-model` shows both namespace bindings |
| Admin can manage all AI resources | `oc auth can-i create inferenceservices.serving.kserve.io --as=admin-user -n gemma-model` returns `yes` |
| Data scientist can deploy but not admin | `oc auth can-i create inferenceservices.serving.kserve.io --as=scientist-user -n gemma-model` returns `yes`; `oc auth can-i create clusterrole --as=scientist-user` returns `no` |
| Agent consumer is read-only | `oc auth can-i create inferenceservices.serving.kserve.io --as=system:serviceaccount:agent-workloads:agent-sa -n gemma-model` returns `no` |
| Default deny policy active | `oc get networkpolicy default-deny-all-ingress -n gemma-model` exists |
| Model serving policy active | `oc get networkpolicy allow-model-serving-ingress -n gemma-model` exists |
| Authorized namespace can reach model | `curl` from `agent-workloads` to model endpoint succeeds |
| Unauthorized namespace is blocked | `curl` from `test-unauthorized` to model endpoint times out |
| Dashboard groups configured | `oc get groups` shows `rhods-admins` and `rhods-users` |

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift / OpenShift AI |
|--------|-----------|--------------------------|
| RBAC primitives | Role, ClusterRole, RoleBinding, ClusterRoleBinding | Same primitives, plus pre-defined Groups (`rhods-admins`, `rhods-users`) that control dashboard access |
| AI-specific roles | Must define custom roles for every CRD (KServe, Kubeflow, etc.) | Same -- custom roles required. But OpenShift AI auto-creates some roles for Model Registry instances |
| Dashboard access control | No built-in AI dashboard; access varies by tool | `rhods-admins` and `rhods-users` groups control OpenShift AI dashboard visibility and admin panel access |
| Project self-provisioning | Namespaces require cluster-admin to create by default | Users can self-provision Projects; creator gets `admin` role automatically |
| NetworkPolicy enforcement | Requires a compatible CNI (Calico, Cilium, etc.); policies are inert without one | OVN-Kubernetes enforces NetworkPolicies by default -- no extra CNI installation needed |
| Network policy for routes | Ingress controller namespace varies; must find and label it | OpenShift router runs in `openshift-ingress`; select it with `network.openshift.io/policy-group=ingress` label |
| Audit logging | API server audit logs; configuration varies by distribution | Built-in audit logging to node log files; accessible via `oc adm node-logs` |
| Service account tokens | `kubectl create token` (K8s 1.24+) | `oc create token` (same mechanism); integrates with OpenShift OAuth |
| User management | External identity provider required; no built-in user objects | OpenShift `User` and `Group` resources; multiple identity providers (LDAP, OIDC, HTPasswd) |

## Key Takeaways

- OpenShift AI adds a **three-tier access model** on top of standard K8s RBAC: cluster-level groups (`rhods-admins`, `rhods-users`), project-level roles (auto-assigned on project creation), and resource-specific roles for Model Registry instances.
- **Custom Roles are required** for AI-specific CRDs -- the built-in `admin` and `edit` roles do not cover `InferenceService`, `ServingRuntime`, `Notebook`, or other OpenShift AI resources. Define roles that match your organizational personas (platform admin, data scientist, agent consumer).
- **Default-deny network policies** are the foundation of AI infrastructure security. Start by blocking all ingress, then add explicit allow rules for each legitimate communication path. On OpenShift, NetworkPolicies are enforced by OVN-Kubernetes out of the box -- no extra CNI needed.
- **Service accounts with least-privilege roles** enable automated agents and pipelines to consume model endpoints without human credentials. The agent gets read access to discover endpoints but cannot modify the deployment.
- **Audit logging** provides the trail you need for compliance and incident investigation. OpenShift API server audit logs capture every create, update, and delete operation on AI resources with timestamps and user identity.

## Cleanup

Delete all resources created in this lesson:

```bash
# Delete network policies
oc delete networkpolicy default-deny-all-ingress -n gemma-model
oc delete networkpolicy allow-model-serving-ingress -n gemma-model
oc delete networkpolicy allow-mcp-server-ingress -n gemma-model

# Delete role bindings
oc delete clusterrolebinding ai-platform-admin-binding
oc delete rolebinding ai-data-scientist-binding -n gemma-model
oc delete rolebinding ai-agent-consumer-binding -n gemma-model

# Delete roles
oc delete clusterrole ai-platform-admin
oc delete role ai-data-scientist -n gemma-model
oc delete role ai-agent-consumer -n gemma-model

# Delete groups
oc delete group rhods-admins
oc delete group rhods-users

# Delete namespace label
oc label namespace agent-workloads access-model-serving-

# Delete test resources
oc delete project test-unauthorized
oc delete serviceaccount agent-sa -n agent-workloads
oc delete project agent-workloads
```

> **Note:** If you are continuing to [L3-M1.2 -- Authorino: Auth for Model Endpoints](../2_authorino/), **keep the RBAC roles and the `agent-sa` service account**. The next lesson uses them to demonstrate token-based authentication on model endpoints. Only delete the network policies if you want a clean starting point for Authorino's own network configuration.

## Next Steps

In [L3-M1.2 -- Authorino: Auth for Model Endpoints](../2_authorino/), you will add application-layer authentication to the Gemma4-e4b model endpoint using Authorino. While the RBAC roles in this lesson control who can manage AI resources via the Kubernetes API, Authorino controls who can call the model's inference endpoint at the HTTP level -- requiring valid tokens, API keys, or OIDC credentials for every prediction request. You will configure the `agent-sa` service account token as an accepted credential, building directly on the RBAC foundation from this lesson.
