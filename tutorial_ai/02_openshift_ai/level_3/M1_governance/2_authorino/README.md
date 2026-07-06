# L3-M1.2 -- Authorino: Auth for Model Endpoints

**Level:** Expert
**Duration:** 45 min

## Overview

In this lesson you secure a deployed model endpoint using Authorino, the Kubernetes-native authentication and authorization service that ships with OpenShift AI. You already know how to deploy an InferenceService (L1-M2.2) and how to restrict who can manage AI resources with RBAC (L3-M1.1). Now you add runtime request-level security: every inference call must present a valid credential before it reaches the model. By the end of this lesson, your Gemma4-e4b endpoint will reject unauthenticated requests, accept ServiceAccount tokens from internal agents, and validate JWTs from external OIDC clients.

## Prerequisites

- Completed: [L3-M1.1 -- RBAC and Network Policies](../1_rbac/)
- Completed: [L1-M2.2 -- Deploying Gemma4-e4b with vLLM](../../../level_1/M2_model_serving/2_deploying_gemma/)
- OpenShift AI 3.4+ cluster with a GPU node
- `oc` CLI authenticated to the cluster
- The `gemma-model` namespace exists with a working Gemma4-e4b InferenceService (or you will re-create it in Step 1)

Verify the Authorino operator is running (it is deployed automatically as part of OpenShift AI's `kserve` component):

```bash
oc get pods -n redhat-ods-applications -l app=authorino
```

Expected output:

```
NAME                         READY   STATUS    RESTARTS   AGE
authorino-xxxxxxxxxx-xxxxx   1/1     Running   0          3d
```

If no pods are returned, the OpenShift AI operator may not have deployed the `kserve` component. Check the DSCInitialization and DataScienceCluster custom resources.

## Concepts

### The Problem: Open Model Endpoints

When you deployed Gemma4-e4b in L1-M2.2, the InferenceService had `security.opendatahub.io/enable-auth: "false"`. That means anyone who can reach the Route can send inference requests -- no credentials, no identity checks, no audit trail. For a learning exercise that is fine. In production it is unacceptable: model endpoints consume expensive GPU resources, may expose sensitive training data through their responses, and need access control for compliance.

On vanilla Kubernetes, you would solve this by deploying an API gateway (like Kong or Envoy Gateway), configuring OAuth2 proxy, or writing authentication middleware into the application itself. Each approach requires installing, configuring, and maintaining additional infrastructure.

### Authorino: Kubernetes-Native AuthN/AuthZ

Authorino is an authentication and authorization service from the Kuadrant project. It implements the Envoy external authorization (ext-authz) gRPC protocol, which means it runs as a sidecar alongside your application and intercepts every request before it reaches the model container. Envoy calls Authorino with the request headers, Authorino evaluates its policies, and returns allow or deny.

On OpenShift AI, Authorino is deployed automatically as part of the `kserve` component -- you do not install it separately. When you set `security.opendatahub.io/enable-auth: "true"` on an InferenceService, the KServe controller injects an Envoy sidecar into the model pod. That Envoy sidecar is configured to call Authorino for every incoming request.

The flow for an authenticated request:

```
Client --> Route --> Envoy sidecar --> Authorino (ext-authz) --> vLLM container
                                          |
                                          +--> deny (401/403)
```

### AuthConfig: The Policy CRD

Authorino uses the `AuthConfig` custom resource (`authorino.kuadrant.io/v1beta3`) to define authentication and authorization policies. An AuthConfig is linked to one or more hostnames -- when a request arrives for that hostname, Authorino applies the policies defined in the AuthConfig.

Key sections of an AuthConfig:

| Section | Purpose |
|---------|---------|
| `spec.hosts` | List of hostnames this policy applies to (matches the InferenceService Route) |
| `spec.authentication` | Authentication methods: how to verify the caller's identity |
| `spec.authorization` | Authorization rules: whether the authenticated caller is allowed to proceed |
| `spec.response` | Optional response mutations: headers or JSON to add to the upstream request |
| `spec.callbacks` | Optional post-authorization webhooks (audit, logging) |

### Authentication Methods

Authorino supports four authentication mechanisms, and you can combine multiple methods in a single AuthConfig. Authorino tries each method in order and succeeds on the first match.

**1. Kubernetes TokenReview** (`kubernetesTokenReview`):
Validates Kubernetes ServiceAccount tokens by calling the cluster's TokenReview API. This is the natural choice for internal services, agents, and pipelines that already have a ServiceAccount. The client sends its SA token as a Bearer token in the Authorization header.

**2. JWT / OIDC** (`jwt`):
Validates JSON Web Tokens against a remote OIDC issuer's JWKS endpoint. This is the standard for external clients authenticating through an identity provider like Keycloak, Azure AD, or Okta. Authorino fetches the issuer's public keys and verifies the token signature, expiry, and audience locally -- no call to the IdP on every request.

**3. API Keys** (`apiKey`):
Looks up API keys stored as Kubernetes Secrets. The client sends the key in a header (typically `Authorization: APIKEY <key>`). Simple but limited -- suitable for service-to-service calls where you control both sides.

**4. mTLS** (`x509`):
Validates the client's TLS certificate against a trusted CA. Used when both client and server present certificates. The strongest authentication mechanism, but requires certificate distribution infrastructure.

### Authorization Policies

After authentication succeeds, Authorino evaluates authorization rules. The most common approaches:

**Pattern matching**: Simple field comparisons against the authenticated identity. For example, check that the ServiceAccount belongs to a specific namespace, or that a JWT claim contains a required role.

**OPA/Rego**: Inline Open Policy Agent rules written in Rego. For complex policies like "allow read access to anyone in the `ml-engineers` group, but restrict write access to `ml-admins`."

**External metadata**: Fetch additional data from an external HTTP endpoint before making the authorization decision. For example, check a model registry to verify the caller has a license to use the model.

### Why Not Just Use Network Policies?

Network policies (covered in L3-M1.1) control which pods can communicate at the network level. They answer "can Pod A send packets to Pod B?" -- a binary yes/no based on labels and namespaces.

Authorino operates at the application level. It answers "is this specific request from this specific identity authorized to call this specific endpoint?" Network policies and Authorino are complementary layers:

| Layer | What it controls | Granularity |
|-------|-----------------|-------------|
| Network Policy | Pod-to-pod connectivity | Namespace, pod labels, ports |
| Authorino | Request-level auth | Identity, claims, headers, paths |

In production, you use both: network policies to restrict which pods can even reach the model service, and Authorino to verify identity and enforce fine-grained access control on the requests that do arrive.

## Step-by-Step

### Step 1: Verify the Model Deployment

Confirm that the Gemma4-e4b InferenceService is running in the `gemma-model` namespace:

```bash
oc get inferenceservice gemma-4-e4b -n gemma-model
```

Expected output:

```
NAME          URL                                                       READY   PREV   LATEST   AGE
gemma-4-e4b   https://gemma-4-e4b-gemma-model.apps.example.com          True                    1d
```

If the InferenceService does not exist, re-deploy it by following the steps in [L1-M2.2](../../../level_1/M2_model_serving/2_deploying_gemma/).

Save the Route URL for later use:

```bash
ROUTE_URL=$(oc get route -n gemma-model \
  -l serving.kserve.io/inferenceservice=gemma-4-e4b \
  -o jsonpath='{.items[0].spec.host}')
echo "Model endpoint: https://${ROUTE_URL}"
```

Confirm the endpoint is currently unauthenticated (auth disabled):

```bash
curl -s "https://${ROUTE_URL}/v1/models" | python3 -m json.tool
```

Expected output (the model responds without any credentials):

```json
{
    "object": "list",
    "data": [
        {
            "id": "gemma-4-e4b",
            "object": "model",
            "owned_by": "vllm",
            "root": "google/gemma-4-E4B-it"
        }
    ]
}
```

### Step 2: Enable Auth on the InferenceService

Apply the auth-enabled InferenceService manifest. This is the same InferenceService from L1-M2.2, but with the critical annotation `security.opendatahub.io/enable-auth: "true"`:

Review the manifest first:

```bash
cat manifests/inferenceservice-auth-enabled.yaml
```

The key change is a single annotation:

```yaml
annotations:
  security.opendatahub.io/enable-auth: "true"
```

When this annotation is set to `"true"`, the KServe controller:

1. Injects an Envoy sidecar into the model pod
2. Configures the sidecar to intercept all incoming requests
3. Routes auth decisions to the Authorino service running in `redhat-ods-applications`

Apply the updated InferenceService:

```bash
oc apply -f manifests/inferenceservice-auth-enabled.yaml
```

Expected output:

```
inferenceservice.serving.kserve.io/gemma-4-e4b configured
```

The pod will restart to pick up the Envoy sidecar. Watch the rollout:

```bash
oc get pods -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b -w
```

Wait until the pod shows `2/2 Running` -- the second container is the Envoy sidecar:

```
NAME                                          READY   STATUS    RESTARTS   AGE
gemma-4-e4b-predictor-xxxxx-yyyyy             2/2     Running   0          2m
```

Press `Ctrl+C` once the pod is ready.

Now test that unauthenticated requests are rejected:

```bash
curl -s -o /dev/null -w "%{http_code}" "https://${ROUTE_URL}/v1/models"
```

Expected output:

```
401
```

The endpoint now returns HTTP 401 Unauthorized for requests without valid credentials. The Envoy sidecar intercepted the request and Authorino rejected it because no AuthConfig is configured yet (the default behavior when auth is enabled but no matching AuthConfig exists is to deny).

### Step 3: Create the ServiceAccount for an Agent

Before configuring the AuthConfig, create a ServiceAccount that will represent an internal AI agent (such as a pipeline step, a RAG orchestrator, or an agentic workflow) that needs to call the model endpoint.

Review the manifest:

```bash
cat manifests/service-account-agent.yaml
```

Apply it:

```bash
oc apply -f manifests/service-account-agent.yaml
```

Expected output:

```
serviceaccount/agent-inference-client created
```

Verify the ServiceAccount was created:

```bash
oc get serviceaccount agent-inference-client -n gemma-model -o yaml
```

Expected output (abbreviated):

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: agent-inference-client
  namespace: gemma-model
  labels:
    app: agent-inference-client
    opendatahub.io/component: inference-client
  annotations:
    description: "ServiceAccount for AI agents that need to call model inference endpoints"
```

### Step 4: Configure the AuthConfig

The AuthConfig defines how Authorino authenticates and authorizes requests to the model endpoint. Review the manifest:

```bash
cat manifests/authconfig.yaml
```

Walk through each section of the AuthConfig:

**Host matching** -- links this policy to the InferenceService Route:

```yaml
spec:
  hosts:
    - gemma-4-e4b-gemma-model.apps.example.com
```

Replace `example.com` with your actual cluster domain. You can also use a wildcard pattern like `gemma-4-e4b-gemma-model.apps.*` if your cluster domain varies between environments.

**Authentication -- Kubernetes TokenReview**:

```yaml
authentication:
  k8s-sa-auth:
    kubernetesTokenReview:
      audiences:
        - "https://kubernetes.default.svc"
```

This method validates Kubernetes ServiceAccount tokens by delegating to the cluster's TokenReview API. The `audiences` field restricts which token audiences are accepted -- using the cluster's default API server audience. When a client sends `Authorization: Bearer <sa-token>`, Authorino calls TokenReview to verify the token is valid and not expired.

**Authentication -- JWT/OIDC**:

```yaml
  oidc-jwt-auth:
    jwt:
      issuerUrl: https://sso.example.com/realms/ai-platform
      audiences:
        - gemma-inference
```

This method validates JWTs issued by an external OIDC provider. Authorino fetches the provider's JWKS (JSON Web Key Set) from the `.well-known/openid-configuration` endpoint and verifies token signatures locally. The `audiences` field ensures the token was issued specifically for the inference service, preventing token reuse across different services.

**Authorization -- pattern matching**:

```yaml
authorization:
  check-namespace:
    patternMatching:
      patterns:
        - patternRef: k8s-sa-auth
          selector: auth.identity.namespace
          operator: eq
          value: gemma-model
```

This rule checks that ServiceAccount tokens come from the `gemma-model` namespace. Without this, any ServiceAccount in the cluster could authenticate to the endpoint. The `patternRef` field limits this rule to identities that authenticated via the `k8s-sa-auth` method (it does not apply to JWT-authenticated clients).

Before applying, update the host to match your cluster:

```bash
# Get your actual Route hostname
ROUTE_URL=$(oc get route -n gemma-model \
  -l serving.kserve.io/inferenceservice=gemma-4-e4b \
  -o jsonpath='{.items[0].spec.host}')

echo "Your Route hostname: ${ROUTE_URL}"
```

Edit `manifests/authconfig.yaml` and replace `gemma-4-e4b-gemma-model.apps.example.com` with your actual hostname. Then apply:

```bash
oc apply -f manifests/authconfig.yaml
```

Expected output:

```
authconfig.authorino.kuadrant.io/gemma-4-e4b-auth created
```

Verify the AuthConfig was created and is ready:

```bash
oc get authconfig -n gemma-model
```

Expected output:

```
NAME                   READY   HOSTS                                              AGE
gemma-4-e4b-auth       True    ["gemma-4-e4b-gemma-model.apps.example.com"]       5s
```

The `READY=True` status means Authorino has successfully loaded the policy. If it shows `False`, check the Authorino pod logs:

```bash
oc logs -n redhat-ods-applications -l app=authorino --tail=50
```

### Step 5: Authenticate as an Internal Agent (ServiceAccount Token)

Now test the authentication flow using the ServiceAccount you created. First, generate a short-lived token for the `agent-inference-client` ServiceAccount:

```bash
SA_TOKEN=$(oc create token agent-inference-client \
  -n gemma-model \
  --audience="https://kubernetes.default.svc" \
  --duration=1h)

echo "Token generated (first 20 chars): ${SA_TOKEN:0:20}..."
```

Expected output:

```
Token generated (first 20 chars): eyJhbGciOiJSUzI1NiIs...
```

The `oc create token` command creates a short-lived (1 hour) bound ServiceAccount token. The `--audience` flag must match the audience configured in the AuthConfig's `kubernetesTokenReview` section.

Now call the model endpoint with the token:

```bash
ROUTE_URL=$(oc get route -n gemma-model \
  -l serving.kserve.io/inferenceservice=gemma-4-e4b \
  -o jsonpath='{.items[0].spec.host}')

curl -s "https://${ROUTE_URL}/v1/chat/completions" \
  -H "Authorization: Bearer ${SA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [
      {"role": "user", "content": "What is Authorino in one sentence?"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }' | python3 -m json.tool
```

Expected output:

```json
{
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "gemma-4-e4b",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Authorino is a Kubernetes-native authentication and authorization service that acts as an Envoy external authorization filter to protect API endpoints."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 15,
        "completion_tokens": 28,
        "total_tokens": 43
    }
}
```

The request succeeded because:

1. The Bearer token was a valid ServiceAccount token
2. Authorino validated it via the Kubernetes TokenReview API
3. The ServiceAccount is in the `gemma-model` namespace, which passes the authorization pattern match

### Step 6: Verify Rejection of Invalid Credentials

Test that invalid or missing credentials are properly rejected.

**Test 1: No credentials**

```bash
curl -s -w "\nHTTP Status: %{http_code}\n" "https://${ROUTE_URL}/v1/models"
```

Expected output:

```
{"code":"UNAUTHENTICATED","message":"credential not found"}
HTTP Status: 401
```

**Test 2: Invalid token**

```bash
curl -s -w "\nHTTP Status: %{http_code}\n" \
  -H "Authorization: Bearer invalid-token-value" \
  "https://${ROUTE_URL}/v1/models"
```

Expected output:

```
{"code":"UNAUTHENTICATED","message":"credential not valid"}
HTTP Status: 401
```

**Test 3: Valid token from a different namespace (authorization failure)**

Create a ServiceAccount in a different namespace and try to authenticate:

```bash
oc create namespace auth-test-ns

oc create serviceaccount test-other-ns -n auth-test-ns

OTHER_TOKEN=$(oc create token test-other-ns \
  -n auth-test-ns \
  --audience="https://kubernetes.default.svc" \
  --duration=5m)

curl -s -w "\nHTTP Status: %{http_code}\n" \
  -H "Authorization: Bearer ${OTHER_TOKEN}" \
  "https://${ROUTE_URL}/v1/models"
```

Expected output:

```
{"code":"PERMISSION_DENIED","message":"not authorized"}
HTTP Status: 403
```

Notice the difference: the token is valid (authentication passed -- it is a real ServiceAccount token), but authorization failed because the ServiceAccount is not in the `gemma-model` namespace. The response code is 403 Forbidden, not 401 Unauthorized. This distinction is important for debugging.

Clean up the test namespace:

```bash
oc delete namespace auth-test-ns
```

### Step 7: Use the Token in an Agent Application

In a real agent application, you would mount the ServiceAccount token and use it programmatically. Here is how that works in practice.

When a pod runs with a specific ServiceAccount, Kubernetes automatically mounts a projected token at `/var/run/secrets/kubernetes.io/serviceaccount/token`. However, for Authorino authentication, you need a token with the correct audience. The recommended approach is to use a projected volume with an explicit audience:

```yaml
# Example: Pod spec for an agent that calls the model endpoint
# (Do not apply this -- it is for illustration)
apiVersion: v1
kind: Pod
metadata:
  name: my-agent
  namespace: gemma-model
spec:
  serviceAccountName: agent-inference-client
  containers:
    - name: agent
      image: registry.access.redhat.com/ubi9/python-311:latest
      env:
        - name: MODEL_ENDPOINT
          value: "https://gemma-4-e4b-gemma-model.apps.example.com"
        - name: TOKEN_PATH
          value: "/var/run/secrets/tokens/inference-token"
      volumeMounts:
        - name: inference-token
          mountPath: /var/run/secrets/tokens
          readOnly: true
  volumes:
    - name: inference-token
      projected:
        sources:
          - serviceAccountToken:
              audience: "https://kubernetes.default.svc"
              expirationSeconds: 3600
              path: inference-token
```

The projected token volume creates a token file that:

- Has the correct audience for the AuthConfig (`https://kubernetes.default.svc`)
- Is automatically rotated before expiry (the kubelet refreshes it)
- Is mounted read-only at a predictable path

Inside the agent container, the code reads the token file and includes it in HTTP requests:

```python
import requests

def call_model(prompt: str) -> str:
    """Call the model endpoint with SA token authentication."""
    # Read the projected token (auto-rotated by kubelet)
    with open("/var/run/secrets/tokens/inference-token") as f:
        token = f.read().strip()

    response = requests.post(
        f"{MODEL_ENDPOINT}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gemma-4-e4b",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
```

### Step 8: Inspect Authorino Logs

Authorino logs every authentication and authorization decision. This is valuable for debugging and auditing.

View recent Authorino logs:

```bash
oc logs -n redhat-ods-applications -l app=authorino \
  --tail=20 \
  --since=5m
```

Example log entries for a successful request:

```json
{
  "level": "info",
  "msg": "auth request",
  "authconfig": "gemma-model/gemma-4-e4b-auth",
  "method": "k8s-sa-auth",
  "authorized": true,
  "identity": {
    "serviceaccount": "agent-inference-client",
    "namespace": "gemma-model"
  }
}
```

Example log entry for a rejected request:

```json
{
  "level": "info",
  "msg": "auth request",
  "authconfig": "gemma-model/gemma-4-e4b-auth",
  "authorized": false,
  "reason": "UNAUTHENTICATED",
  "detail": "credential not found"
}
```

These logs give you a complete audit trail of who accessed the model, when, and whether they were allowed. In production, you would forward these logs to a centralized logging system (covered in the OpenShift Logging stack) for compliance and monitoring.

## Verification

Confirm the following before moving on:

| Check | How to verify |
|-------|---------------|
| Auth enabled on InferenceService | `oc get inferenceservice gemma-4-e4b -n gemma-model -o jsonpath='{.metadata.annotations.security\.opendatahub\.io/enable-auth}'` returns `true` |
| Envoy sidecar injected | `oc get pods -n gemma-model` shows `2/2` containers ready |
| AuthConfig ready | `oc get authconfig -n gemma-model` shows `READY=True` |
| Unauthenticated requests rejected | `curl` without Bearer token returns HTTP 401 |
| SA token accepted | `curl` with valid SA token returns model response (HTTP 200) |
| Wrong-namespace SA rejected | `curl` with SA token from other namespace returns HTTP 403 |
| Authorino logs visible | `oc logs -l app=authorino` shows auth decision entries |

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| Auth infrastructure | Install and configure API gateway (Kong, Envoy Gateway) or OAuth2 proxy manually | Authorino deployed automatically with `kserve` component |
| Enabling auth | Modify Ingress annotations, deploy auth proxy sidecar, configure webhook | Single annotation: `security.opendatahub.io/enable-auth: "true"` |
| Sidecar injection | Manual Envoy sidecar configuration in pod spec | Automatic Envoy sidecar injection by KServe controller |
| Policy definition | Varies by gateway: Kong plugins, Envoy filters, OPA policies | Standardized AuthConfig CRD (`authorino.kuadrant.io/v1beta3`) |
| SA token auth | Write custom TokenReview webhook or middleware | Built-in `kubernetesTokenReview` in AuthConfig |
| JWT/OIDC auth | Configure OAuth2 proxy or Envoy JWT filter | Declarative `jwt` block in AuthConfig with auto JWKS fetching |
| API key auth | Custom middleware or gateway plugin | `apiKey` method backed by Kubernetes Secrets |
| Authorization | OPA Gatekeeper or custom admission webhooks | Inline OPA/Rego, pattern matching, or external metadata in AuthConfig |
| Audit trail | Custom logging per auth component | Centralized Authorino logs with structured auth decision entries |
| Multi-method auth | Wire multiple auth proxies in chain | Multiple authentication methods in single AuthConfig, first-match semantics |

## Key Takeaways

- Securing a model endpoint on OpenShift AI requires a single annotation (`security.opendatahub.io/enable-auth: "true"`) to enable Envoy sidecar injection and Authorino integration -- no additional infrastructure to install or maintain.

- The `AuthConfig` CRD (`authorino.kuadrant.io/v1beta3`) is the central policy object that defines authentication methods and authorization rules, linked to InferenceService endpoints by hostname matching.

- **Internal services and agents** authenticate using Kubernetes ServiceAccount tokens validated via TokenReview -- a natural fit because the token infrastructure already exists in the cluster and tokens are automatically mounted into pods.

- **External clients** authenticate using JWTs validated against an OIDC provider's JWKS endpoint -- Authorino fetches and caches the public keys automatically, so there is no per-request call to the identity provider.

- Authorino and network policies are **complementary layers**: network policies control which pods can reach the endpoint (Layer 3/4), while Authorino controls which identities are authorized to make requests (Layer 7). Production deployments should use both.

## Cleanup

Delete the resources created in this lesson:

```bash
# Remove the AuthConfig
oc delete authconfig gemma-4-e4b-auth -n gemma-model

# Remove the agent ServiceAccount
oc delete serviceaccount agent-inference-client -n gemma-model

# Revert the InferenceService to disable auth (restore the original from L1-M2.2)
oc annotate inferenceservice gemma-4-e4b \
  -n gemma-model \
  security.opendatahub.io/enable-auth="false" \
  --overwrite
```

Wait for the pod to restart without the Envoy sidecar:

```bash
oc get pods -n gemma-model -w
```

The pod should return to `1/1 Running` (one container, no sidecar).

> **Note:** If you are continuing to [L3-M1.3 -- Models-as-a-Service](../3_maas/), you may want to keep auth enabled. Check the prerequisites of the next lesson.

## Next Steps

In [L3-M1.3 -- Models-as-a-Service](../3_maas/), you will build on the auth and RBAC foundations from this module to implement a self-service model catalog. Platform teams publish approved models with pre-configured auth policies, and application teams consume them through a standardized interface without needing cluster-admin privileges.
