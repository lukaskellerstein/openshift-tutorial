# L3-M1.3 -- Models-as-a-Service (MaaS)

**Level:** Expert
**Duration:** 1 hour

## Overview

Models-as-a-Service (MaaS), generally available in OpenShift AI 3.4, lets a platform team deploy a model once and expose it as a managed API endpoint that multiple application teams consume through self-service API keys with metered access. Instead of every team spinning up its own InferenceService (duplicating GPU resources, operational burden, and configuration drift), a single shared endpoint is governed by Kuadrant -- Authorino for authentication and Limitador for rate limiting. This lesson walks through the full MaaS flow: configuring tier-based rate limits, generating API keys, and consuming the endpoint as a client.

## Prerequisites

- Completed: [L3-M1.1 -- RBAC for AI Workloads](../1_rbac/) and [L3-M1.2 -- Authorino](../2_authorino/)
- Gemma4-e4b InferenceService deployed and serving in the `gemma-model` namespace (from L1-M2.2)
- OpenShift AI 3.4+ with Kuadrant operator installed (Authorino and Limitador components)
- Gateway API (Istio-based or Envoy Gateway) configured as the ingress for model endpoints
- `oc` CLI authenticated with a user that has `cluster-admin` privileges (required for Kuadrant CRDs)
- Python 3.11+ with the `requests` library installed locally (for the test client)

## Concepts

### The Problem MaaS Solves

In a typical OpenShift AI deployment without MaaS, the workflow looks like this: Team A needs inference, so they create an InferenceService. Team B also needs inference for the same model, so they create another InferenceService. Now you have two copies of a multi-gigabyte model loaded into GPU memory, two sets of scaling rules, two sets of monitoring dashboards, and no centralized view of who is consuming what.

MaaS replaces this with a shared-infrastructure pattern:

```
                    +----------------------------+
                    |   Platform Team manages    |
                    |                            |
                    |  +----------------------+  |
                    |  | Gemma4-e4b model      |  |
                    |  | (single deployment)   |  |
                    |  +----------+-----------+  |
                    |             |               |
                    |  +----------v-----------+  |
                    |  | Kuadrant Gateway      |  |
                    |  | - Authorino (auth)    |  |
                    |  | - Limitador (limits)  |  |
                    |  +--+-------+--------+--+  |
                    +-----|-------|--------|------+
                          |       |        |
               +----------+  +---+---+  +--+----------+
               | Team A   |  | Team B|  | Team C      |
               | Free key |  | Prem. |  | Enterprise  |
               | 10 r/min |  | 100/m |  | unlimited   |
               +----------+  +-------+  +-------------+
```

### Kuadrant Architecture

Kuadrant is the policy engine that makes MaaS work. It consists of two main components:

**Authorino** -- An Envoy-compatible external authorization service. In the MaaS context, Authorino:
- Validates API keys passed in the `Authorization` header
- Looks up the corresponding Kubernetes Secret
- Extracts the `maas-tier` label from the Secret metadata
- Passes the tier information downstream as a header so Limitador can apply the correct rate limit

**Limitador** -- A rate-limiting service backed by Redis. Limitador:
- Receives the tier information from Authorino
- Maintains per-key request counters in Redis
- Enforces the rate limits defined in the RateLimitPolicy CRD
- Returns standard rate-limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`)

The request flow through Kuadrant:

```
Client request
  |
  | Authorization: Bearer <api-key>
  v
Gateway (Envoy / Istio)
  |
  +---> Authorino (ext_authz filter)
  |       |
  |       +-- lookup Secret by api-key value
  |       +-- extract maas-tier label --> "free" or "premium"
  |       +-- inject x-maas-tier header
  |       |
  |     <-+ allow / deny
  |
  +---> Limitador (rate_limit filter)
  |       |
  |       +-- read x-maas-tier header
  |       +-- check counter for this key + tier
  |       +-- 200 OK or 429 Too Many Requests
  |       |
  |     <-+ allow / deny
  |
  +---> InferenceService (upstream)
  |
  v
Response to client
```

### Tier-Based Access Control

MaaS tiers map directly to business requirements:

| Tier | Rate Limit | Max Tokens | Use Case |
|------|-----------|------------|----------|
| `free` | 10 req/min | 1,000 | Prototyping, development, internal experimentation |
| `premium` | 100 req/min | 4,096 | Production workloads, customer-facing applications |
| `enterprise` | Unlimited (or 10,000 req/min) | 8,192 | Mission-critical, SLA-backed services |

Each tier is enforced by a Kuadrant `RateLimitPolicy` that matches on the `x-maas-tier` header injected by Authorino.

### Self-Service API Keys

API keys in MaaS are Kubernetes Secrets with specific labels and annotations. The self-service flow works as follows:

1. An application team requests an API key through the MaaS API (`POST /maas-api/v1/tokens`) or through the OpenShift AI dashboard.
2. The platform creates a Secret in the `maas-keys` namespace with:
   - The API key value stored in `data.api_key`
   - A `maas-tier` label indicating the assigned tier
   - Annotations for the owning team, creation date, and expiration
3. Authorino watches this namespace for Secrets and uses them as an API key store.
4. The application team uses the key in the `Authorization: Bearer <key>` header.

### Enterprise OIDC Integration

For organizations using SSO, MaaS supports OIDC-based authentication through Authorino's identity sources. Instead of (or in addition to) API key Secrets, Authorino can:

- Validate JWT tokens from Azure AD, Okta, or Keycloak
- Extract tier information from JWT claims (e.g., a custom `maas_tier` claim)
- Map OIDC groups to tiers using Authorino's authorization policies

This lesson focuses on the API key flow. The OIDC integration reuses the same Authorino patterns from L3-M1.2 -- the only difference is the identity source configuration.

### Showback Dashboards (Technology Preview)

OpenShift AI 3.4 introduces showback dashboards as a Technology Preview feature. These dashboards:

- Track per-user and per-team consumption via Prometheus metrics exported by Limitador
- Show request counts, token usage, and error rates per API key
- Help platform teams with internal chargeback / cost allocation
- Are available in the OpenShift AI dashboard under "Model Serving > Usage"

Showback relies on the metrics Limitador exports to Prometheus (`limitador_request_count`, `limitador_request_duration_seconds`). We will configure the metrics integration in the verification steps.

## Step-by-Step

### Step 1: Verify the Gemma4-e4b Model Is Serving

Confirm the model is deployed and healthy before layering MaaS on top:

```bash
oc get inferenceservice gemma-4-e4b -n gemma-model
```

Expected output:

```
NAME          URL                                                         READY   PREV   LATEST   AGE
gemma-4-e4b   https://gemma-4-e4b-gemma-model.apps.sandbox.example.com   True           100      5d
```

Test that inference works without any auth (the pre-MaaS state):

```bash
INFERENCE_URL=$(oc get inferenceservice gemma-4-e4b -n gemma-model \
  -o jsonpath='{.status.url}')

curl -s "${INFERENCE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [{"role": "user", "content": "Hello, what model are you?"}],
    "max_tokens": 50
  }' | python3 -m json.tool
```

Expected output (abbreviated):

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "I am Gemma, a large language model created by Google DeepMind..."
      }
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 50,
    "total_tokens": 62
  }
}
```

### Step 2: Create the MaaS Namespace and API Key Secrets

MaaS configuration resources live in a dedicated namespace. Create it and apply the tier configuration and API key Secrets:

```bash
# Create the namespace for MaaS configuration
oc new-project maas-config --display-name="MaaS Configuration" \
  --description="Models-as-a-Service tier config and API keys"
```

Expected output:

```
Now using project "maas-config" on server "https://api.sandbox.example.com:6443".
```

Apply the MaaS configuration manifest, which contains the tier definitions and example API keys:

```bash
oc apply -f manifests/maas-config.yaml
```

Expected output:

```
configmap/maas-tier-config created
secret/maas-key-free-user1 created
secret/maas-key-premium-user1 created
authconfig.authorino.kuadrant.io/maas-auth created
```

Verify the Secrets were created with the correct tier labels:

```bash
oc get secrets -n maas-config -l app=maas-api-key \
  --show-labels -o wide
```

Expected output:

```
NAME                    TYPE     DATA   AGE   LABELS
maas-key-free-user1     Opaque   1      10s   app=maas-api-key,maas-tier=free,team=frontend
maas-key-premium-user1  Opaque   1      10s   app=maas-api-key,maas-tier=premium,team=ml-platform
```

### Step 3: Examine the AuthConfig

The AuthConfig resource tells Authorino how to validate API keys and extract tier information. Review what was applied:

```bash
oc get authconfig maas-auth -n maas-config -o yaml
```

Key sections to note in the output:

- **`spec.hosts`** -- The hostnames this AuthConfig applies to (the model's Route).
- **`spec.identity`** -- Configured with `apiKey` type, watching Secrets in `maas-config` namespace that have the `app: maas-api-key` label.
- **`spec.response.success.headers`** -- Injects the `x-maas-tier` header with the value of the Secret's `maas-tier` label, so Limitador can read it downstream.

The AuthConfig does two things in a single evaluation:
1. **Authentication:** Is this API key valid? (Does a matching Secret exist?)
2. **Metadata enrichment:** What tier does this key belong to? (Read the label, inject the header.)

### Step 4: Apply the RateLimitPolicy

The RateLimitPolicy CRD defines the per-tier rate limits that Limitador enforces:

```bash
oc apply -f manifests/rate-limit-policy.yaml -n maas-config
```

Expected output:

```
ratelimitpolicy.kuadrant.io/maas-tier-limits created
```

Verify the policy was accepted:

```bash
oc get ratelimitpolicy maas-tier-limits -n maas-config
```

Expected output:

```
NAME               TARGETREF KIND   TARGETREF NAME     AGE
maas-tier-limits   HTTPRoute        gemma-model-route  5s
```

Examine the rate limit counters (requires Limitador CLI or API access):

```bash
# If Limitador is exposed via a service in the kuadrant-system namespace:
LIMITADOR_URL=$(oc get svc limitador -n kuadrant-system \
  -o jsonpath='{.spec.clusterIP}')

curl -s "http://${LIMITADOR_URL}:8080/limits" | python3 -m json.tool
```

Expected output (abbreviated):

```json
[
  {
    "namespace": "maas-config/maas-tier-limits",
    "max_value": 10,
    "seconds": 60,
    "conditions": ["x-maas-tier == free"],
    "variables": ["authorization.identity.metadata.annotations.api-key-id"]
  },
  {
    "namespace": "maas-config/maas-tier-limits",
    "max_value": 100,
    "seconds": 60,
    "conditions": ["x-maas-tier == premium"],
    "variables": ["authorization.identity.metadata.annotations.api-key-id"]
  }
]
```

### Step 5: Configure the Gateway HTTPRoute

For Kuadrant to intercept requests to the model endpoint, the model must be exposed through a Gateway API HTTPRoute (not a plain OpenShift Route). If you do not already have one, create it:

```bash
cat <<'EOF' | oc apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: gemma-model-route
  namespace: maas-config
  labels:
    app: maas-gateway
    tutorial-level: "3"
    tutorial-module: "M1"
spec:
  parentRefs:
    - name: kuadrant-gateway
      namespace: kuadrant-system
  hostnames:
    - "gemma-maas.apps.sandbox.example.com"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /v1
      backendRefs:
        - name: gemma-4-e4b-predictor
          namespace: gemma-model
          port: 8080
EOF
```

Expected output:

```
httproute.gateway.networking.k8s.io/gemma-model-route created
```

Verify the route is accepted by the gateway:

```bash
oc get httproute gemma-model-route -n maas-config \
  -o jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'
```

Expected output:

```
True
```

Update the MaaS endpoint URL to use the gateway hostname:

```bash
export MAAS_ENDPOINT="https://gemma-maas.apps.sandbox.example.com"
echo "MaaS endpoint: ${MAAS_ENDPOINT}"
```

### Step 6: Test Authentication with API Keys

Now test the full auth chain. First, try a request without an API key:

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }'
```

Expected output:

```
401
```

Authorino rejected the request -- no API key was provided. Now try with a valid free-tier key:

```bash
# Retrieve the free-tier API key value from the Secret
FREE_KEY=$(oc get secret maas-key-free-user1 -n maas-config \
  -o jsonpath='{.data.api_key}' | base64 -d)

curl -s "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${FREE_KEY}" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [{"role": "user", "content": "Hello, what model are you?"}],
    "max_tokens": 50
  }' | python3 -m json.tool
```

Expected output:

```json
{
  "id": "chatcmpl-def456",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "I am Gemma, a large language model..."
      }
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 45,
    "total_tokens": 57
  }
}
```

Check the rate limit headers in the response:

```bash
curl -s -D - "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${FREE_KEY}" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [{"role": "user", "content": "Say hi"}],
    "max_tokens": 10
  }' 2>&1 | grep -i "x-ratelimit"
```

Expected output:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 8
X-RateLimit-Reset: 45
```

### Step 7: Demonstrate Rate Limiting

Use the Python test client to send rapid requests and observe rate limiting in action:

```bash
# Retrieve API keys
FREE_KEY=$(oc get secret maas-key-free-user1 -n maas-config \
  -o jsonpath='{.data.api_key}' | base64 -d)
PREMIUM_KEY=$(oc get secret maas-key-premium-user1 -n maas-config \
  -o jsonpath='{.data.api_key}' | base64 -d)

export MAAS_ENDPOINT="https://gemma-maas.apps.sandbox.example.com"
```

Run the test client with the free-tier key (limit: 10 req/min):

```bash
cd scripts/
python3 maas_test_client.py \
  --endpoint "${MAAS_ENDPOINT}" \
  --api-key "${FREE_KEY}" \
  --tier free \
  --burst 15
```

Expected output:

```
=== MaaS Rate Limit Test ===
Endpoint: https://gemma-maas.apps.sandbox.example.com
Tier:     free
Burst:    15 requests

Request  1/15: 200 OK  [Limit: 10, Remaining: 9, Reset: 60s]
Request  2/15: 200 OK  [Limit: 10, Remaining: 8, Reset: 58s]
Request  3/15: 200 OK  [Limit: 10, Remaining: 7, Reset: 56s]
...
Request 10/15: 200 OK  [Limit: 10, Remaining: 0, Reset: 35s]
Request 11/15: 429 Too Many Requests  [Retry-After: 35s]
  --> Rate limit exceeded. Waiting before retry...
Request 12/15: 429 Too Many Requests  [Retry-After: 33s]
  --> Rate limit exceeded. Waiting before retry...
Request 13/15: 429 Too Many Requests  [Retry-After: 31s]
  --> Rate limit exceeded. Waiting before retry...
Request 14/15: 429 Too Many Requests  [Retry-After: 29s]
  --> Rate limit exceeded. Waiting before retry...
Request 15/15: 429 Too Many Requests  [Retry-After: 27s]
  --> Rate limit exceeded. Waiting before retry...

=== Summary ===
Successful:    10
Rate limited:   5
Total:         15
```

Now run with the premium-tier key (limit: 100 req/min) -- the same burst of 15 should succeed entirely:

```bash
python3 maas_test_client.py \
  --endpoint "${MAAS_ENDPOINT}" \
  --api-key "${PREMIUM_KEY}" \
  --tier premium \
  --burst 15
```

Expected output:

```
=== MaaS Rate Limit Test ===
Endpoint: https://gemma-maas.apps.sandbox.example.com
Tier:     premium
Burst:    15 requests

Request  1/15: 200 OK  [Limit: 100, Remaining: 99, Reset: 60s]
Request  2/15: 200 OK  [Limit: 100, Remaining: 98, Reset: 58s]
...
Request 15/15: 200 OK  [Limit: 100, Remaining: 85, Reset: 30s]

=== Summary ===
Successful:   15
Rate limited:  0
Total:        15
```

### Step 8: Generate a New API Key (Self-Service Flow)

In a production MaaS deployment, teams would request API keys through a self-service API or the OpenShift AI dashboard. Here is the manual equivalent -- creating a new API key Secret:

```bash
# Generate a random API key
NEW_KEY=$(openssl rand -hex 32)

# Create a Secret for a new team with a free-tier allocation
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: maas-key-free-team-analytics
  namespace: maas-config
  labels:
    app: maas-api-key
    maas-tier: free
    team: analytics
  annotations:
    maas.openshift.ai/created-by: admin@example.com
    maas.openshift.ai/created-at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    maas.openshift.ai/expires-at: "2026-12-31T23:59:59Z"
type: Opaque
stringData:
  api_key: "${NEW_KEY}"
EOF
```

Expected output:

```
secret/maas-key-free-team-analytics created
```

Authorino picks up the new Secret automatically (it watches the namespace). Test the new key immediately:

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${NEW_KEY}" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }'
```

Expected output:

```
200
```

To revoke an API key, delete the Secret:

```bash
oc delete secret maas-key-free-team-analytics -n maas-config
```

After deletion, requests with that key will return `401 Unauthorized`.

### Step 9: Monitor Usage with Prometheus Metrics

Limitador exports metrics that feed the showback dashboards. Query them directly:

```bash
# Port-forward to the Limitador metrics endpoint
oc port-forward svc/limitador -n kuadrant-system 9090:9090 &
PF_PID=$!

# Query rate-limit counters
curl -s "http://localhost:9090/metrics" | grep limitador_request
```

Expected output:

```
# HELP limitador_request_count Total number of requests processed
# TYPE limitador_request_count counter
limitador_request_count{namespace="maas-config/maas-tier-limits",tier="free",status="ok"} 10
limitador_request_count{namespace="maas-config/maas-tier-limits",tier="free",status="rate_limited"} 5
limitador_request_count{namespace="maas-config/maas-tier-limits",tier="premium",status="ok"} 15
limitador_request_count{namespace="maas-config/maas-tier-limits",tier="premium",status="rate_limited"} 0
```

These metrics integrate with the OpenShift AI showback dashboards (Technology Preview in 3.4). To view them in the OpenShift AI dashboard:

1. Navigate to **OpenShift AI Dashboard > Model Serving > Usage**.
2. Select the Gemma4-e4b model.
3. View per-key and per-tier request counts, token consumption, and error rates.

Clean up the port-forward:

```bash
kill $PF_PID 2>/dev/null
```

### Step 10: Production Hardening Checklist

Before moving MaaS to production, address these items:

**API key rotation:**

```bash
# Generate a new key for the same team/tier
NEW_ROTATED_KEY=$(openssl rand -hex 32)

# Create the replacement Secret (new name, same labels)
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: maas-key-premium-user1-v2
  namespace: maas-config
  labels:
    app: maas-api-key
    maas-tier: premium
    team: ml-platform
  annotations:
    maas.openshift.ai/rotated-from: maas-key-premium-user1
    maas.openshift.ai/created-at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
type: Opaque
stringData:
  api_key: "${NEW_ROTATED_KEY}"
EOF

# Give the team time to switch to the new key, then delete the old one
# oc delete secret maas-key-premium-user1 -n maas-config
```

**Redis high availability for Limitador:**

```bash
# Verify Limitador is using a persistent Redis backend
oc get deployment limitador -n kuadrant-system \
  -o jsonpath='{.spec.template.spec.containers[0].env}' | python3 -m json.tool
```

Look for `REDIS_URL` pointing to a Redis cluster (not a standalone instance). In production, use a Redis Sentinel or Redis Cluster deployment with persistent storage.

**Network policies:**

```bash
# Restrict direct access to the InferenceService -- force traffic through the gateway
cat <<'EOF' | oc apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-direct-inference
  namespace: gemma-model
  labels:
    app: maas-network-policy
    tutorial-level: "3"
    tutorial-module: "M1"
spec:
  podSelector:
    matchLabels:
      serving.kserve.io/inferenceservice: gemma-4-e4b
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kuadrant-system
EOF
```

This NetworkPolicy ensures that only traffic from the Kuadrant gateway namespace can reach the model pods. Application teams cannot bypass rate limits by calling the InferenceService directly.

## Verification

Run through this checklist to confirm MaaS is working end-to-end:

```bash
# 1. Unauthenticated request is rejected
curl -s -o /dev/null -w "No key: %{http_code}\n" \
  "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma-4-e4b","messages":[{"role":"user","content":"test"}],"max_tokens":5}'

# 2. Invalid key is rejected
curl -s -o /dev/null -w "Bad key: %{http_code}\n" \
  "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid-key-12345" \
  -d '{"model":"gemma-4-e4b","messages":[{"role":"user","content":"test"}],"max_tokens":5}'

# 3. Valid free key works
FREE_KEY=$(oc get secret maas-key-free-user1 -n maas-config \
  -o jsonpath='{.data.api_key}' | base64 -d)
curl -s -o /dev/null -w "Free key: %{http_code}\n" \
  "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${FREE_KEY}" \
  -d '{"model":"gemma-4-e4b","messages":[{"role":"user","content":"test"}],"max_tokens":5}'

# 4. Valid premium key works
PREMIUM_KEY=$(oc get secret maas-key-premium-user1 -n maas-config \
  -o jsonpath='{.data.api_key}' | base64 -d)
curl -s -o /dev/null -w "Premium key: %{http_code}\n" \
  "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${PREMIUM_KEY}" \
  -d '{"model":"gemma-4-e4b","messages":[{"role":"user","content":"test"}],"max_tokens":5}'

# 5. Rate limiting works (check headers)
curl -s -D - "${MAAS_ENDPOINT}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${FREE_KEY}" \
  -d '{"model":"gemma-4-e4b","messages":[{"role":"user","content":"test"}],"max_tokens":5}' \
  2>&1 | grep -E "HTTP|X-RateLimit"

# 6. AuthConfig and RateLimitPolicy exist
oc get authconfig maas-auth -n maas-config
oc get ratelimitpolicy maas-tier-limits -n maas-config
```

Expected verification output:

```
No key: 401
Bad key: 401
Free key: 200
Premium key: 200
HTTP/2 200
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 52
NAME        READY   HOSTS
maas-auth   True    ["gemma-maas.apps.sandbox.example.com"]
NAME               TARGETREF KIND   TARGETREF NAME     AGE
maas-tier-limits   HTTPRoute        gemma-model-route  10m
```

## Key Takeaways

- **MaaS eliminates model duplication.** A single model deployment, governed by Kuadrant, serves all teams -- reducing GPU waste and operational complexity.
- **Kuadrant separates authentication from rate limiting.** Authorino handles API key validation and tier extraction; Limitador enforces per-tier rate limits. Both plug into the Gateway API request flow as Envoy filters.
- **API keys are Kubernetes Secrets.** This means standard Kubernetes RBAC controls who can create, read, and delete keys. Tier assignment is a label on the Secret -- Authorino reads it at request time.
- **Rate limiting is declarative.** The RateLimitPolicy CRD defines limits per tier. Changing a limit is a `kubectl apply` -- no code changes, no restarts.
- **Showback metrics come for free.** Limitador exports Prometheus metrics that feed usage dashboards, enabling chargeback without additional instrumentation.

## Cleanup

Remove all resources created in this lesson:

```bash
# Delete the RateLimitPolicy
oc delete ratelimitpolicy maas-tier-limits -n maas-config

# Delete the AuthConfig
oc delete authconfig maas-auth -n maas-config

# Delete the HTTPRoute
oc delete httproute gemma-model-route -n maas-config

# Delete all MaaS API key Secrets
oc delete secrets -n maas-config -l app=maas-api-key

# Delete the tier ConfigMap
oc delete configmap maas-tier-config -n maas-config

# Delete the NetworkPolicy (if applied)
oc delete networkpolicy deny-direct-inference -n gemma-model 2>/dev/null

# Delete the MaaS namespace
oc delete project maas-config
```

Expected output:

```
ratelimitpolicy.kuadrant.io "maas-tier-limits" deleted
authconfig.authorino.kuadrant.io "maas-auth" deleted
httproute.gateway.networking.k8s.io "gemma-model-route" deleted
secret "maas-key-free-user1" deleted
secret "maas-key-premium-user1" deleted
configmap "maas-tier-config" deleted
project.project.openshift.io "maas-config" deleted
```

## Next Steps

In [L3-M1.4 -- NeMo Guardrails](../4_nemo_guardrails/), you will add content safety guardrails to the model endpoint. Where MaaS controls who can access the model and how much, NeMo Guardrails controls what the model is allowed to say -- blocking harmful, off-topic, or policy-violating outputs before they reach the client. The two layers complement each other: MaaS handles the access plane, NeMo Guardrails handles the content plane.
