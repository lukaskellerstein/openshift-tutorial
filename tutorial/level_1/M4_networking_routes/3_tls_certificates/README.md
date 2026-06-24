# L1-M4.3 — TLS & Certificates

**Level:** Foundations
**Duration:** 30 min

## Overview

In Kubernetes, you manage TLS certificates manually -- creating Secrets, referencing them in Ingress resources, and often installing cert-manager to automate renewal. OpenShift simplifies this significantly: every cluster ships with a wildcard certificate that automatically secures Routes, and the Route API lets you attach custom certificates directly without creating separate Secret objects. This lesson walks through OpenShift's auto-generated certificates, shows you how to configure each TLS termination type (edge, passthrough, re-encrypt) with custom certs, and introduces cert-manager integration for automated certificate management.

## Prerequisites

- Completed: L1-M4.2 (Routes vs Ingress)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `developer` (`oc login -u developer -p developer https://api.crc.testing:6443`)
- `openssl` available on your machine (pre-installed on macOS and most Linux distributions)

## K8s Context

In vanilla Kubernetes, TLS for ingress traffic requires several manual steps:

1. **Generate or obtain a certificate** (self-signed, Let's Encrypt, or from your CA).
2. **Create a TLS Secret** containing the certificate and private key:
   ```bash
   kubectl create secret tls my-tls-secret \
     --cert=tls.crt \
     --key=tls.key
   ```
3. **Reference the Secret in an Ingress resource:**
   ```yaml
   apiVersion: networking.k8s.io/v1
   kind: Ingress
   spec:
     tls:
       - hosts:
           - my-app.example.com
         secretName: my-tls-secret
   ```
4. **Install an Ingress controller** (NGINX, Traefik, etc.) that handles TLS termination.
5. **Optionally install cert-manager** to automate certificate issuance and renewal.

There is no default certificate, no built-in TLS -- you must set everything up yourself.

## Concepts

### Auto-Generated Wildcard Certificates

Every OpenShift cluster generates a **wildcard certificate** during installation that covers `*.apps.<cluster_domain>` (e.g., `*.apps-crc.testing` in CRC). This certificate is:

- Automatically configured on the default Ingress Controller (HAProxy-based router)
- Applied to every Route that does not specify its own certificate
- Self-signed in CRC (which is why your browser shows a security warning)
- Issued by a real CA in production OpenShift installations (or replaced by your organization's CA)

This means that the moment you create a Route, it is TLS-enabled with the cluster's wildcard cert -- zero configuration required.

### TLS Termination Types on Routes

OpenShift Routes support three TLS termination strategies, each suited to different security requirements:

| Termination | Where TLS Ends | Backend Connection | Use Case |
|-------------|----------------|-------------------|----------|
| **Edge** | At the router | Unencrypted (HTTP) to pod | Most common. Simple setup, good performance. |
| **Passthrough** | At the pod | Encrypted end-to-end (router just forwards TCP) | App manages its own TLS. Required for non-HTTP protocols. |
| **Re-encrypt** | At the router, then re-encrypted | Encrypted to pod with a different cert | Maximum security. Router validates both external and internal certs. |

### Custom Certificates on Routes

Unlike Kubernetes Ingress (which references a Secret), OpenShift Routes embed certificate data **directly in the Route spec**:

```yaml
spec:
  tls:
    termination: edge
    certificate: |
      -----BEGIN CERTIFICATE-----
      ...
    key: |
      -----BEGIN RSA PRIVATE KEY-----
      ...
    caCertificate: |
      -----BEGIN CERTIFICATE-----
      ...
```

This is a deliberate design choice: the Route is self-contained, and you can inspect its TLS configuration with a single `oc get route -o yaml` command. No hunting for Secrets.

### Cert-Manager on OpenShift

For automated certificate lifecycle management (especially with Let's Encrypt or internal CAs), you can install **cert-manager** on OpenShift. It works the same way as on Kubernetes, with one addition: it can annotate Routes to trigger automatic certificate injection. The cert-manager operator is available through OperatorHub.

## Step-by-Step

### Step 1: Deploy a sample application

We need a simple HTTP application to expose through Routes. Deploy an NGINX-based app using the manifests in the `manifests/` directory:

```bash
oc new-project tls-demo --display-name="TLS Demo"
oc apply -f manifests/deployment.yaml
oc apply -f manifests/service.yaml
```

The deployment uses a UBI-based NGINX image that listens on port 8080 (compatible with OpenShift's restricted SCC since it does not require root).

Verify the pod is running:

```bash
oc get pods -l app=tls-demo
```

Expected output:

```
NAME                        READY   STATUS    RESTARTS   AGE
tls-demo-5d8f9b7c4-x2k9p   1/1     Running   0          30s
```

### Step 2: Observe the default wildcard certificate

Before creating any custom TLS Routes, examine the cluster's wildcard certificate. The Ingress Controller stores it in the `openshift-ingress` namespace:

```bash
oc get secret router-certs-default -n openshift-ingress -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -subject -issuer -dates
```

Expected output (CRC):

```
subject=CN = *.apps-crc.testing
issuer=CN = ingress-operator@...
notBefore=...
notAfter=...
```

The wildcard `*.apps-crc.testing` means any Route under this domain gets TLS automatically.

### Step 3: Create an edge-terminated Route with the default certificate

Create a basic Route that relies on the cluster's wildcard certificate:

```bash
oc apply -f manifests/route-edge-default.yaml
```

Test it:

```bash
oc get route tls-demo-edge-default -o jsonpath='{.spec.host}'
# Expected: tls-demo-edge-default-tls-demo.apps-crc.testing

curl -k https://tls-demo-edge-default-tls-demo.apps-crc.testing
```

The `-k` flag tells curl to accept the self-signed certificate (expected in CRC). You should see the NGINX welcome page. The Route is encrypted with the cluster's wildcard cert -- you did not supply any certificate.

### Step 4: Generate self-signed certificates for custom TLS demos

For the remaining steps, we need custom certificates. Use the provided script to generate a CA and server certificates:

```bash
bash scripts/generate-certs.sh
```

This script creates:
- `certs/ca.crt` and `certs/ca.key` -- A self-signed Certificate Authority
- `certs/server.crt` and `certs/server.key` -- A server certificate signed by the CA, valid for `*.apps-crc.testing`

You can also generate them manually:

```bash
# Create output directory
mkdir -p certs

# Generate CA key and certificate
openssl genrsa -out certs/ca.key 4096
openssl req -x509 -new -nodes -key certs/ca.key -sha256 -days 365 \
  -out certs/ca.crt -subj "/CN=Tutorial Demo CA"

# Generate server key and CSR
openssl genrsa -out certs/server.key 4096
openssl req -new -key certs/server.key \
  -out certs/server.csr -subj "/CN=*.apps-crc.testing"

# Sign the server certificate with our CA
openssl x509 -req -in certs/server.csr -CA certs/ca.crt -CAkey certs/ca.key \
  -CAcreateserial -out certs/server.crt -days 365 -sha256
```

### Step 5: Create an edge-terminated Route with a custom certificate

Edge termination is the most common TLS strategy: the router terminates TLS and forwards plain HTTP to the pod. Use the `oc create route` command to create a Route with your custom certificate:

```bash
oc create route edge tls-demo-edge-custom \
  --service=tls-demo \
  --port=8080 \
  --cert=certs/server.crt \
  --key=certs/server.key \
  --ca-cert=certs/ca.crt \
  --hostname=tls-demo-edge-custom-tls-demo.apps-crc.testing
```

The manifest at `manifests/route-edge-custom.yaml` shows the equivalent YAML structure for reference. In practice, the `oc create route` command is easier because it reads certificate files directly.

Verify the Route was created with TLS:

```bash
oc get route tls-demo-edge-custom -o jsonpath='{.spec.tls.termination}'
# Expected: edge
```

Test the connection:

```bash
curl -k https://tls-demo-edge-custom-tls-demo.apps-crc.testing
```

### Step 6: Create a passthrough Route

Passthrough termination forwards encrypted traffic directly to the pod -- the application itself must handle TLS. This requires a pod that serves HTTPS.

First, create a TLS Secret for the application to use:

```bash
oc create secret tls tls-demo-passthrough-cert \
  --cert=certs/server.crt \
  --key=certs/server.key
```

Deploy an NGINX instance configured with TLS. The deployment mounts the TLS secret and uses a custom NGINX config that serves HTTPS on port 8443:

```bash
oc apply -f manifests/nginx-tls-configmap.yaml
oc apply -f manifests/deployment-tls.yaml
oc apply -f manifests/service-tls.yaml
```

Wait for the TLS-enabled pod to start:

```bash
oc get pods -l app=tls-demo-passthrough
```

Expected output:

```
NAME                                    READY   STATUS    RESTARTS   AGE
tls-demo-passthrough-7b9f8d6c5-m3k7p   1/1     Running   0          30s
```

Now create the passthrough Route:

```bash
oc apply -f manifests/route-passthrough.yaml
```

Test it:

```bash
curl -k https://tls-demo-passthrough-tls-demo.apps-crc.testing
```

Expected output:

```
TLS passthrough backend is working!
```

The key difference from edge: the router does not decrypt the traffic. The TLS handshake happens directly between the client (curl) and the NGINX pod.

### Step 7: Create a re-encrypt Route

Re-encrypt is the most secure termination type: the router terminates the external TLS connection, then opens a **new** TLS connection to the backend pod. This means traffic is encrypted at every hop.

Re-encrypt uses the same TLS-enabled backend from Step 6. Create the re-encrypt Route:

```bash
oc create route reencrypt tls-demo-reencrypt \
  --service=tls-demo-passthrough \
  --port=8443 \
  --cert=certs/server.crt \
  --key=certs/server.key \
  --ca-cert=certs/ca.crt \
  --dest-ca-cert=certs/ca.crt \
  --hostname=tls-demo-reencrypt-tls-demo.apps-crc.testing
```

Notice the `--dest-ca-cert` flag -- this is the CA certificate that the router uses to **verify the backend pod's certificate**. This is unique to re-encrypt and does not exist in edge or passthrough.

The manifest at `manifests/route-reencrypt.yaml` shows the equivalent YAML structure. Note the `destinationCACertificate` field, which is the OpenShift-specific addition that enables backend certificate verification.

Test it:

```bash
curl -k https://tls-demo-reencrypt-tls-demo.apps-crc.testing
```

Expected output:

```
TLS passthrough backend is working!
```

Verify the termination type:

```bash
oc get route tls-demo-reencrypt -o jsonpath='{.spec.tls.termination}'
# Expected: reencrypt
```

### Step 8: Compare all Routes side by side

List all Routes and their TLS configuration:

```bash
oc get routes -o custom-columns=\
NAME:.metadata.name,\
HOST:.spec.host,\
TLS:.spec.tls.termination,\
INSECURE:.spec.tls.insecureEdgeTerminationPolicy
```

Expected output:

```
NAME                      HOST                                                TLS          INSECURE
tls-demo-edge-default     tls-demo-edge-default-tls-demo.apps-crc.testing     edge         Redirect
tls-demo-edge-custom      tls-demo-edge-custom-tls-demo.apps-crc.testing      edge         <none>
tls-demo-passthrough      tls-demo-passthrough-tls-demo.apps-crc.testing      passthrough  <none>
tls-demo-reencrypt        tls-demo-reencrypt-tls-demo.apps-crc.testing        reencrypt    <none>
```

### Step 9: Understand cert-manager integration (conceptual)

In production, you would not manually generate and embed certificates. Instead, you would use **cert-manager** to automate this:

1. **Install cert-manager** from OperatorHub:
   ```bash
   # In the Web Console: Operators -> OperatorHub -> search "cert-manager"
   # Or via CLI (requires cluster-admin):
   oc apply -f manifests/cert-manager-issuer.yaml  # example ClusterIssuer
   ```

2. **Annotate Routes** to request automatic certificates:
   ```yaml
   metadata:
     annotations:
       cert-manager.io/issuer-name: letsencrypt-prod
       cert-manager.io/issuer-kind: ClusterIssuer
   ```

3. cert-manager watches for these annotations, requests a certificate from the configured issuer (e.g., Let's Encrypt), and injects it into the Route.

The manifest at `manifests/cert-manager-issuer.yaml` shows an example ClusterIssuer configuration. Note that this requires cert-manager to be installed and will not work in CRC without additional setup.

## Verification

Run these commands to verify the lesson is complete:

```bash
# 1. Edge route with default cert exists and is accessible
oc get route tls-demo-edge-default -o jsonpath='{.spec.tls.termination}'
# Expected: edge

# 2. Edge route with custom cert exists
oc get route tls-demo-edge-custom -o jsonpath='{.spec.tls.termination}'
# Expected: edge

# 3. Passthrough route exists
oc get route tls-demo-passthrough -o jsonpath='{.spec.tls.termination}'
# Expected: passthrough

# 4. Re-encrypt route exists with destination CA
oc get route tls-demo-reencrypt -o jsonpath='{.spec.tls.termination}'
# Expected: reencrypt

# 5. All routes respond (will show NGINX welcome page or similar)
curl -sk https://tls-demo-edge-default-tls-demo.apps-crc.testing | head -5
curl -sk https://tls-demo-passthrough-tls-demo.apps-crc.testing | head -5
curl -sk https://tls-demo-reencrypt-tls-demo.apps-crc.testing | head -5
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Default TLS | None -- must install and configure | Wildcard certificate auto-generated for `*.apps.<domain>` |
| Certificate storage | TLS Secrets referenced by Ingress | Embedded directly in Route spec (or use Secrets) |
| TLS termination options | Depends on Ingress controller | Built-in: edge, passthrough, re-encrypt |
| Ingress controller | Must install separately (NGINX, Traefik, etc.) | HAProxy router pre-installed and configured |
| Re-encrypt support | Rare -- requires specific controller config | Native `re-encrypt` termination type |
| Destination CA verification | Controller-dependent | Built-in `destinationCACertificate` field on Routes |
| Cert-manager | Install manually | Available via OperatorHub operator |
| HTTP-to-HTTPS redirect | Ingress annotation (controller-specific) | `insecureEdgeTerminationPolicy: Redirect` on Route |
| CLI cert management | `kubectl create secret tls` | `oc create route edge --cert --key --ca-cert` |

## Key Takeaways

- OpenShift auto-generates a wildcard TLS certificate during installation, so every Route gets HTTPS out of the box with zero configuration.
- Routes support three TLS termination types: **edge** (most common, TLS ends at router), **passthrough** (TLS ends at pod), and **re-encrypt** (TLS at both hops -- most secure).
- Unlike Kubernetes Ingress, OpenShift Routes embed certificate data directly in the Route spec, making TLS configuration self-contained and inspectable.
- Re-encrypt termination is an OpenShift-native feature that provides end-to-end encryption with certificate validation at the router -- rarely available in vanilla Kubernetes without custom Ingress controller configuration.
- For production use, integrate cert-manager (available via OperatorHub) to automate certificate issuance and renewal rather than managing certificates manually.

## Cleanup

```bash
# Delete all routes
oc delete route tls-demo-edge-default tls-demo-edge-custom tls-demo-passthrough tls-demo-reencrypt

# Delete deployments, services, configmaps, and secrets
oc delete deployment tls-demo tls-demo-passthrough
oc delete service tls-demo tls-demo-passthrough
oc delete configmap nginx-tls-config
oc delete secret tls-demo-passthrough-cert

# Remove generated certificates
rm -rf certs/

# Delete the project
oc delete project tls-demo
```

## Next Steps

In **L1-M4.4 — Network Policies**, you will learn how OpenShift applies the same Kubernetes NetworkPolicy resources but with different defaults -- including deny-by-default behavior in multi-tenant mode and OpenShift-specific EgressFirewall resources for controlling outbound traffic.
