# L1-M3.3 — ImageStreams & Image Management

**Level:** Foundations
**Duration:** 30 min

## Overview

In Kubernetes you reference container images by their full registry path and tag — and the cluster has no awareness of whether that image has changed, where it came from, or how it relates to your deployments. OpenShift introduces **ImageStreams**, a layer of abstraction that decouples your workloads from raw image references. In this lesson you will learn what ImageStreams are, why OpenShift uses them, and how they unlock features like image change triggers, scheduled imports, and simple rollbacks.

## Prerequisites

- Completed: L1-M3.2 (BuildConfigs & Build Strategies)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`

## K8s Context

In vanilla Kubernetes, a Deployment references an image directly:

```yaml
containers:
  - name: my-app
    image: docker.io/library/nginx:1.25
```

There is no cluster-level object that tracks that image. If the upstream tag is overwritten with a new digest, Kubernetes does not notice unless you explicitly re-pull (via `imagePullPolicy: Always` and a pod restart). There is no built-in mechanism to trigger a redeployment when an image changes, track the history of image tags, or centrally manage where images come from.

You handle all of this yourself — typically through CI/CD pipelines, admission webhooks, or external tooling.

## Concepts

### What Is an ImageStream?

An **ImageStream** is an OpenShift API object (`image.openshift.io/v1`) that acts as a virtual pointer to one or more container images. It does not store the image layers — it stores **metadata** (tag name, image digest, source registry, creation timestamp) that references images in an external or internal registry.

Think of it like a DNS CNAME record for container images: your Deployment points to the ImageStream tag, and the ImageStream tag points to the actual image in a registry.

### What Is an ImageStreamTag?

Each tag within an ImageStream (e.g., `my-app:latest`, `my-app:v1.2`) is an **ImageStreamTag** — a named pointer to a specific image digest. When the underlying image changes, the tag can be updated to the new digest while keeping the same tag name.

### Why Does OpenShift Use This Abstraction?

1. **Decoupling** — Workloads reference an ImageStream tag instead of a registry URL. If you move images between registries (dev to prod, Docker Hub to Quay), you update the ImageStream — not every Deployment manifest.

2. **Image change triggers** — OpenShift can automatically redeploy your application when an ImageStream tag is updated. No need for external CI hooks or manual rollouts.

3. **Rollback** — ImageStreams keep a history of which digest each tag pointed to. Rolling back is as simple as reverting the tag pointer.

4. **Scheduled imports** — OpenShift can periodically poll an external registry for changes and update the ImageStream automatically.

5. **Security and governance** — Cluster admins can control which external images are imported and used via ImageStream policies.

### Internal Registry

OpenShift ships with an integrated container registry. When you build images with `oc start-build`, the resulting image is pushed to this internal registry and tracked via an ImageStream automatically. The internal registry URL follows the pattern `image-registry.openshift-image-registry.svc:5000/<project>/<imagestream>`.

## Step-by-Step

### Step 1: Create a Project

Create a dedicated project for this lesson:

```bash
oc new-project imagestream-demo
```

Expected output:

```
Now using project "imagestream-demo" on server "https://api.crc.testing:6443".
```

### Step 2: Create a Basic ImageStream

Create an empty ImageStream that we will populate with tags:

```bash
oc apply -f manifests/imagestream.yaml
```

Verify it was created:

```bash
oc get imagestream
```

Expected output:

```
NAME       IMAGE REPOSITORY                                                           TAGS   UPDATED
my-nginx
```

The ImageStream exists but has no tags yet — the `TAGS` column is empty.

### Step 3: Import an External Image into the ImageStream

Use `oc import-image` to pull metadata from an external registry into your ImageStream. This does not copy the image layers — it creates a reference:

```bash
oc import-image my-nginx:1.25 --from=docker.io/library/nginx:1.25 --confirm
```

Expected output (abbreviated):

```
imagestream.image.openshift.io/my-nginx imported

Name:                   my-nginx
Namespace:              imagestream-demo
...
Tags:                   1.25

1.25
  tagged from docker.io/library/nginx:1.25
    * docker.io/library/nginx@sha256:...
```

Now check the ImageStream tags:

```bash
oc get imagestream my-nginx
```

Expected output:

```
NAME       IMAGE REPOSITORY                                                                  TAGS   UPDATED
my-nginx   default-route-openshift-image-registry.apps-crc.testing/imagestream-demo/my-nginx   1.25   5 seconds ago
```

### Step 4: Import a Second Tag

Import a different version of nginx to demonstrate multi-tag support:

```bash
oc import-image my-nginx:1.24 --from=docker.io/library/nginx:1.24 --confirm
```

List all tags on the ImageStream:

```bash
oc get imagestreamtag -l app=my-nginx
```

You can also describe the ImageStream for a full view:

```bash
oc describe imagestream my-nginx
```

Expected output (abbreviated):

```
Name:         my-nginx
Namespace:    imagestream-demo
...
Tags:
  1.24
    tagged from docker.io/library/nginx:1.24
    * docker.io/library/nginx@sha256:...

  1.25
    tagged from docker.io/library/nginx:1.25
    * docker.io/library/nginx@sha256:...
```

Each tag tracks the exact digest, so you know precisely which image bytes are referenced.

### Step 5: Deploy Using the ImageStream Reference

Now deploy an application that references the ImageStream instead of a raw registry path. Apply the Deployment manifest:

```bash
oc apply -f manifests/deployment.yaml
```

This Deployment uses the annotation `image.openshift.io/triggers` to link it to the ImageStream. When the ImageStream tag updates, OpenShift will automatically roll out a new version.

Verify the Deployment is running:

```bash
oc get deployment nginx-app
oc get pods
```

Expected output:

```
NAME        READY   UP-TO-DATE   AVAILABLE   AGE
nginx-app   1/1     1            1           15s

NAME                         READY   STATUS    RESTARTS   AGE
nginx-app-5d4f7b8c9-x2kl4   1/1     Running   0          15s
```

### Step 6: Set Up Scheduled Import

Configure the ImageStream to periodically check the external registry for updates. This is useful for base images that receive security patches:

```bash
oc tag docker.io/library/nginx:1.25 my-nginx:1.25 --scheduled
```

Verify the scheduled import is configured:

```bash
oc describe imagestream my-nginx | grep -A 2 "1.25"
```

Expected output:

```
  1.25
    tagged from docker.io/library/nginx:1.25
      prefer registry pullthrough when referencing this tag
      updates automatically from registry
```

The "updates automatically from registry" line confirms scheduled imports are active. By default, OpenShift checks every 15 minutes.

### Step 7: Demonstrate Image Change Trigger

Simulate what happens when an upstream image changes by re-tagging the ImageStream to a different digest. Tag the `1.24` image as `1.25` to simulate an update:

```bash
oc tag my-nginx:1.24 my-nginx:latest
```

If you applied the Deployment with the trigger annotation (Step 5), OpenShift notices the tag change and starts a new rollout:

```bash
oc rollout status deployment/nginx-app
```

Check the rollout history:

```bash
oc rollout history deployment/nginx-app
```

### Step 8: Explore ImageStream History and Rollback

Each ImageStreamTag keeps a history of the digests it has pointed to. View the history:

```bash
oc describe imagestreamtag my-nginx:1.25
```

To revert a tag to a previous image, use `oc tag` with the specific digest or a previously known tag:

```bash
oc tag my-nginx:1.25 my-nginx:latest
```

This updates the `latest` tag back to the 1.25 image, and the trigger fires another rollout — effectively a rollback.

### Step 9: Explore ImageStreams in the Web Console

1. Open the OpenShift Web Console (https://console-openshift-console.apps-crc.testing).
2. Switch to the **Developer** perspective.
3. Select the **imagestream-demo** project.
4. Navigate to **Builds > ImageStreams** (or use the Administrator perspective under **Builds > ImageStreams**).
5. Click on **my-nginx** to see all tags, their digests, and import history.

The console provides a visual timeline of tag changes, making it easy to audit image provenance.

## Verification

Run the following commands to verify the lesson was completed successfully:

```bash
# ImageStream exists with multiple tags
oc get imagestream my-nginx -o jsonpath='{.status.tags[*].tag}'
# Expected: 1.24 1.25 latest

# Deployment is running and using the ImageStream
oc get deployment nginx-app -o jsonpath='{.metadata.annotations.image\.openshift\.io/triggers}'
# Expected: JSON array referencing the ImageStream

# Pods are running
oc get pods -l app=nginx-app --field-selector=status.phase=Running
# Expected: at least 1 pod in Running state
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Image reference | Direct registry URL in pod spec (`docker.io/nginx:1.25`) | ImageStream tag (`my-nginx:1.25`) that points to a registry URL |
| Image change detection | None built-in; requires external tooling or `imagePullPolicy: Always` + pod restart | ImageStream detects tag changes and triggers rollouts automatically |
| Image history | None; tag is overwritten silently | ImageStream keeps digest history per tag |
| Scheduled updates | Not supported | `--scheduled` flag polls the registry periodically (default: 15 min) |
| Image rollback | Manually update the image field and redeploy | Retag the ImageStreamTag; trigger fires automatically |
| Registry abstraction | None; changing registries means updating every manifest | Update the ImageStream; workloads reference the tag, not the registry |
| Internal registry | Not included (install separately) | Built-in, integrated with ImageStreams and builds |
| Image metadata | `kubectl describe pod` shows the image | `oc describe imagestreamtag` shows full provenance, digest, and history |

## Key Takeaways

- **ImageStreams decouple workloads from registries** — your Deployments reference a stable ImageStream tag, not a raw registry URL. This makes it simple to switch registries or promote images between environments.
- **Image change triggers enable automated rollouts** — when an ImageStream tag is updated (by a build, an import, or a manual retag), OpenShift can automatically redeploy your application without external CI/CD intervention.
- **ImageStreams track history** — every tag records which image digest it has pointed to over time, enabling auditing and simple rollbacks.
- **Scheduled imports keep base images current** — OpenShift can poll external registries for updates, ensuring your applications pick up security patches to base images automatically.
- **This is the biggest conceptual leap from Kubernetes** — ImageStreams have no K8s equivalent. They are central to how OpenShift manages builds, deployments, and image lifecycle.

## Cleanup

Remove all resources created in this lesson:

```bash
# Delete the deployment
oc delete deployment nginx-app

# Delete the ImageStream
oc delete imagestream my-nginx

# Delete the project
oc delete project imagestream-demo
```

## Next Steps

In the next lesson, **L1-M3.4 — Deployment Strategies**, you will explore how to configure rolling updates, recreate strategies, rollbacks, and rollout controls using standard Kubernetes Deployments on OpenShift.
