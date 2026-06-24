# L2-M6.2 — odo — Developer CLI

**Level:** Practitioner
**Duration:** 30 min

## Overview

If `oc` is the Swiss Army knife for cluster operators and developers alike, `odo` is the scalpel built exclusively for developers. While `oc` maps closely to Kubernetes resource primitives (Deployments, Services, Routes), `odo` abstracts them away so you can focus on writing code and seeing changes instantly. In this lesson you will install `odo`, initialize a Devfile-based component, use `odo dev` for live-sync inner-loop development, and then deploy to the cluster with `odo deploy` — all without writing a single YAML manifest by hand.

## Prerequisites

- Level 1 completed (especially L1-M3 on application deployment and L1-M1.3 on `oc` CLI)
- L2-M6.1 (OpenShift Dev Spaces) completed — gives context on Devfiles
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI installed and logged in
- A text editor for editing source code

## K8s Context

In vanilla Kubernetes, the developer inner loop looks like this:

1. Edit code.
2. Build a container image (docker build / podman build / kaniko).
3. Push the image to a registry.
4. Update the Deployment manifest (or Helm values) with the new image tag.
5. Apply the manifest (`kubectl apply -f ...`).
6. Wait for rollout.
7. Test.
8. Repeat.

This cycle takes minutes per iteration and breaks your flow. Tools like Skaffold, Tilt, and Telepresence exist in the Kubernetes ecosystem to shorten this loop, but none are built into the platform. OpenShift offers `odo` as a first-party, platform-integrated alternative that works with Devfiles — the same standard used by Eclipse Che / OpenShift Dev Spaces.

## Concepts

### What Is odo?

`odo` (OpenShift Do) is a developer-focused CLI that operates at the application level rather than the resource level. Instead of thinking about Deployments, Services, and Routes, you think about **components** — your application code plus the runtime it needs.

Key design principles:

- **Developer-first**: no Kubernetes/OpenShift resource knowledge required.
- **Inner-loop speed**: `odo dev` syncs code changes into a running container in seconds, not minutes.
- **Devfile-driven**: uses the open [Devfile](https://devfile.io) standard to describe development environments, the same standard behind OpenShift Dev Spaces (L2-M6.1).
- **Outer-loop ready**: `odo deploy` builds a production image and creates real OpenShift resources.

### odo vs oc — Mental Model

| Aspect | `oc` | `odo` |
|--------|------|-------|
| Audience | Developers + Operators | Developers only |
| Abstraction level | Kubernetes resources | Application components |
| Inner loop | Manual build/push/apply | `odo dev` (live sync) |
| Outer loop | `oc apply -f ...` | `odo deploy` |
| Configuration | YAML manifests | Devfile (`devfile.yaml`) |
| Learning curve | Must know K8s primitives | Minimal K8s knowledge needed |

### The Devfile

A Devfile (`devfile.yaml`) is an open standard that describes:

- **Container components**: the runtime images used during development (e.g., Node.js 20, Python 3.12).
- **Commands**: how to build, run, test, and debug the application.
- **Endpoints**: ports the application exposes.
- **Deployment resources** (via `kubernetes` or `openshift` components): the manifests used for `odo deploy`.

When you run `odo init`, odo pulls a starter Devfile from the Devfile registry and customizes it for your project. You saw Devfiles in L2-M6.1 with Dev Spaces — `odo` uses the same format.

### Inner Loop vs Outer Loop

- **Inner loop** (`odo dev`): your local edit-run-test cycle. Code changes are synced into a running development container on the cluster. The container runs your app with hot-reload. No image build or registry push is needed.
- **Outer loop** (`odo deploy`): production deployment. Builds an actual container image (using BuildConfig or Dockerfile), pushes it to the internal registry, and creates Deployment/Service/Route resources on the cluster.

## Step-by-Step

### Step 1: Install odo

Download the `odo` binary for your platform.

**macOS (Apple Silicon):**

```bash
curl -L https://developers.redhat.com/content-gateway/rest/mirror/pub/openshift-v4/clients/odo/v3.16.1/odo-darwin-arm64 -o odo
chmod +x odo
sudo mv odo /usr/local/bin/
```

**macOS (Intel):**

```bash
curl -L https://developers.redhat.com/content-gateway/rest/mirror/pub/openshift-v4/clients/odo/v3.16.1/odo-darwin-amd64 -o odo
chmod +x odo
sudo mv odo /usr/local/bin/
```

**Linux (x86_64):**

```bash
curl -L https://developers.redhat.com/content-gateway/rest/mirror/pub/openshift-v4/clients/odo/v3.16.1/odo-linux-amd64 -o odo
chmod +x odo
sudo mv odo /usr/local/bin/
```

Verify the installation:

```bash
odo version
```

Expected output:

```
odo v3.16.1 (5a3e3bd62)

Server: https://api.crc.testing:6443
Kubernetes: v1.28.x
```

> **Tip:** You can also install via `brew install odo-dev` on macOS, or check [the odo releases page](https://github.com/redhat-developer/odo/releases) for the latest version.

### Step 2: Create a Project and Application Directory

Create a dedicated OpenShift project and a local working directory for this lesson:

```bash
oc new-project odo-demo
```

```bash
mkdir -p /tmp/odo-lesson && cd /tmp/odo-lesson
```

Create a simple Node.js application to work with:

```bash
cat > app.js << 'APPEOF'
const http = require("http");

const PORT = 3000;

const server = http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({
    message: "Hello from odo!",
    timestamp: new Date().toISOString(),
    path: req.url,
  }));
});

server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
APPEOF
```

```bash
cat > package.json << 'PKGEOF'
{
  "name": "odo-demo",
  "version": "1.0.0",
  "description": "Demo app for odo lesson",
  "main": "app.js",
  "scripts": {
    "start": "node app.js",
    "dev": "node --watch app.js"
  }
}
PKGEOF
```

### Step 3: Initialize a Devfile Component with odo init

Use `odo init` to create a Devfile for your project. This is analogous to `npm init` or `git init` — it sets up the odo project metadata.

```bash
odo init --name odo-demo --devfile nodejs --devfile-registry DefaultDevfileRegistry
```

Expected output:

```
 Your new component 'odo-demo' is ready in the current directory.
To start editing your component, use 'odo dev' and open this folder in your favorite IDE.
Changes will be directly reflected on the cluster.
```

This creates a `devfile.yaml` in your project root. Examine it:

```bash
cat devfile.yaml
```

The generated Devfile contains:

- A **container component** (e.g., `nodejs`) specifying the development image.
- A **command** for running the app (`npm start` or similar).
- **Endpoint** declarations (port 3000).

> **Note:** You can also run `odo init` interactively (without flags) to browse available Devfile stacks and select one.

### Step 4: Explore Available Devfile Stacks

Before continuing, see what Devfile stacks are available in the registry:

```bash
odo registry
```

Expected output (abbreviated):

```
 NAME                REGISTRY                DESCRIPTION
 dotnet60            DefaultDevfileRegistry  .NET 6.0 application
 go                  DefaultDevfileRegistry  Go application
 java-maven          DefaultDevfileRegistry  Java application (Maven)
 java-quarkus        DefaultDevfileRegistry  Quarkus Java application
 java-springboot     DefaultDevfileRegistry  Spring Boot application
 nodejs              DefaultDevfileRegistry  Node.js application
 python              DefaultDevfileRegistry  Python application
 ...
```

These are the same Devfile stacks used by OpenShift Dev Spaces. If your team has a custom Devfile registry, you can add it:

```bash
odo preference add registry MyRegistry https://registry.example.com
```

### Step 5: Start Inner-Loop Development with odo dev

This is where `odo` shines. Start the development session:

```bash
odo dev
```

Expected output:

```
 Deploying to the cluster in developer mode
 ✓  Waiting for Kubernetes resources  ...
 ✓  Syncing files into the container  ...
 ✓  Building your application  ...
 ✓  Executing the application (devRun)  ...

Your application is now running on the cluster.

 Forwarding from 127.0.0.1:40001 -> 3000

Watching for changes in the current directory /tmp/odo-lesson
Press Ctrl+c to exit `odo dev` and delete resources from the cluster
```

What just happened:

1. `odo` created a development container on the cluster using the image from the Devfile.
2. Your local source code was synced into the container.
3. The application was started inside the container.
4. A port-forward was set up so you can access the app locally.

Test the application:

```bash
# In a separate terminal
curl http://127.0.0.1:40001
```

Expected output:

```json
{"message":"Hello from odo!","timestamp":"2026-06-24T10:30:00.000Z","path":"/"}
```

### Step 6: Experience Live Sync

With `odo dev` still running, modify the source code. Edit `app.js` and change the message:

```bash
# In a separate terminal, edit the message
sed -i.bak 's/Hello from odo!/Hello from odo — live sync works!/' /tmp/odo-lesson/app.js
```

Watch the `odo dev` terminal — it detects the change and re-syncs:

```
 File /tmp/odo-lesson/app.js changed
 ✓  Syncing files into the container  ...
 ✓  Executing the application (devRun)  ...
```

Test again:

```bash
curl http://127.0.0.1:40001
```

Expected output:

```json
{"message":"Hello from odo -- live sync works!","timestamp":"2026-06-24T10:31:15.000Z","path":"/"}
```

The change was reflected in seconds — no image build, no push, no manifest update. This is the inner-loop speed advantage of `odo`.

### Step 7: Examine What odo Created on the Cluster

While `odo dev` is running, open another terminal and inspect the cluster resources:

```bash
oc get all -n odo-demo -l app.kubernetes.io/managed-by=odo
```

Expected output:

```
NAME                              READY   STATUS    RESTARTS   AGE
pod/odo-demo-app-7d4f5b8c9-x2k4l 1/1     Running   0          3m

NAME                       TYPE        CLUSTER-IP      PORT(S)
service/odo-demo-app       ClusterIP   172.30.45.120   3000/TCP
```

Notice:
- `odo dev` creates development-mode resources (a Pod and a Service) but does NOT create a Route — it uses port-forwarding instead.
- These are temporary resources that are deleted when you press Ctrl+C in the `odo dev` session.

### Step 8: Stop the Dev Session

Press **Ctrl+C** in the `odo dev` terminal:

```
 ✓  Deleting resources from the cluster
 ✓  Successfully deleted all resources
```

The development resources are cleaned up automatically. Verify:

```bash
oc get all -n odo-demo
```

Expected output:

```
No resources found in odo-demo namespace.
```

### Step 9: Customize the Devfile for Production Deployment

Before running `odo deploy`, you need to add deployment configuration to the Devfile. Edit `devfile.yaml` to include an `image` component and a `deploy` command.

You can use the provided Devfile from this lesson's manifests:

```bash
# Copy the production-ready Devfile from the lesson manifests
cp manifests/devfile-deploy.yaml devfile.yaml
```

Or manually add the deploy section to your existing `devfile.yaml`. The key additions are:

```yaml
# Added under components:
- name: deploy
  kubernetes:
    uri: manifests/deployment.yaml

# Added under commands:
- id: build-image
  apply:
    component: image
- id: deploy-k8s
  apply:
    component: deploy
- id: deploy
  composite:
    commands:
      - build-image
      - deploy-k8s
    group:
      kind: deploy
      isDefault: true
```

This tells `odo deploy` to:
1. Build a container image using the Dockerfile.
2. Apply the Kubernetes/OpenShift manifests for production deployment.

Create a simple Dockerfile for the production build:

```bash
cat > Dockerfile << 'DEOF'
FROM registry.access.redhat.com/ubi9/nodejs-20-minimal:latest
COPY package.json ./
RUN npm install --production
COPY app.js ./
EXPOSE 3000
CMD ["node", "app.js"]
DEOF
```

### Step 10: Deploy to Production with odo deploy

Now run the outer-loop deployment:

```bash
odo deploy
```

Expected output:

```
 __
 /  \__     Deploying the application using odo-demo Devfile
 \__/  \    Namespace: odo-demo
 /  \__/    odo version: 3.16.1
 \__/

 ✓  Building image locally  ...
 ✓  Pushing image to cluster registry  ...
 ✓  Deploying Kubernetes resources  ...

Your application has been successfully deployed.
```

Check the deployed resources:

```bash
oc get all -n odo-demo
```

Expected output:

```
NAME                            READY   STATUS    RESTARTS   AGE
pod/odo-demo-5d7f8b4c6-m2k9j   1/1     Running   0          30s

NAME               TYPE        CLUSTER-IP      PORT(S)    AGE
service/odo-demo   ClusterIP   172.30.67.89    3000/TCP   30s

NAME                       READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/odo-demo   1/1     1            1           30s

NAME                                        HOST/PORT                                   PATH
route.route.openshift.io/odo-demo           odo-demo-odo-demo.apps-crc.testing
```

Test the deployed application via the Route:

```bash
curl http://odo-demo-odo-demo.apps-crc.testing
```

### Step 11: Compare the Developer Workflows

Now that you have experienced both, compare the `oc` and `odo` workflows side by side.

**The oc workflow** (what you learned in Level 1):

```bash
# 1. Write/edit YAML manifests (Deployment, Service, Route, BuildConfig, ImageStream)
# 2. Apply them
oc apply -f manifests/

# 3. Start a build
oc start-build my-app --from-dir=.

# 4. Wait for build and rollout
oc rollout status deployment/my-app

# 5. Make a code change
# 6. Repeat steps 3-4 (minutes per iteration)
```

**The odo workflow**:

```bash
# 1. Initialize once
odo init

# 2. Start developing (live sync, seconds per iteration)
odo dev

# 3. Make code changes — they appear immediately

# 4. When ready for production
odo deploy
```

The time savings compound. A developer iterating 50 times a day saves hours per week using `odo dev` versus the manual `oc` build-deploy cycle.

## Verification

Run through these checks to verify the lesson worked correctly.

**1. odo is installed and connected:**

```bash
odo version
```

You should see the odo version and the connected server URL.

**2. odo dev syncs changes (run and test):**

```bash
cd /tmp/odo-lesson
odo dev &
sleep 15
curl http://127.0.0.1:40001
# Should return JSON response
kill %1
```

**3. odo deploy created production resources:**

```bash
oc get deployment odo-demo -n odo-demo -o jsonpath='{.status.availableReplicas}'
# Expected: 1

oc get route odo-demo -n odo-demo -o jsonpath='{.spec.host}'
# Expected: odo-demo-odo-demo.apps-crc.testing
```

**4. Devfile exists and is valid:**

```bash
ls -la /tmp/odo-lesson/devfile.yaml
odo list -n odo-demo
```

Expected output from `odo list`:

```
 NAME       PROJECT NAME   STATE     MANAGED BY ODO
 odo-demo   odo-demo       Deployed  Deploy
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift with odo |
|--------|-----------|-------------------|
| Inner-loop tool | Skaffold / Tilt / Telepresence (third-party) | `odo dev` (first-party, integrated) |
| Dev environment spec | Custom tooling | Devfile (open standard) |
| Code sync | Depends on tool | Built-in live sync |
| Outer-loop deploy | `kubectl apply` + CI/CD | `odo deploy` or `oc apply` |
| Image build | External (docker/kaniko/buildah) | Built-in (BuildConfig, S2I, Dockerfile) |
| Port forwarding | `kubectl port-forward` (manual) | Automatic in `odo dev` |
| Resource cleanup | Manual (`kubectl delete`) | Automatic on Ctrl+C (`odo dev`) |
| IDE integration | Varies by tool | Dev Spaces uses same Devfile |
| Developer onboarding | Install + configure multiple tools | `odo init` + `odo dev` |
| Who manages manifests? | Developer writes YAML | odo generates from Devfile |

## Key Takeaways

- **`odo` is for inner-loop speed**: it eliminates the build-push-deploy cycle during development by syncing code directly into a running container on the cluster.
- **`oc` and `odo` are complementary, not competing**: use `odo dev` while coding, `oc` for cluster operations, debugging, and anything beyond application development.
- **Devfiles are the standard**: the same `devfile.yaml` works with `odo`, OpenShift Dev Spaces, and other Devfile-compatible tools. Define your dev environment once, use it everywhere.
- **`odo deploy` bridges inner to outer loop**: when your code is ready, `odo deploy` builds a production image and creates real OpenShift resources without requiring you to write deployment manifests by hand.
- **Zero-to-running is fast**: a new developer can `git clone`, `odo init`, `odo dev`, and have a live application in under a minute with no Kubernetes knowledge required.

## Cleanup

```bash
# Delete the deployed application
cd /tmp/odo-lesson
odo delete component --name odo-demo --force

# Delete the OpenShift project
oc delete project odo-demo

# Remove the local working directory
rm -rf /tmp/odo-lesson
```

## Next Steps

In **L2-M6.3 — Helm on OpenShift**, you will learn how to use Helm charts on OpenShift, including the integrated Helm chart repository in the Web Console, installing and managing Helm releases, and working with Red Hat-certified Helm charts. You will see how Helm complements `odo` — Helm manages packaged applications, while `odo` focuses on the development workflow.
