# L1-M3.1 — oc new-app & Source-to-Image (S2I)

**Level:** Foundations
**Duration:** 40 min

## Overview

In Kubernetes, deploying an application means manually writing Deployment, Service, and Ingress manifests (or using Helm). OpenShift provides `oc new-app`, a single command that inspects a source repository, Docker image, or template and automatically creates everything needed to build, deploy, and expose your application. This lesson teaches you how to deploy applications using `oc new-app` and introduces Source-to-Image (S2I) -- OpenShift's built-in mechanism for building container images directly from source code without writing a Dockerfile.

## Prerequisites

- Completed: L1-M2.1 (Projects vs Namespaces)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`
- A project created for this lesson (we will create one in Step 1)

## K8s Context

In vanilla Kubernetes, deploying an application from source code requires multiple steps:

1. Write a `Dockerfile`
2. Build the image with `docker build` (or `podman build`)
3. Push the image to a container registry
4. Write a `Deployment` manifest referencing that image
5. Write a `Service` manifest to expose it internally
6. Optionally write an `Ingress` to expose it externally

Each step is a separate tool, a separate command, and a separate thing that can break. You need a registry account, a CI system, and several YAML files before your app can run. Kubernetes does not have any opinion about how you get from source code to a running pod -- that is entirely your responsibility.

## Concepts

### oc new-app -- One Command to Deploy

`oc new-app` is OpenShift's opinionated application deployment command. You give it a source (Git repo, Docker image, or template) and it figures out the rest. Depending on the input, it automatically creates some or all of:

| Resource | Purpose |
|----------|---------|
| **BuildConfig** | Defines how to build the container image from source |
| **ImageStream** | Tracks the built image (an abstraction over image references) |
| **Deployment** | Manages the pod replicas running the application |
| **Service** | Provides internal cluster networking to the pods |

Note that `oc new-app` does **not** create a Route by default -- you need to expose the service separately with `oc expose`. This is intentional: not every service should be publicly accessible.

### Source-to-Image (S2I)

S2I is OpenShift's built-in build strategy that takes your application source code and produces a runnable container image -- all without you writing a Dockerfile. Here is how it works:

1. **Builder image**: OpenShift provides curated builder images for common languages (Python, Node.js, Java, Ruby, Go, PHP, .NET). These images know how to install dependencies and start the application for their respective language.
2. **Assemble phase**: S2I injects your source code into the builder image and runs an `assemble` script that installs dependencies (e.g., `pip install` for Python, `npm install` for Node.js).
3. **Run phase**: The resulting image uses a `run` script that starts your application (e.g., `python app.py`, `npm start`).

**Why does OpenShift have S2I?**

- **Security**: Developers do not need access to `docker build` or root-level container tooling. The build runs inside the cluster under controlled SCCs.
- **Consistency**: Every Python app is built the same way, with the same base image, patched by Red Hat. No more "works on my machine" Dockerfiles.
- **Speed**: Developers push code, OpenShift handles the rest. The inner loop is: `git push` -> build triggers -> new image -> automatic redeployment.

### Builder Images

OpenShift ships with builder images in the `openshift` namespace. You can list them:

```bash
oc get imagestreams -n openshift | grep -E 'python|nodejs|java|ruby|golang|php|dotnet'
```

Common builder images include:

| Builder | Image Stream | Languages/Frameworks |
|---------|-------------|---------------------|
| Python | `python:3.11-ubi9` | Flask, Django, FastAPI |
| Node.js | `nodejs:18-ubi9` | Express, Next.js, NestJS |
| Java | `java:openjdk-17-ubi8` | Spring Boot, Quarkus |
| Go | `golang:1.21-ubi9` | Standard Go applications |
| Ruby | `ruby:3.1-ubi9` | Rails, Sinatra |
| PHP | `php:8.1-ubi9` | Laravel, Symfony |

The `-ubi9` suffix means the image is based on Red Hat's Universal Base Image 9, which is security-hardened and freely redistributable.

### The Three Modes of oc new-app

`oc new-app` detects what you give it and acts accordingly:

1. **From a Git repository**: Detects the language, picks a builder image, creates a BuildConfig + ImageStream + Deployment + Service.
2. **From a Docker image**: Pulls the image, creates a Deployment + Service (no build needed).
3. **From a template**: Processes the template parameters, creates all resources defined in the template.

## Step-by-Step

### Step 1: Create a Project for This Lesson

Create a dedicated project so all resources are easy to find and clean up:

```bash
oc new-project l1-m3-s2i --display-name="L1-M3: S2I Demo"
```

Expected output:
```
Now using project "l1-m3-s2i" on server "https://api.crc.testing:6443".
```

### Step 2: Deploy from a Docker Image (the Simplest Case)

Before diving into S2I, start with the simplest `oc new-app` usage -- deploying an existing container image. This is analogous to writing a Kubernetes Deployment + Service, but in one command:

```bash
oc new-app --name=nginx-demo --image=bitnami/nginx:latest
```

> **Why Bitnami?** The standard `nginx` image from Docker Hub runs as root, which OpenShift blocks by default (SCC `restricted`). Bitnami's image runs as a non-root user and works out of the box on OpenShift.

Expected output (abbreviated):
```
--> Found container image ... (Bitnami) for "bitnami/nginx:latest"
...
--> Creating resources ...
    deployment.apps "nginx-demo" created
    service "nginx-demo" created
--> Success
    Application is not exposed. You can expose services to the outside world by executing one or more of the commands:
      'oc expose service/nginx-demo'
    Run 'oc status' to view your app.
```

Notice: OpenShift created a **Deployment** and a **Service** -- but no BuildConfig or ImageStream, because no build is needed.

Verify the resources:

```bash
oc get all -l app=nginx-demo
```

Expected output:
```
NAME                              READY   STATUS    RESTARTS   AGE
pod/nginx-demo-6f8b9c4d7f-kx2m4  1/1     Running   0          30s

NAME                 TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)    AGE
service/nginx-demo   ClusterIP   172.30.45.12   <none>        8080/TCP   30s

NAME                         READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/nginx-demo   1/1     1            1           30s
```

Now expose it with a Route so you can access it from your browser:

```bash
oc expose service/nginx-demo
```

```bash
oc get route nginx-demo
```

Expected output:
```
NAME         HOST/PORT                                PATH   SERVICES     PORT   TERMINATION   WILDCARD
nginx-demo   nginx-demo-l1-m3-s2i.apps-crc.testing          nginx-demo   8080                 None
```

Test it:

```bash
curl -s http://nginx-demo-l1-m3-s2i.apps-crc.testing | head -5
```

### Step 3: Deploy a Python App Using S2I (from a Git Repository)

Now for the main event -- deploying an application directly from source code using S2I. We will use the `sclorg/django-ex` sample app (a simple Django application maintained by Red Hat's Software Collections):

```bash
oc new-app python:3.11-ubi9~https://github.com/sclorg/django-ex.git --name=django-app
```

Let's break down this command:

- `python:3.11-ubi9` -- the builder image (from the `openshift` namespace)
- `~` -- the S2I separator meaning "build this source with this builder"
- `https://github.com/sclorg/django-ex.git` -- the Git repository containing the source code
- `--name=django-app` -- the name for all created resources

Expected output:
```
--> Found image ... in image stream "openshift/python" under tag "3.11-ubi9" for "python:3.11-ubi9"
    ...
--> Creating resources ...
    imagestream.image.openshift.io "django-app" created
    buildconfig.build.openshift.io "django-app" created
    deployment.apps "django-app" created
    service "django-app" created
--> Success
    Build scheduled, use 'oc logs -f buildconfig/django-app' to track its progress.
    Application is not exposed. You can expose services to the outside world by executing one or more of the commands:
      'oc expose service/django-app'
    Run 'oc status' to view your app.
```

This time, OpenShift created **four** resources:

| Resource | What it does |
|----------|-------------|
| **ImageStream** `django-app` | Tracks the built image |
| **BuildConfig** `django-app` | Defines the S2I build (source repo + builder image) |
| **Deployment** `django-app` | Manages pods running the built image |
| **Service** `django-app` | Internal networking (ClusterIP) |

### Step 4: Watch the S2I Build

The build is running in a build pod. Watch it in real time:

```bash
oc logs -f buildconfig/django-app
```

You will see the S2I process in action:

```
Cloning "https://github.com/sclorg/django-ex.git" ...
...
---> Installing application source ...
---> Installing dependencies ...
Collecting django
  Downloading Django-4.2.7-py3-none-any.whl (8.0 MB)
...
Pushing image image-registry.openshift-image-registry.svc:5000/l1-m3-s2i/django-app:latest ...
...
Push successful
```

Check the build status:

```bash
oc get builds
```

Expected output:
```
NAME             TYPE     FROM          STATUS     STARTED          DURATION
django-app-1     Source   Git@abc1234   Complete   2 minutes ago    1m30s
```

The `TYPE` column shows `Source` -- this is an S2I build.

### Step 5: Expose and Test the Django App

Once the build completes and the pod is running:

```bash
oc expose service/django-app
```

```bash
oc get route django-app
```

Test the application:

```bash
curl -s http://django-app-l1-m3-s2i.apps-crc.testing | head -10
```

You should see the Django welcome page HTML.

### Step 6: Examine What oc new-app Created

Let's inspect every resource that was auto-generated. This is important -- understanding what `oc new-app` creates helps you debug issues later.

**List all resources with the app label:**

```bash
oc get all -l app=django-app
```

**Inspect the BuildConfig:**

```bash
oc get buildconfig django-app -o yaml
```

Key fields in the BuildConfig:

```yaml
spec:
  source:
    type: Git
    git:
      uri: https://github.com/sclorg/django-ex.git
  strategy:
    type: Source              # This is an S2I build
    sourceStrategy:
      from:
        kind: ImageStreamTag
        namespace: openshift
        name: python:3.11-ubi9   # The builder image
  output:
    to:
      kind: ImageStreamTag
      name: django-app:latest    # Where the built image goes
  triggers:                       # Auto-rebuild triggers
    - type: ConfigChange          # Rebuild if BuildConfig changes
    - type: ImageChange           # Rebuild if builder image updates
```

**Inspect the ImageStream:**

```bash
oc get imagestream django-app -o yaml
```

The ImageStream tracks the `django-app:latest` tag, which points to the image in the internal registry.

**Inspect the Deployment:**

```bash
oc get deployment django-app -o yaml
```

Notice that the Deployment references the ImageStream (not a direct image URL). This is how OpenShift enables automatic redeployments when a new image is built.

### Step 7: Deploy from a Git Repo with Auto-Detection

You do not always need to specify the builder image. If you omit it, `oc new-app` inspects the Git repository and detects the language automatically:

```bash
oc new-app https://github.com/sclorg/nodejs-ex.git --name=nodejs-app
```

OpenShift examines the repo, finds a `package.json`, and selects the Node.js builder image:

```
--> Found image ... in image stream "openshift/nodejs" under tag "18-ubi9" ...
...
--> Creating resources ...
    imagestream.image.openshift.io "nodejs-app" created
    buildconfig.build.openshift.io "nodejs-app" created
    deployment.apps "nodejs-app" created
    service "nodejs-app" created
--> Success
```

Language detection works by looking for signature files:

| File Found | Language Detected |
|-----------|-------------------|
| `requirements.txt`, `setup.py` | Python |
| `package.json` | Node.js |
| `pom.xml`, `build.gradle` | Java |
| `Gemfile` | Ruby |
| `go.mod` | Go |
| `composer.json` | PHP |

### Step 8: Deploy Using a Manifest (the Kubernetes-Compatible Way)

For comparison, here is how you would deploy the same nginx application using a standard Kubernetes-style manifest. Apply the manifests from this lesson's `manifests/` directory:

```bash
oc apply -f manifests/deployment.yaml
oc apply -f manifests/service.yaml
oc apply -f manifests/route.yaml
```

Or apply them all at once:

```bash
oc apply -f manifests/
```

This creates the same result as `oc new-app --image=bitnami/nginx`, but with explicit YAML files you can version-control and review. In production, you will typically use manifests (or Helm/Kustomize) rather than `oc new-app`.

### Step 9: Understand the Dry-Run Option

Before running `oc new-app`, you can preview what it will create without actually creating anything:

```bash
oc new-app python:3.11-ubi9~https://github.com/sclorg/django-ex.git \
  --name=django-dry-run \
  --dry-run \
  -o yaml
```

This outputs the full YAML for all resources that would be created. Redirect it to a file to get a starting point for your own manifests:

```bash
oc new-app python:3.11-ubi9~https://github.com/sclorg/django-ex.git \
  --name=django-dry-run \
  --dry-run \
  -o yaml > my-app.yaml
```

This is extremely useful: use `oc new-app --dry-run -o yaml` to generate manifests, then customize them for production use.

## Verification

Confirm everything is running correctly:

```bash
# 1. Check that all pods are running
oc get pods
```

Expected output (your pod names will differ):
```
NAME                           READY   STATUS      RESTARTS   AGE
django-app-1-build             0/1     Completed   0          5m
django-app-5d8b9f7c6-abc12     1/1     Running     0          3m
nginx-demo-6f8b9c4d7f-xyz34    1/1     Running     0          8m
nginx-manifest-7a4c3e2d1-qw56  1/1     Running     0          1m
nodejs-app-1-build             0/1     Completed   0          4m
nodejs-app-6c9d8e7f5-def78     1/1     Running     0          2m
```

```bash
# 2. Check all routes
oc get routes
```

```bash
# 3. Check the S2I builds completed
oc get builds
```

```bash
# 4. Check ImageStreams
oc get imagestreams
```

```bash
# 5. Verify the Django app responds
curl -s -o /dev/null -w "%{http_code}" http://django-app-l1-m3-s2i.apps-crc.testing
```

Expected output: `200`

```bash
# 6. View overall app status
oc status
```

The `oc status` command gives you a high-level overview of all resources and their relationships in the current project.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Deploy from image | Write Deployment + Service YAML | `oc new-app --image=<image>` |
| Deploy from source | Write Dockerfile, build externally, push to registry, write YAML | `oc new-app <builder>~<git-repo>` (S2I) |
| Build system | None built-in (use external CI) | BuildConfig + S2I (built-in) |
| Image tracking | Direct image reference in Deployment | ImageStream (abstraction with triggers) |
| Language detection | N/A | Auto-detects from repo contents |
| Expose externally | Ingress + Ingress Controller | `oc expose service` (Route, built-in) |
| Dockerfile required? | Yes, always for source builds | No, S2I uses builder images |
| Auto-rebuild on source change | Must configure CI webhook | BuildConfig triggers (webhook, image change) |

## Key Takeaways

- **`oc new-app` is a shortcut, not magic**: It creates standard resources (Deployment, Service, BuildConfig, ImageStream) that you can inspect, modify, and manage individually. Use `--dry-run -o yaml` to see exactly what it will create.
- **S2I eliminates the Dockerfile**: You provide source code, OpenShift provides the builder image, and S2I assembles a runnable container image. This enforces consistent, secure base images across your organization.
- **Builder images are curated and secure**: Red Hat maintains UBI-based builder images for major languages. They are patched regularly, run as non-root, and are designed to work within OpenShift's security constraints.
- **`oc new-app` does not create Routes**: You must explicitly run `oc expose service/<name>` to make an app accessible outside the cluster. This is a deliberate security-first design.
- **For production, use manifests**: `oc new-app` is great for getting started and prototyping. For production deployments, generate manifests with `--dry-run -o yaml` and manage them in Git.

## Cleanup

Remove all resources created in this lesson:

```bash
# Delete the entire project (removes all resources within it)
oc delete project l1-m3-s2i
```

If you prefer to keep the project and delete resources selectively:

```bash
# Delete the nginx demo
oc delete all -l app=nginx-demo

# Delete the Django S2I app
oc delete all -l app=django-app

# Delete the Node.js S2I app
oc delete all -l app=nodejs-app

# Delete the manifest-deployed nginx
oc delete all -l app=nginx-manifest
```

## Next Steps

In **L1-M3.2 -- BuildConfigs & Build Strategies**, you will dive deeper into the build system that S2I introduced here. You will learn about the different build strategies (Docker, Source, Pipeline, Custom), how to configure build triggers (webhooks, image change, config change), and how to manually trigger and manage builds with `oc start-build`.
