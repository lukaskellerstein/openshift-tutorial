# L1-M3.2 — BuildConfigs & Build Strategies

**Level:** Foundations
**Duration:** 40 min

## Overview

In Kubernetes, building container images is an external concern -- you use Docker, Podman, Kaniko, or a CI system and then push to a registry. OpenShift has a built-in build system controlled by a resource called `BuildConfig`. In this lesson you will learn the three main build strategies (Docker/Containerfile, Source-to-Image, and Pipeline), how triggers automate builds, and how to manage builds from the CLI.

## Prerequisites

- Completed: L1-M3.1 (`oc new-app` & Source-to-Image)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`

## K8s Context

In vanilla Kubernetes, there is no built-in mechanism for building container images. The typical workflow is:

1. Write a Dockerfile.
2. Build the image locally with `docker build` or `podman build`.
3. Push it to an external registry (Docker Hub, ECR, GCR, Quay, etc.).
4. Reference the registry image in your Deployment manifest.

This works, but it means every team must set up its own CI/CD pipeline for builds, manage registry credentials, and handle image promotion between environments. There is no standard Kubernetes API for "build this source code into a container image."

## Concepts

### What is a BuildConfig?

A `BuildConfig` is an OpenShift-specific resource (`build.openshift.io/v1`) that defines **how** to build a container image and **when** to trigger that build. Think of it as a build job definition that lives in the cluster. Each time a BuildConfig is triggered, it creates a `Build` object -- a single, immutable run of that build job.

### Build Strategies

OpenShift supports three build strategies:

**1. Docker (Containerfile) Strategy**

The cluster clones your Git repository, finds the `Dockerfile` (or `Containerfile`), and runs a container build inside a build pod. This is the closest to what you already do in Kubernetes -- except it happens inside the cluster, not on your laptop or in an external CI system.

**2. Source-to-Image (S2I) Strategy**

S2I is OpenShift's most distinctive build feature. You point it at source code (a Git repo), select a **builder image** (e.g., `python:3.11-ubi9`, `httpd:2.4-el9`, `nodejs:18-ubi9`), and OpenShift assembles the image automatically -- no Dockerfile required. The builder image contains scripts (`assemble`, `run`) that know how to install dependencies and start the application.

This is powerful for standardization: platform teams can provide approved builder images, and developers just push code.

### Build Triggers

Triggers automate build execution. A BuildConfig can have multiple triggers:

| Trigger | What it does |
|---------|-------------|
| **ConfigChange** | Starts a build whenever the BuildConfig resource itself is created or modified. |
| **ImageChange** | Starts a build when the base/builder image is updated (e.g., a security patch to `python:3.11-ubi9`). |
| **Webhook (GitHub)** | Starts a build when a GitHub webhook fires (push event). |
| **Webhook (Generic)** | Starts a build from any system that can POST to a URL. |

### Build Output

A build produces a container image. The `output` section of a BuildConfig specifies where to push the built image -- typically an `ImageStreamTag` in the internal registry. ImageStreams are covered in the next lesson (L1-M3.3).

## Step-by-Step

### Step 1: Create a project for build experiments

Create a dedicated project so all build resources are easy to find and clean up.

```bash
oc new-project build-strategies
```

Expected output:
```
Now using project "build-strategies" on server "https://api.crc.testing:6443".
```

### Step 2: Create the ImageStream for build output

Before creating BuildConfigs, create an ImageStream to receive the built images. The ImageStream acts as a pointer to images in the internal registry.

```bash
oc apply -f manifests/imagestream.yaml
```

```yaml
# manifests/imagestream.yaml
apiVersion: image.openshift.io/v1
kind: ImageStream
metadata:
  name: sample-app
  labels:
    app: sample-app
    tutorial-level: "1"
    tutorial-module: "M3"
```

Expected output:
```
imagestream.image.openshift.io/sample-app created
```

### Step 3: Create a Docker strategy BuildConfig

This BuildConfig clones the `httpd-ex` sample repository and builds the image using the Dockerfile in the repo.

```bash
oc apply -f manifests/buildconfig-docker.yaml
```

```yaml
# manifests/buildconfig-docker.yaml
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: sample-app-docker
  labels:
    app: sample-app
    build-strategy: docker
    tutorial-level: "1"
    tutorial-module: "M3"
spec:
  source:
    type: Git
    git:
      uri: https://github.com/sclorg/httpd-ex.git
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: Dockerfile
  output:
    to:
      kind: ImageStreamTag
      name: sample-app:docker
  triggers:
    - type: ConfigChange
    - type: ImageChange
```

Because we set a `ConfigChange` trigger, creating this BuildConfig automatically starts a build. Verify it:

```bash
oc get builds
```

Expected output:
```
NAME                   TYPE     FROM          STATUS    STARTED          DURATION
sample-app-docker-1    Docker   Git@<sha>     Running   10 seconds ago
```

### Step 4: Watch the Docker build logs

Follow the build logs in real time to see the Dockerfile steps execute inside the build pod:

```bash
oc logs -f build/sample-app-docker-1
```

You will see output similar to a local `docker build` -- pulling the base image, running each Dockerfile instruction, and finally pushing the image to the internal registry.

Wait for the build to complete. The final lines will look like:

```
Successfully pushed image-registry.openshift-image-registry.svc:5000/build-strategies/sample-app@sha256:...
Push successful
```

Verify the build completed:

```bash
oc get builds
```

Expected output:
```
NAME                   TYPE     FROM          STATUS      STARTED          DURATION
sample-app-docker-1    Docker   Git@abc1234   Complete    2 minutes ago    1m30s
```

### Step 5: Create an S2I BuildConfig

Now create a BuildConfig that uses the Source-to-Image strategy. Notice the key difference: instead of pointing to a Dockerfile, we specify a **builder image** (`httpd:2.4-el9` from the `openshift` namespace).

```bash
oc apply -f manifests/buildconfig-s2i.yaml
```

```yaml
# manifests/buildconfig-s2i.yaml
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: sample-app-s2i
  labels:
    app: sample-app
    build-strategy: s2i
    tutorial-level: "1"
    tutorial-module: "M3"
spec:
  source:
    type: Git
    git:
      uri: https://github.com/sclorg/httpd-ex.git
  strategy:
    type: Source
    sourceStrategy:
      from:
        kind: ImageStreamTag
        namespace: openshift
        name: httpd:2.4-el9
  output:
    to:
      kind: ImageStreamTag
      name: sample-app:s2i
  triggers:
    - type: ConfigChange
    - type: ImageChange
```

The S2I build will automatically start. Watch the logs:

```bash
oc logs -f build/sample-app-s2i-1
```

Notice the S2I-specific steps in the output: the builder image's `assemble` script runs, copying source files into the correct location and preparing the runtime. There is no Dockerfile involved.

### Step 6: Compare the two builds

Once both builds complete, list all builds to see them side by side:

```bash
oc get builds
```

Expected output:
```
NAME                   TYPE      FROM          STATUS     STARTED          DURATION
sample-app-docker-1    Docker    Git@abc1234   Complete   5 minutes ago    1m30s
sample-app-s2i-1       Source    Git@abc1234   Complete   2 minutes ago    1m15s
```

Check the ImageStream to see both tags:

```bash
oc get imagestream sample-app
```

Expected output:
```
NAME         IMAGE REPOSITORY                                                           TAGS          UPDATED
sample-app   default-route-openshift-image-registry.apps-crc.testing/build-strategies/sample-app   docker,s2i    30 seconds ago
```

### Step 7: Try S2I with a different language (Python)

To demonstrate that S2I works across languages, create a BuildConfig for a Python application. The same pattern applies -- change the builder image, point to a Python repo, and S2I handles the rest.

First, create the ImageStream for the Python app:

```bash
oc apply -f manifests/imagestream-python.yaml
```

Then create the BuildConfig:

```bash
oc apply -f manifests/buildconfig-s2i-python.yaml
```

```yaml
# manifests/buildconfig-s2i-python.yaml (key sections)
spec:
  source:
    type: Git
    git:
      uri: https://github.com/sclorg/django-ex.git
  strategy:
    type: Source
    sourceStrategy:
      from:
        kind: ImageStreamTag
        namespace: openshift
        name: python:3.11-ubi9
```

Watch the build:

```bash
oc logs -f build/python-app-s2i-1
```

You will see the Python builder image install dependencies from `requirements.txt` and set up the Django application -- all without writing a single line of Dockerfile.

### Step 8: Manually trigger a build with oc start-build

Builds do not always have to be triggered automatically. You can start a build manually:

```bash
oc start-build sample-app-docker
```

Expected output:
```
build.build.openshift.io/sample-app-docker-2 started
```

Notice the build number incremented to `-2`. Each `oc start-build` creates a new Build object. Check the history:

```bash
oc get builds -l build-strategy=docker
```

Expected output:
```
NAME                   TYPE     FROM          STATUS     STARTED          DURATION
sample-app-docker-1    Docker   Git@abc1234   Complete   8 minutes ago    1m30s
sample-app-docker-2    Docker   Git@abc1234   Running    5 seconds ago
```

You can also start a build and follow the logs in one command:

```bash
oc start-build sample-app-s2i --follow
```

### Step 9: Explore BuildConfig details and webhook triggers

Inspect the BuildConfig to see its full configuration:

```bash
oc describe bc/sample-app-docker
```

Key sections in the output:
- **Strategy**: shows the build type and settings
- **Triggered by**: lists what caused each build
- **Builds**: history of all builds from this config

Now create a BuildConfig with explicit webhook triggers:

```bash
oc apply -f manifests/buildconfig-webhook-example.yaml
```

```yaml
# manifests/buildconfig-webhook-example.yaml (trigger section)
spec:
  triggers:
    - type: GitHub
      github:
        secret: my-github-webhook-secret
    - type: Generic
      generic:
        secret: my-generic-webhook-secret
    - type: ConfigChange
    - type: ImageChange
```

Retrieve the webhook URLs:

```bash
oc describe bc/sample-app-webhook | grep -A 1 "Webhook"
```

Expected output:
```
Webhook GitHub:
	URL:	https://api.crc.testing:6443/apis/build.openshift.io/v1/namespaces/build-strategies/buildconfigs/sample-app-webhook/webhooks/<secret>/github
Webhook Generic:
	URL:	https://api.crc.testing:6443/apis/build.openshift.io/v1/namespaces/build-strategies/buildconfigs/sample-app-webhook/webhooks/<secret>/generic
```

You would add these URLs to your GitHub repository settings (Settings > Webhooks) to trigger builds on every push. For testing, you can trigger the generic webhook manually:

```bash
# Trigger a build via the generic webhook
curl -X POST -k \
  https://api.crc.testing:6443/apis/build.openshift.io/v1/namespaces/build-strategies/buildconfigs/sample-app-webhook/webhooks/my-generic-webhook-secret/generic
```

### Step 10: List available builder images

OpenShift ships with many builder images in the `openshift` namespace. To see what S2I builders are available:

```bash
oc get imagestreams -n openshift | grep -E 'NAME|python|nodejs|httpd|nginx|php|ruby|perl|dotnet|golang|java'
```

Expected output:
```
NAME                    IMAGE REPOSITORY   TAGS                          UPDATED
dotnet                  ...                6.0-ubi8,7.0-ubi8,...         ...
golang                  ...                1.20-ubi9,1.21-ubi9,...       ...
httpd                   ...                2.4-el9,2.4-ubi8,...          ...
java                    ...                11-ubi8,17-ubi8,...           ...
nginx                   ...                1.22-ubi9,1.24-ubi9,...       ...
nodejs                  ...                18-ubi9,20-ubi9,...           ...
php                     ...                8.1-ubi9,8.2-ubi9,...         ...
python                  ...                3.9-ubi9,3.11-ubi9,...        ...
ruby                    ...                3.1-ubi9,3.2-ubi9,...         ...
```

Each of these can be used as a `sourceStrategy.from` reference in an S2I BuildConfig.

## Verification

Confirm that all builds completed successfully:

```bash
# List all builds -- all should show "Complete"
oc get builds

# Verify ImageStreams have the expected tags
oc get imagestreams

# Check the details of a specific build
oc describe build/sample-app-docker-1 | grep -E "Status:|Duration:|Push"

# Verify the webhook BuildConfig has the correct triggers
oc describe bc/sample-app-webhook | grep "Triggered by"
```

In the **Web Console**, navigate to **Builds > BuildConfigs** in the Developer perspective. You should see all three BuildConfigs. Click on any one to see its build history, logs, and trigger configuration.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Building images | External (Docker, Podman, Kaniko, CI/CD) | Built-in BuildConfig resource |
| Dockerfile builds | Done locally or in CI pipelines | Docker strategy runs in-cluster |
| Building without Dockerfile | Not natively supported | S2I builds from source code only |
| Build triggers | CI/CD webhooks (external) | Native webhook, image change, config change triggers |
| Build history | Tracked by external CI system | Build objects stored in the cluster with `oc get builds` |
| Build logs | Stored in external CI system | `oc logs build/<name>` from the cluster |
| Builder image catalog | No equivalent | Pre-installed builder ImageStreams in `openshift` namespace |
| Build API | No standard API | `build.openshift.io/v1` API group |

## Key Takeaways

- A **BuildConfig** defines how to build a container image and when to trigger the build. Each execution creates a **Build** object.
- The **Docker strategy** builds from a Dockerfile/Containerfile inside the cluster -- similar to what you do externally in Kubernetes, but managed by OpenShift.
- **S2I (Source-to-Image)** is OpenShift's signature build feature: it builds images from source code using a builder image, with no Dockerfile required. This enables standardization across teams.
- **Triggers** (ConfigChange, ImageChange, Webhook) automate builds so images stay current when code changes, base images are patched, or configuration is updated.
- Use `oc start-build` to manually trigger builds and `oc logs build/<name>` to view build output.

## Cleanup

```bash
# Delete all resources created in this lesson
oc delete project build-strategies
```

This deletes the project and all resources within it (BuildConfigs, Builds, ImageStreams). If you want to delete resources selectively instead:

```bash
# Delete by tutorial labels
oc delete buildconfig,imagestream,build -l tutorial-level=1,tutorial-module=M3

# Or delete individually
oc delete bc/sample-app-docker bc/sample-app-s2i bc/sample-app-webhook bc/python-app-s2i
oc delete is/sample-app is/python-app
```

## Next Steps

In **L1-M3.3 -- ImageStreams & Image Management**, you will learn how ImageStreams work in depth: why OpenShift uses this abstraction instead of direct image references, how tags and scheduled imports work, and how image change triggers connect to the BuildConfig triggers you learned here.
