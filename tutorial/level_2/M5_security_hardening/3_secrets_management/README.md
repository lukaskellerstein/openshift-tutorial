# L2-M5.3 — Secrets Management

**Level:** Practitioner
**Duration:** 30 min

## Overview

In Kubernetes you store secrets as base64-encoded values in `Secret` objects -- workable, but dangerous to commit to Git and impossible to centralize across clusters. OpenShift supports the same primitives, but production teams layer on purpose-built tools: **Sealed Secrets** (Bitnami) for encrypting secrets into Git, the **External Secrets Operator** for pulling secrets from external stores (Vault, AWS Secrets Manager, Azure Key Vault), and **HashiCorp Vault** for full secrets lifecycle management. This lesson walks you through all three approaches and shows how to rotate secrets safely on a running cluster.

## Prerequisites

- Completed: L1-M5.3 (ConfigMaps & Secrets)
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` and `kubectl` CLIs installed
- `kubeseal` CLI installed (for Sealed Secrets section)
- Cluster-admin access (for installing operators)

## K8s Context

You already know Kubernetes `Secret` objects: opaque key-value pairs, base64-encoded (not encrypted), mountable as volumes or injected as environment variables. You know the problem: those Secrets live in etcd (optionally encrypted at rest), but the YAML manifests you write are plaintext base64 -- you cannot commit them to Git without exposing credentials. In vanilla K8s, you work around this with external tools or manual `kubectl create secret` commands. OpenShift does not change how Secrets themselves work, but the ecosystem around OpenShift provides cleaner answers.

## Concepts

### Sealed Secrets (Bitnami)

Sealed Secrets adds a controller to the cluster and a CLI tool (`kubeseal`) to the developer's workstation. You encrypt a regular `Secret` into a `SealedSecret` custom resource using the controller's public key. Only the controller (which holds the private key) can decrypt it. The `SealedSecret` YAML is safe to commit to Git because it is asymmetrically encrypted -- not merely encoded.

**How it works:**
1. Developer creates a standard Kubernetes `Secret` locally.
2. `kubeseal` encrypts it against the cluster's Sealed Secrets controller public key.
3. The resulting `SealedSecret` CR is committed to Git.
4. When applied to the cluster, the controller decrypts the `SealedSecret` and creates a real `Secret`.

### External Secrets Operator (ESO)

The External Secrets Operator syncs secrets from external providers (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager) into Kubernetes `Secret` objects. You define an `ExternalSecret` CR that declares which key to fetch and where to store it. The operator handles retrieval and refresh on a configurable interval, enabling automatic rotation.

**Key CRDs:**
- `SecretStore` / `ClusterSecretStore` -- connection details for the external provider.
- `ExternalSecret` -- maps an external secret to a Kubernetes `Secret`.

### HashiCorp Vault Integration

Vault is the most feature-rich option: dynamic secrets, leasing, revocation, audit logging, and fine-grained ACLs. On OpenShift, you can integrate Vault via:
- **Vault Agent Injector** -- sidecar that injects secrets into pods as files.
- **External Secrets Operator** -- pulls Vault secrets into K8s Secrets (covered above).
- **CSI Secrets Store Driver** -- mounts Vault secrets as CSI volumes.

### Secret Rotation

Production clusters must rotate secrets regularly. The approach depends on your tool:
- **Sealed Secrets**: re-encrypt with `kubeseal`, update the Git manifest, let GitOps sync.
- **ESO**: update the value in the external store; the operator re-syncs on its refresh interval.
- **Vault**: use dynamic secrets with short TTLs -- Vault generates fresh credentials automatically.

### Why OpenShift Cares

OpenShift's security-first posture (SCCs, restricted by default, built-in OAuth) means secrets management is not optional -- it is expected. The OperatorHub makes installing Sealed Secrets and the External Secrets Operator a catalog experience rather than a manual Helm install. OpenShift's built-in etcd encryption (configurable via the API server) provides defense-in-depth alongside these tools.

## Step-by-Step

### Step 1: Create a Project

```bash
oc new-project secrets-management-lab
```

Expected output:
```
Now using project "secrets-management-lab" on server "https://api.crc.testing:6443".
```

---

### Step 2: Install the Sealed Secrets Controller

Install the Sealed Secrets controller using the Helm chart or from a manifest. For CRC, we use the upstream release directly:

```bash
# Install the Sealed Secrets controller into the kube-system namespace
oc apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.5/controller.yaml
```

> **Note:** On a production OpenShift cluster, you may install Sealed Secrets via OperatorHub if a community operator is available, or use a Helm chart managed by GitOps.

Verify the controller is running:

```bash
oc get pods -n kube-system -l name=sealed-secrets-controller
```

Expected output:
```
NAME                                          READY   STATUS    RESTARTS   AGE
sealed-secrets-controller-6f4b5b6b9c-x7k2m   1/1     Running   0          30s
```

### Step 3: Create a SealedSecret

First, create a regular Secret manifest locally (do NOT apply it to the cluster):

```bash
oc create secret generic db-credentials \
  --from-literal=username=appuser \
  --from-literal=password='S3cur3P@ssw0rd!' \
  --dry-run=client -o yaml > /tmp/db-secret.yaml
```

Now encrypt it with `kubeseal`:

```bash
kubeseal --format yaml < /tmp/db-secret.yaml > manifests/sealedsecret-db-credentials.yaml
```

> **Important:** The `kubeseal` CLI contacts the controller to fetch its public certificate. If your cluster uses a custom CA, pass `--cert` with the public cert file.

Examine the generated `SealedSecret`:

```bash
cat manifests/sealedsecret-db-credentials.yaml
```

The output looks like the manifest in `manifests/sealedsecret-db-credentials.yaml` -- the `encryptedData` fields are encrypted strings that only the cluster's controller can decrypt.

Apply the `SealedSecret` to the cluster:

```bash
oc apply -f manifests/sealedsecret-db-credentials.yaml
```

Verify the controller created the corresponding `Secret`:

```bash
oc get secret db-credentials -o yaml
```

Expected output (abbreviated):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
  namespace: secrets-management-lab
type: Opaque
data:
  password: UzNjdXIzUEBzc3cwcmQh
  username: YXBwdXNlcg==
```

> **Troubleshooting:** If the Secret does not appear, check the controller logs:
> `oc logs -n kube-system -l name=sealed-secrets-controller`

---

### Step 4: Deploy an App That Consumes the Secret

Apply the sample deployment that mounts the sealed secret as environment variables:

```bash
oc apply -f manifests/deployment-with-secret.yaml
oc apply -f manifests/service.yaml
```

Verify the pod can read the secret values:

```bash
oc wait --for=condition=Ready pod -l app=secret-demo --timeout=60s
oc exec $(oc get pod -l app=secret-demo -o jsonpath='{.items[0].metadata.name}') \
  -- env | grep -E 'DB_USERNAME|DB_PASSWORD'
```

Expected output:
```
DB_USERNAME=appuser
DB_PASSWORD=S3cur3P@ssw0rd!
```

---

### Step 5: Install the External Secrets Operator

Install ESO from OperatorHub (preferred on OpenShift):

```bash
oc apply -f manifests/eso-subscription.yaml
```

Wait for the operator to become available:

```bash
oc get csv -n openshift-operators -w
```

Wait until the `external-secrets-operator` CSV shows `Succeeded`:

```
NAME                                 DISPLAY                    PHASE
external-secrets-operator.v0.9.11   External Secrets Operator  Succeeded
```

> **Note:** On CRC with limited resources, the operator may take 2-3 minutes to start. If the install plan requires approval, run:
> `oc get installplan -n openshift-operators` and approve it manually.

---

### Step 6: Configure a SecretStore (Vault Example)

For this step, we simulate a Vault backend. In production, you would point to a real Vault instance or AWS Secrets Manager.

First, create a token secret that ESO uses to authenticate with Vault:

```bash
oc create secret generic vault-token \
  --from-literal=token=hvs.EXAMPLE_TOKEN_VALUE \
  -n secrets-management-lab
```

Apply the SecretStore that connects to Vault:

```bash
oc apply -f manifests/secretstore-vault.yaml
```

Verify the SecretStore is healthy:

```bash
oc get secretstore vault-backend -o jsonpath='{.status.conditions[0].message}'
```

Expected output (when Vault is reachable):
```
store validated
```

> **Troubleshooting:** If the status shows an error, verify the Vault address is reachable from the cluster and the token has the correct policies. Common issues:
> - `connection refused` -- Vault is not running or not accessible from the pod network.
> - `permission denied` -- the token lacks the required Vault policy.

---

### Step 7: Create an ExternalSecret

Apply the ExternalSecret that pulls a secret from Vault and creates a Kubernetes Secret:

```bash
oc apply -f manifests/externalsecret-api-key.yaml
```

Check the sync status:

```bash
oc get externalsecret api-credentials -o jsonpath='{.status.conditions[0].message}'
```

Expected output (when Vault is configured and accessible):
```
Secret was synced
```

Verify the resulting Kubernetes Secret was created:

```bash
oc get secret api-credentials -o jsonpath='{.data.api-key}' | base64 -d
```

---

### Step 8: Secret Rotation with External Secrets

ESO refreshes secrets on the interval defined in the ExternalSecret's `refreshInterval`. To simulate rotation:

1. Update the secret value in your external store (Vault, AWS SM, etc.).
2. Wait for the refresh interval to elapse (or delete the Secret to force re-sync).
3. Verify the new value:

```bash
# Force re-sync by deleting the managed Secret
oc delete secret api-credentials
# ESO will recreate it with the latest value from Vault
oc get externalsecret api-credentials -o jsonpath='{.status.conditions[0].message}'
```

For workloads that mount secrets as environment variables, a pod restart is required to pick up new values. For volume-mounted secrets, Kubernetes updates the mounted files automatically (within the kubelet sync period, typically 1-2 minutes).

> **Production tip:** Use a `Deployment` annotation strategy to trigger rolling restarts on secret change:
> ```bash
> oc annotate deployment secret-demo \
>   kubectl.kubernetes.io/restartedAt="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
>   --overwrite
> ```

---

### Step 9: Rotate a Sealed Secret

To rotate a Sealed Secret:

1. Generate the new secret locally:
```bash
oc create secret generic db-credentials \
  --from-literal=username=appuser \
  --from-literal=password='N3wR0t@t3dP@ss!' \
  --dry-run=client -o yaml > /tmp/db-secret-rotated.yaml
```

2. Re-encrypt with `kubeseal`:
```bash
kubeseal --format yaml < /tmp/db-secret-rotated.yaml > manifests/sealedsecret-db-credentials.yaml
```

3. Commit the updated SealedSecret to Git and apply (or let GitOps sync):
```bash
oc apply -f manifests/sealedsecret-db-credentials.yaml
```

4. Restart the deployment to pick up the new values:
```bash
oc rollout restart deployment/secret-demo
oc rollout status deployment/secret-demo
```

---

### Step 10: Enable etcd Encryption (Cluster-Admin)

OpenShift supports encrypting Secret data at rest in etcd. This is a cluster-level setting:

```bash
oc patch apiserver cluster --type merge \
  -p '{"spec":{"encryption":{"type":"aescbc"}}}'
```

Verify the encryption migration status:

```bash
oc get openshiftapiserver -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Encrypted")]}{"\n"}{end}'
```

> **Note:** This is a cluster-wide operation that encrypts all Secrets and ConfigMaps in etcd. It takes several minutes to complete the migration. Supported encryption types are `aescbc` (AES-CBC) and `aesgcm` (AES-GCM).

## Verification

Run through this checklist to confirm everything works:

```bash
# 1. SealedSecret created a real Secret
oc get secret db-credentials -n secrets-management-lab
# Expected: db-credentials secret exists

# 2. Deployment reads secret values
oc exec $(oc get pod -l app=secret-demo -o jsonpath='{.items[0].metadata.name}') \
  -- env | grep DB_
# Expected: DB_USERNAME and DB_PASSWORD are set

# 3. External Secrets Operator is installed
oc get csv -n openshift-operators | grep external-secrets
# Expected: CSV in Succeeded phase

# 4. SecretStore and ExternalSecret are configured
oc get secretstore vault-backend
oc get externalsecret api-credentials
# Expected: Both resources exist

# 5. etcd encryption status (cluster-admin only)
oc get openshiftapiserver -o jsonpath='{.items[*].status.conditions[?(@.type=="Encrypted")].status}'
# Expected: "True" (after migration completes)
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Secret storage | base64 in etcd, encryption optional | Same, but etcd encryption configurable via `apiserver` CR |
| Sealed Secrets install | Helm chart or raw manifests | Same, or via OperatorHub community operator |
| External Secrets Operator | Helm chart install | OperatorHub install (catalog experience) |
| Vault integration | Manual Helm install of injector | OperatorHub or Helm; works with OpenShift OAuth |
| Secret rotation | Manual process | Same tools, but ESO refresh + GitOps makes it declarative |
| etcd encryption | `EncryptionConfiguration` in API server manifest | `oc patch apiserver cluster` -- managed declaratively |
| Operator management | Install OLM yourself, then operators | OLM pre-installed, OperatorHub built into console |
| GitOps integration | Install ArgoCD yourself | OpenShift GitOps operator pre-integrated |

## Key Takeaways

- **Never commit plaintext Secrets to Git.** Use Sealed Secrets to encrypt them asymmetrically so only the cluster can decrypt, or use External Secrets Operator to pull from an external store.
- **External Secrets Operator centralizes secret management** across clusters by syncing from providers like Vault, AWS Secrets Manager, and Azure Key Vault -- with automatic refresh for rotation.
- **HashiCorp Vault provides the richest feature set** (dynamic secrets, leasing, audit logging) and integrates with OpenShift via the Agent Injector, ESO, or CSI driver.
- **Secret rotation requires a pod restart for env-var-mounted secrets** but volume-mounted secrets update automatically via kubelet sync.
- **OpenShift's OperatorHub simplifies installation** of secrets management tools compared to vanilla K8s, and etcd encryption is a single `oc patch` command rather than manual API server configuration.

## Cleanup

```bash
# Delete the demo application and secrets
oc delete -f manifests/deployment-with-secret.yaml
oc delete -f manifests/service.yaml
oc delete -f manifests/externalsecret-api-key.yaml
oc delete -f manifests/secretstore-vault.yaml
oc delete -f manifests/sealedsecret-db-credentials.yaml
oc delete secret db-credentials vault-token api-credentials 2>/dev/null

# Remove the Sealed Secrets controller
oc delete -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.5/controller.yaml

# Delete the External Secrets Operator subscription (optional -- keeps operator for other projects)
oc delete -f manifests/eso-subscription.yaml

# Revert etcd encryption (optional, cluster-admin)
# oc patch apiserver cluster --type merge -p '{"spec":{"encryption":{"type":"identity"}}}'

# Delete the project
oc delete project secrets-management-lab
```

## Next Steps

In **L2-M5.4 (Compliance & Auditing)**, you will use the Compliance Operator to run OpenSCAP scans against CIS benchmarks, configure audit logging, and build a compliance pipeline that verifies your cluster meets security baselines -- including verifying that secrets are properly encrypted at rest.
