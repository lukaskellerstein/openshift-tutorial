# L2-M5.1 — Image Security & Compliance

**Level:** Practitioner
**Duration:** 30 min

## Overview

In Kubernetes, you can pull and run any container image from any registry with no restrictions by default. OpenShift takes a fundamentally different approach: it provides built-in mechanisms for image signing, verification, admission policies, and security scanning to ensure that only trusted, compliant images run in your cluster. This lesson covers image signing and verification with GNU Privacy Guard (GPG), ImagePolicy admission to restrict which registries and images are allowed, the Red Hat container catalog and Universal Base Images (UBI), and Quay registry security scanning powered by Clair.

## Prerequisites

- Completed: L1-M2.4 — Security Context Constraints (SCCs)
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI installed and authenticated
- Basic familiarity with container registries and image references

## K8s Context

In vanilla Kubernetes, there are no built-in controls over which container images can run in your cluster. Any pod can reference any image from any registry. To restrict images, you need external tools:

- **Admission webhooks** — you write and deploy your own webhook server to validate image references.
- **OPA Gatekeeper / Kyverno** — third-party policy engines you install separately.
- **Image signing** — you set up Notary/Cosign and configure verification manually.
- **Vulnerability scanning** — you integrate Trivy, Anchore, or similar tools into your CI pipeline.

None of this is built into the platform. Every cluster operator must assemble their own image security stack.

## Concepts

### Image Signing and Verification

OpenShift supports GPG-based image signing via the Machine Config Operator. Signed images carry a cryptographic signature that proves they came from a trusted publisher and have not been tampered with. OpenShift nodes can be configured to verify these signatures before allowing an image to be pulled.

The signing workflow consists of:
1. **Sign** the image using `podman image sign` or `skopeo copy --sign-by`.
2. **Store** signatures in a signature store (a web server or registry extension).
3. **Configure** cluster nodes to require signatures from trusted keys via `/etc/containers/policy.json`.

### ImagePolicy Admission

OpenShift includes a built-in `ImagePolicy` admission plugin (part of the `image.openshift.io` API) that controls which images can be deployed. This is configured through the `ClusterImagePolicy` and `ImagePolicy` custom resources, as well as the legacy `imagepolicy` admission configuration. Key capabilities include:

- **Restrict registries** — allow images only from approved registries (e.g., `registry.redhat.io`, your private Quay instance).
- **Require signed images** — reject images that lack valid signatures.
- **Resolve tags to digests** — prevent tag mutation attacks by forcing images to be pulled by digest.
- **Block specific images** — deny images matching certain patterns.

### Red Hat Container Catalog and UBI

Red Hat provides the **Red Hat Ecosystem Catalog** (catalog.redhat.com) with thousands of certified, security-scanned container images. These images are:

- **Scanned** for known CVEs by Red Hat Product Security.
- **Rebuilt** regularly with security patches.
- **Certified** to run on OpenShift with proper SCC compliance (non-root by default).
- **Supported** under Red Hat subscriptions.

**Universal Base Images (UBI)** are a subset of Red Hat Enterprise Linux (RHEL) images that are freely redistributable. UBI images come in several variants:

| UBI Variant | Use Case | Image Reference |
|-------------|----------|-----------------|
| `ubi9` | Full RHEL user space | `registry.access.redhat.com/ubi9/ubi` |
| `ubi9-minimal` | Minimal footprint (~35 MB) | `registry.access.redhat.com/ubi9/ubi-minimal` |
| `ubi9-micro` | Distroless-style (~12 MB) | `registry.access.redhat.com/ubi9/ubi-micro` |
| `ubi9-init` | Systemd-based services | `registry.access.redhat.com/ubi9/ubi-init` |

UBI images run as non-root by default, making them SCC-compatible on OpenShift without modification.

### Quay Registry and Clair Security Scanning

**Red Hat Quay** is an enterprise container registry that integrates **Clair**, an open-source vulnerability scanner. Clair automatically scans every image pushed to Quay and reports:

- Known CVEs from the National Vulnerability Database (NVD).
- Package-level vulnerability details (which RPM or pip/npm package is affected).
- Severity ratings (Critical, High, Medium, Low).
- Fixable vs unfixable vulnerabilities.

On OpenShift, the Quay operator can be deployed in-cluster, giving you a fully integrated registry with security scanning. The Quay Container Security Operator exposes scan results directly in the OpenShift Web Console.

## Step-by-Step

### Step 1: Set Up the Project

Create a dedicated project for this lesson.

```bash
oc new-project image-security-lab
```

Expected output:
```
Now using project "image-security-lab" on server "https://api.crc.testing:6443".
```

### Step 2: Deploy an Application Using UBI Base Images

First, let us examine why UBI images are the recommended base for OpenShift workloads. Deploy a simple application built on UBI.

```bash
oc apply -f manifests/ubi-deployment.yaml
```

Verify the deployment uses a UBI-based image:

```bash
oc get deployment ubi-demo -o jsonpath='{.spec.template.spec.containers[0].image}'
```

Expected output:
```
registry.access.redhat.com/ubi9/ubi-minimal:9.4
```

Wait for the pod to become ready:

```bash
oc rollout status deployment/ubi-demo --timeout=120s
```

Inspect the running container's user context to confirm it runs as non-root:

```bash
oc exec deployment/ubi-demo -- id
```

Expected output:
```
uid=1000680000(1000680000) gid=0(root) groups=0(root),1000680000
```

The UID is a randomly assigned, unprivileged user ID — this is OpenShift's `restricted` SCC in action (as you learned in L1-M2.4).

### Step 3: Compare with a Non-UBI Image

Deploy a standard Docker Hub image to see the difference:

```bash
oc apply -f manifests/dockerhub-deployment.yaml
```

Check the pod status:

```bash
oc get pods -l app=dockerhub-demo
```

If the image tries to run as root or bind to a privileged port, you will see the pod fail:

```
NAME                              READY   STATUS             RESTARTS   AGE
dockerhub-demo-6b8c9f7d4a-x2k1p  0/1     CrashLoopBackOff   3          2m
```

Inspect the failure reason:

```bash
oc logs deployment/dockerhub-demo
```

This demonstrates why Red Hat recommends UBI-based images for OpenShift: they are designed to work within the `restricted` SCC by default.

### Step 4: Apply an ImagePolicy to Restrict Allowed Registries

In a production environment, you want to ensure that only images from trusted registries can be deployed. Apply an `ImagePolicy` configuration.

First, review the image policy manifest:

```yaml
# manifests/image-policy.yaml
apiVersion: config.openshift.io/v1
kind: Image
metadata:
  name: cluster
spec:
  registrySources:
    allowedRegistries:
      - registry.access.redhat.com
      - registry.redhat.io
      - quay.io
      - image-registry.openshift-image-registry.svc:5000
      - registry.crc.testing:5000
```

Apply the cluster-wide image policy (requires cluster-admin):

```bash
oc login -u kubeadmin https://api.crc.testing:6443
oc apply -f manifests/image-policy.yaml
```

Expected output:
```
image.config.openshift.io/cluster configured
```

> **Important:** This change is cluster-wide and affects all projects. The Machine Config Operator will roll the change out to all nodes. On CRC with a single node, the update takes approximately 5-10 minutes as the node reconfigures and restarts.

Monitor the Machine Config Operator update:

```bash
oc get machineconfigpool master -w
```

Wait until `UPDATED` shows `True` and `UPDATING` shows `False`:
```
NAME     CONFIG                            UPDATED   UPDATING   DEGRADED   MACHINECOUNT   READYCOUNT
master   rendered-master-abc123            True      False      False      1              1
```

### Step 5: Verify the Image Policy Enforcement

Switch back to the developer user:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc project image-security-lab
```

Try to deploy an image from a registry that is not on the allowed list:

```bash
oc apply -f manifests/blocked-deployment.yaml
```

The deployment will be created, but the pod will fail to pull the image:

```bash
oc get events --field-selector reason=Failed --sort-by=.lastTimestamp
```

Expected output (after the image policy takes effect):
```
LAST SEEN   TYPE      REASON   OBJECT                                MESSAGE
30s         Warning   Failed   pod/blocked-demo-7d8c4f5b9a-m3k2p    Failed to pull image "docker.io/library/nginx:latest":
                                                                      registries "docker.io" not allowed
```

### Step 6: Configure Image Signature Verification

Image signature verification ensures that only cryptographically signed images from trusted publishers can be pulled. This is configured at the node level through Machine Config.

Review the signature verification manifest:

```yaml
# manifests/signature-verification-machineconfig.yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  name: 50-image-signature-policy
  labels:
    machineconfiguration.openshift.io/role: worker
spec:
  config:
    ignition:
      version: 3.2.0
    storage:
      files:
        - path: /etc/containers/policy.json
          mode: 0644
          overwrite: true
          contents:
            source: data:text/plain;charset=utf-8;base64,ewogICJkZWZhdWx0IjogWwogICAgewogICAgICAidHlwZSI6ICJyZWplY3QiCiAgICB9CiAgXSwKICAidHJhbnNwb3J0cyI6IHsKICAgICJkb2NrZXIiOiB7CiAgICAgICJyZWdpc3RyeS5hY2Nlc3MucmVkaGF0LmNvbSI6IFsKICAgICAgICB7CiAgICAgICAgICAidHlwZSI6ICJzaWduZWRCeSIsCiAgICAgICAgICAia2V5VHlwZSI6ICJHUEdLZXlzIiwKICAgICAgICAgICJrZXlQYXRoIjogIi9ldGMvcGtpL3JwbS1ncGcvUlBNLUdQRy1LRVktcmVkaGF0LXJlbGVhc2UiCiAgICAgICAgfQogICAgICBdLAogICAgICAicmVnaXN0cnkucmVkaGF0LmlvIjogWwogICAgICAgIHsKICAgICAgICAgICJ0eXBlIjogInNpZ25lZEJ5IiwKICAgICAgICAgICJrZXlUeXBlIjogIkdQR0tleXMiLAogICAgICAgICAgImtleVBhdGgiOiAiL2V0Yy9wa2kvcnBtLWdwZy9SUE0tR1BHLUtFWS1yZWRoYXQtcmVsZWFzZSIKICAgICAgICB9CiAgICAgIF0sCiAgICAgICJpbWFnZS1yZWdpc3RyeS5vcGVuc2hpZnQtaW1hZ2UtcmVnaXN0cnkuc3ZjOjUwMDAiOiBbCiAgICAgICAgewogICAgICAgICAgInR5cGUiOiAiaW5zZWN1cmVBY2NlcHRBbnl0aGluZyIKICAgICAgICB9CiAgICAgIF0KICAgIH0KICB9Cn0=
```

The base64-encoded content decodes to a `policy.json` that:
- **Rejects** all images by default.
- **Requires GPG signatures** for `registry.access.redhat.com` and `registry.redhat.io`.
- **Accepts any image** from the internal OpenShift registry (needed for S2I builds).

> **Note:** On CRC, applying MachineConfigs triggers a node reboot. In a production cluster with multiple workers, nodes are updated one at a time in a rolling fashion. For this lesson, you can review the manifest without applying it to avoid the reboot wait time.

To apply it (cluster-admin required):

```bash
oc login -u kubeadmin https://api.crc.testing:6443
# Only apply if you are prepared to wait for a node reboot (~5-10 min on CRC)
oc apply -f manifests/signature-verification-machineconfig.yaml
```

### Step 7: Explore Quay Security Scanning with Clair

In a production environment, Red Hat Quay with Clair provides automated vulnerability scanning. While setting up a full Quay instance is beyond this 30-minute lesson, you can explore the Quay Container Security Operator, which surfaces scan results from any Quay registry in the OpenShift Console.

Deploy a workload and inspect its image vulnerabilities using the `ImageManifestVuln` custom resource (available when the Quay Container Security Operator is installed):

```bash
# Check if the Container Security Operator is available
oc get csv -n openshift-operators | grep container-security
```

If the operator is installed, it creates `ImageManifestVuln` resources for any image with known vulnerabilities:

```bash
oc get imagemanifestvuln -n image-security-lab
```

Expected output (example):
```
NAME                              REGISTRY                        REPOSITORY        SEVERITY
sha256.abc123...                  registry.access.redhat.com      ubi9/ubi-minimal  Low
```

Get details on specific vulnerabilities:

```bash
oc get imagemanifestvuln -n image-security-lab -o json | \
  jq '.items[0].spec.features[] | select(.vulnerabilities != null) | {name: .name, version: .version, vulns: [.vulnerabilities[].name]}'
```

> **Tip:** Even without the Quay Container Security Operator installed, you can view image security data on the **Red Hat Ecosystem Catalog** at https://catalog.redhat.com/software/containers/search. Search for any Red Hat image to see its CVE report, health index, and package list.

### Step 8: Create a Namespace-Scoped Image Policy (ImageTagMirrorSet)

For more granular control, you can use an `ImageTagMirrorSet` to redirect image references to a trusted internal mirror, ensuring all pulls go through your scanned and approved registry:

```bash
oc login -u kubeadmin https://api.crc.testing:6443
oc apply -f manifests/image-tag-mirror-set.yaml
```

This redirects any pull from `docker.io/library` to your internal Quay mirror, so even if someone specifies a Docker Hub image, it will be served from your trusted, pre-scanned mirror.

### Step 9: View Image Security Status in the Web Console

OpenShift's Web Console provides a visual overview of image security:

1. Open the Web Console at https://console-openshift-console.apps-crc.testing.
2. Switch to the **Administrator** perspective.
3. Navigate to **Administration > Cluster Settings > Configuration**.
4. Click on **Image** to see the cluster image policy.
5. Navigate to **Workloads > Pods** in the `image-security-lab` project.
6. Click on a pod and view the **Events** tab to see image pull status.
7. If the Container Security Operator is installed, check **Home > Overview** for a vulnerability summary dashboard.

## Verification

Run these checks to verify the lesson is working:

```bash
# 1. Confirm UBI deployment is running
oc get deployment ubi-demo -n image-security-lab \
  -o jsonpath='{.status.readyReplicas}'
# Expected: 1

# 2. Confirm UBI pod runs as non-root
oc exec deployment/ubi-demo -n image-security-lab -- id
# Expected: uid=1000680000 (or similar non-root UID)

# 3. Check the cluster image policy
oc get image.config.openshift.io/cluster -o yaml
# Expected: registrySources.allowedRegistries includes your trusted registries

# 4. Verify image pull from blocked registry fails (after policy takes effect)
oc get events -n image-security-lab --field-selector reason=Failed \
  --sort-by=.lastTimestamp | head -5
# Expected: "registries ... not allowed" message for blocked images
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Image registry restrictions | No built-in mechanism; requires admission webhooks or third-party tools | `Image` config resource with `allowedRegistries` / `blockedRegistries` built in |
| Image signing | Manual setup with Cosign/Notary + external webhook | Native GPG signature verification via Machine Config and `policy.json` |
| Vulnerability scanning | External tools (Trivy, Anchore, Snyk) in CI pipelines | Quay + Clair integrated scanning; Container Security Operator for in-cluster visibility |
| Base images | No preference; any image from any source | UBI images: free, certified, non-root, SCC-compatible, rebuilt with CVE fixes |
| Image digest enforcement | Requires admission webhook to rewrite tags to digests | Built-in `resolveImages` option in ImagePolicy admission |
| Security visibility | kubectl + external dashboards | Web Console shows vulnerability data, image policy status, and events natively |
| Tag-to-digest resolution | Not available natively | ImageStream tag-to-digest resolution prevents tag mutation attacks |
| Certified image catalog | No equivalent | Red Hat Ecosystem Catalog with health index, CVE data, and certification status |

## Key Takeaways

- **OpenShift provides cluster-wide image policies** through the `Image` config resource, letting administrators restrict which registries are allowed without writing custom admission webhooks.
- **UBI (Universal Base Images)** are the recommended base for OpenShift workloads because they are free, pre-scanned, non-root by default, and compatible with the `restricted` SCC.
- **Image signature verification** can be enforced at the node level using MachineConfig to set container `policy.json`, ensuring only cryptographically signed images from trusted publishers run on the cluster.
- **Quay + Clair** provide integrated security scanning for container images, and the Container Security Operator surfaces vulnerability data directly in the OpenShift Web Console.
- **These features work together as a defense-in-depth strategy**: restrict registries, require signatures, scan for vulnerabilities, and use certified base images.

## Cleanup

```bash
# Switch to developer user
oc login -u developer -p developer https://api.crc.testing:6443

# Delete the project and all resources
oc delete project image-security-lab

# If you applied the cluster-wide image policy, revert it (cluster-admin required):
oc login -u kubeadmin https://api.crc.testing:6443

# Remove registry restrictions (allow all registries again)
oc patch image.config.openshift.io/cluster --type=json \
  -p='[{"op": "remove", "path": "/spec/registrySources"}]'

# If you applied the MachineConfig, remove it:
oc delete machineconfig 50-image-signature-policy 2>/dev/null

# If you applied the ImageTagMirrorSet, remove it:
oc delete imagetagmirrorset docker-hub-mirror 2>/dev/null

# Switch back to developer
oc login -u developer -p developer https://api.crc.testing:6443
```

## Next Steps

In **L2-M5.2 — Pod Security & Admission**, you will dive deeper into pod-level security controls. Building on the SCCs you learned in L1-M2.4, you will explore Kubernetes Pod Security Admission (PSA) and how it coexists with OpenShift SCCs, and look at policy engines like OPA Gatekeeper and Kyverno for fine-grained admission control.
