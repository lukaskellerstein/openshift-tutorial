# L2-M1.4 -- Pipelines + GitOps Together

**Level:** Practitioner
**Duration:** 45 min

## Overview

In the previous two lessons you used Tekton pipelines for CI and ArgoCD for CD as separate tools. Now you connect them into one automated flow: a code change triggers a Tekton pipeline that builds, tests, and pushes a new container image, then updates the image tag in a GitOps repository. ArgoCD detects the Git commit and syncs the new version to the cluster -- zero manual deployment steps.

This is the industry-standard GitOps CI/CD pattern. The pipeline is responsible for Continuous Integration (build and test), and ArgoCD handles Continuous Delivery (deploy). The Git repository is the single source of truth for what is running on the cluster.

## Prerequisites

- Completed: L2-M1.2 (Pipeline: Build, Test, Deploy) and L2-M1.3 (OpenShift GitOps / ArgoCD)
- OpenShift cluster running (CRC or Developer Sandbox)
- OpenShift Pipelines operator installed (from L2-M1.2)
- OpenShift GitOps operator installed (from L2-M1.3)
- A GitHub account (or any Git hosting with API token support)
- `git` CLI installed locally

## K8s Context

In vanilla Kubernetes, connecting CI and CD requires gluing together external tools yourself. A typical pattern looks like:

1. GitHub Actions or Jenkins builds and pushes an image
2. The CI job updates a Helm values file or Kustomize overlay in a separate Git repo
3. A self-installed ArgoCD watches that repo and applies changes

Every team assembles this differently -- there is no standard way to connect the CI output to the CD input. You install and configure each piece independently, manage credentials across systems, and handle failure modes at each boundary.

OpenShift provides both Tekton (Pipelines) and ArgoCD (GitOps) as managed operators with integrated RBAC, shared credential management, and cluster-native features like ImageStreams. The pattern is the same, but the platform removes most of the setup burden.

## Concepts

### The CI/CD Boundary: Image Tag as Contract

The key insight in the Pipelines + GitOps pattern is the **separation of concerns at the image tag**:

- **CI (Tekton)** owns: clone, test, build, push image, update the image tag in Git
- **CD (ArgoCD)** owns: watch Git, detect changes, sync desired state to the cluster

The **image tag** is the contract between CI and CD. The pipeline produces a new tag (typically a Git commit SHA), writes it into the GitOps repository, and its job is done. ArgoCD takes over from there.

```
Code Repo                          GitOps Repo                    Cluster
---------                          -----------                    -------
  push  -->  Tekton Pipeline  -->  update image tag  -->  ArgoCD  -->  deploy
             (build + test)        (git commit)           (sync)
```

### Why Commit SHA as the Image Tag?

Using the source commit SHA (e.g., `a3f8b2c`) as the image tag creates full traceability:

- From a running pod, you can read the image tag to find the exact source commit
- From a source commit, you can find the exact image that was built
- The GitOps repo commit log shows which source versions were deployed and when

Never use `latest` as an image tag in a GitOps workflow -- it breaks the entire model because ArgoCD cannot detect a change if the tag stays the same.

### Two Repositories, Two Concerns

This pattern uses two separate Git repositories:

| Repository | Contains | Who writes | Who reads |
|------------|----------|------------|-----------|
| Source repo | Application code, Dockerfile, tests | Developers | Tekton (clone + build) |
| GitOps repo | Deployment, Service, Route manifests | Tekton (update image tag) | ArgoCD (sync to cluster) |

Separating the repos enforces clean boundaries. Developers never directly modify what is deployed -- they push code, the pipeline validates it, and the manifests are updated automatically.

### The Pipeline's GitOps Update Step

The critical new piece compared to L2-M1.2 is the `update-gitops-repo` task. This Tekton task:

1. Clones the GitOps repository
2. Replaces the image tag in the deployment manifest with the new commit SHA
3. Commits and pushes the change back to Git

This Git push is what triggers ArgoCD. ArgoCD polls the GitOps repo (default: every 3 minutes) or receives a webhook, detects the new commit, and syncs the cluster state to match.

## Step-by-Step

### Step 1: Run the Setup Script

The setup script creates the project, verifies that both operators are installed, and prepares the namespace.

```bash
# From the lesson directory
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Or do it manually:

```bash
# Create the project
oc new-project pipelines-gitops-demo --display-name="CI/CD + GitOps Demo"
```

Expected output:

```
Now using project "pipelines-gitops-demo" on server "https://api.crc.testing:6443".
```

Verify both operators are available:

```bash
# Check Tekton (OpenShift Pipelines)
oc get csv -n openshift-pipelines | grep pipelines
```

```
openshift-pipelines-operator-rh.v1.x.x   Red Hat OpenShift Pipelines   Succeeded
```

```bash
# Check ArgoCD (OpenShift GitOps)
oc get csv -n openshift-gitops | grep gitops
```

```
openshift-gitops-operator.v1.x.x   Red Hat OpenShift GitOps   Succeeded
```

### Step 2: Create Two Git Repositories

You need two repositories on GitHub (or your Git host of choice).

**Source repository** -- contains the application code:

```bash
# Create a new repo called demo-app-source on GitHub, then:
mkdir demo-app-source && cd demo-app-source
git init

# Copy the application files from this lesson
cp /path/to/this/lesson/app/* .

# Commit and push
git add -A
git commit -m "Initial application code"
git remote add origin https://github.com/<your-username>/demo-app-source.git
git push -u origin main
```

**GitOps repository** -- contains the Kubernetes/OpenShift manifests:

```bash
# Create a new repo called demo-app-gitops on GitHub, then:
mkdir demo-app-gitops && cd demo-app-gitops
git init

# Copy the GitOps manifests from this lesson
cp /path/to/this/lesson/manifests/gitops-repo-deployment.yaml deployment.yaml
cp /path/to/this/lesson/manifests/gitops-repo-service.yaml service.yaml
cp /path/to/this/lesson/manifests/gitops-repo-route.yaml route.yaml

# Commit and push
git add -A
git commit -m "Initial GitOps manifests"
git remote add origin https://github.com/<your-username>/demo-app-gitops.git
git push -u origin main
```

### Step 3: Configure Git Credentials for the Pipeline

The pipeline needs write access to the GitOps repo to push manifest changes. Create a Personal Access Token (PAT) on GitHub with `repo` scope, then create the secret:

```bash
# Create the secret with your actual credentials
oc create secret generic git-credentials \
  --type=kubernetes.io/basic-auth \
  --from-literal=username=<your-git-username> \
  --from-literal=password=<your-git-token> \
  -n pipelines-gitops-demo

# Annotate the secret so Tekton knows which Git host it applies to
oc annotate secret git-credentials \
  tekton.dev/git-0=https://github.com \
  -n pipelines-gitops-demo
```

Now create the ServiceAccount that uses this secret:

```bash
oc apply -f manifests/pipeline-sa.yaml
```

> **Security note:** In production, use a deploy key or a machine user account with minimal permissions instead of a personal access token. The token only needs write access to the GitOps repository, not all your repos.

### Step 4: Create the ImageStream

The internal registry needs an ImageStream to receive the built images:

```bash
oc apply -f manifests/imagestream.yaml
```

Expected output:

```
imagestream.image.openshift.io/demo-app created
```

### Step 5: Deploy the Tekton Tasks

Apply all four custom tasks that make up the pipeline:

```bash
# Apply all tasks
oc apply -f manifests/task-run-tests.yaml
oc apply -f manifests/task-generate-tag.yaml
oc apply -f manifests/task-build-and-push.yaml
oc apply -f manifests/task-update-gitops-repo.yaml
```

Verify the tasks are created:

```bash
oc get tasks
```

Expected output:

```
NAME                  AGE
build-and-push        5s
generate-image-tag    5s
run-tests             5s
update-gitops-repo    5s
```

### Step 6: Deploy the Pipeline

```bash
oc apply -f manifests/pipeline.yaml
```

Examine the pipeline structure:

```bash
oc get pipeline ci-cd-pipeline -o yaml | grep -A 5 "tasks:"
```

The pipeline has five steps that execute in this order:

```
clone-source ──> run-tests    ──> build-image ──> update-gitops
             └─> generate-tag ─┘
```

`run-tests` and `generate-tag` run in parallel after the clone (both depend only on `clone-source`). `build-image` waits for both to succeed before starting. `update-gitops` runs last.

### Step 7: Configure ArgoCD to Watch the GitOps Repository

Grant ArgoCD permission to manage resources in the demo namespace:

```bash
oc apply -f manifests/argocd-rbac-rolebinding.yaml
```

Now edit the ArgoCD Application manifest to point to your GitOps repository:

```bash
# Edit the repoURL in the manifest before applying
# Replace <your-username> with your actual GitHub username
sed 's/<your-username>/YOUR_ACTUAL_USERNAME/g' \
  manifests/argocd-application.yaml | oc apply -f -
```

Verify the Application was created:

```bash
oc get application -n openshift-gitops
```

Expected output:

```
NAME       SYNC STATUS   HEALTH STATUS
demo-app   Synced        Healthy
```

ArgoCD will immediately sync the current state of the GitOps repo. Check that the initial deployment is running:

```bash
oc get pods -n pipelines-gitops-demo
```

Expected output:

```
NAME                        READY   STATUS    RESTARTS   AGE
demo-app-6b7f8c9d4-x2k9p   1/1     Running   0          30s
demo-app-6b7f8c9d4-m8n3q   1/1     Running   0          30s
```

### Step 8: Run the Pipeline (The Full CI/CD Flow)

This is the moment everything comes together. Edit the PipelineRun manifest with your repository URLs, then trigger the pipeline:

```bash
# Edit the PipelineRun with your actual repo URLs
sed 's|<your-username>|YOUR_ACTUAL_USERNAME|g' \
  manifests/pipelinerun.yaml | oc create -f -
```

> **Note:** We use `oc create` (not `oc apply`) because PipelineRun uses `generateName` to create a unique name each time.

Watch the pipeline execution:

```bash
# List the PipelineRun
oc get pipelineruns

# Follow the logs of the running pipeline
oc logs -f $(oc get pipelinerun -o name | tail -1) --all-containers
```

Expected output (abbreviated):

```
[clone-source] Cloning into '/workspace/output'...
[run-tests]    ==> Running application tests
[run-tests]    Basic validation passed
[run-tests]    ==> Tests completed successfully
[generate-tag] ==> Image tag will be: a3f8b2c
[build-image]  ==> Building image ...demo-app:a3f8b2c
[build-image]  ==> Image built and pushed: ...demo-app:a3f8b2c
[update-gitops] ==> Cloning GitOps repo...
[update-gitops] ==> Updating image in deployment.yaml to ...demo-app:a3f8b2c
[update-gitops] ==> Pushing changes to main
[update-gitops] ==> GitOps repo updated. ArgoCD will detect the change.
```

### Step 9: Watch ArgoCD Detect and Sync the Change

After the pipeline pushes to the GitOps repo, ArgoCD will detect the change within its polling interval (default 3 minutes). You can speed this up:

```bash
# Force ArgoCD to check now (requires argocd CLI, optional)
# argocd app get demo-app --refresh

# Or watch the Application status
oc get application demo-app -n openshift-gitops -w
```

Expected output after sync:

```
NAME       SYNC STATUS   HEALTH STATUS
demo-app   Synced        Healthy
```

Verify the pods are running the new image:

```bash
oc get pods -n pipelines-gitops-demo -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}'
```

Expected output:

```
demo-app-7c9f8d5e2-k4m8p   image-registry.openshift-image-registry.svc:5000/pipelines-gitops-demo/demo-app:a3f8b2c
demo-app-7c9f8d5e2-n7x2r   image-registry.openshift-image-registry.svc:5000/pipelines-gitops-demo/demo-app:a3f8b2c
```

The image tag (`a3f8b2c`) matches the commit SHA from the source repository -- full traceability from code to deployment.

### Step 10: Verify via the Web Console

Open the OpenShift Web Console and observe the flow from both perspectives.

**Developer perspective (Pipelines):**

1. Navigate to **Pipelines** in the `pipelines-gitops-demo` project
2. Click on `ci-cd-pipeline` to see the pipeline definition
3. Click on the **PipelineRuns** tab to see execution history
4. Click a specific run to see the step-by-step graph with logs

**ArgoCD dashboard:**

```bash
# Get the ArgoCD route
oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}'
```

1. Open the URL in a browser (prefix with `https://`)
2. Log in with OpenShift credentials
3. Click the `demo-app` application tile
4. Observe the resource tree: Application > Deployment > ReplicaSet > Pods
5. The **Last Sync** timestamp shows when ArgoCD applied the change

### Step 11: Simulate a Code Change (End-to-End Validation)

To see the full loop, make a code change and watch it flow through automatically:

```bash
# In your demo-app-source repository
cd demo-app-source

# Change the version
sed -i 's/1.0.0/1.1.0/' app.py

# Commit and push
git add app.py
git commit -m "Bump version to 1.1.0"
git push origin main
```

Now trigger the pipeline again (in production, you would use a webhook trigger):

```bash
# Trigger a new PipelineRun
sed 's|<your-username>|YOUR_ACTUAL_USERNAME|g' \
  manifests/pipelinerun.yaml | oc create -f -
```

Watch the entire flow:

```bash
# Follow the pipeline
oc get pipelinerun -w

# After it completes, check ArgoCD
oc get application demo-app -n openshift-gitops

# Verify the new version is deployed
oc exec $(oc get pod -l app=demo-app -o name | head -1) \
  -- curl -s localhost:8080 | python3 -m json.tool
```

Expected output:

```json
{
    "message": "Hello from the CI/CD + GitOps demo app!",
    "version": "1.1.0"
}
```

## Verification

Run these checks to confirm the full integration is working:

```bash
echo "=== Pipeline Status ==="
oc get pipelinerun --sort-by=.metadata.creationTimestamp | tail -3

echo ""
echo "=== ArgoCD Application ==="
oc get application demo-app -n openshift-gitops \
  -o jsonpath='Sync: {.status.sync.status}  Health: {.status.health.status}{"\n"}'

echo ""
echo "=== Running Pods ==="
oc get pods -l app=demo-app -n pipelines-gitops-demo

echo ""
echo "=== Image Tags in Use ==="
oc get pods -l app=demo-app -n pipelines-gitops-demo \
  -o jsonpath='{range .items[*]}{.spec.containers[0].image}{"\n"}{end}'

echo ""
echo "=== Route ==="
oc get route demo-app -n pipelines-gitops-demo \
  -o jsonpath='https://{.spec.host}{"\n"}'
```

All PipelineRuns should show `Succeeded`. The ArgoCD Application should show `Synced` and `Healthy`. The pod image tags should contain a commit SHA, not `latest`.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| CI pipeline engine | Install Tekton or use external CI (GitHub Actions, Jenkins) | OpenShift Pipelines operator (managed Tekton) |
| CD engine | Install ArgoCD manually via Helm or YAML | OpenShift GitOps operator (managed ArgoCD) |
| Container registry | External registry (Docker Hub, ECR, GCR) | Built-in internal registry with ImageStreams |
| Build system | External (Docker, Kaniko, Buildpacks) | Built-in BuildConfig with S2I and Docker strategies |
| Credential management | Kubernetes Secrets + manual wiring | Tekton annotations (`tekton.dev/git-0`) link secrets to repos |
| RBAC for CI/CD | Configure ClusterRoles/RoleBindings manually | Operators create default RBAC; SA setup is simpler |
| Pipeline visibility | `tkn` CLI or third-party dashboards | Integrated in Web Console (Developer perspective) |
| GitOps visibility | ArgoCD UI (self-hosted) | ArgoCD UI integrated with OpenShift authentication |
| Image traceability | Manual -- track tags yourself | ImageStream history + build logs linked in console |
| Triggering | Configure webhooks + Tekton triggers manually | Same setup, but EventListener Routes are created natively |

## Key Takeaways

- **The image tag is the contract between CI and CD.** Tekton produces a tagged image and writes the tag to Git. ArgoCD reads Git and syncs to the cluster. Neither tool needs to know about the other -- Git is the interface.

- **Two repositories enforce separation of concerns.** The source repo holds application code (developers' domain). The GitOps repo holds deployment manifests (operations' domain). The pipeline is the only automated bridge between them.

- **Never use `latest` in a GitOps workflow.** ArgoCD detects changes by comparing Git state to cluster state. If the image tag never changes, ArgoCD sees nothing to sync. Always use commit SHAs, semantic versions, or build numbers.

- **OpenShift simplifies the integration.** On vanilla Kubernetes, you install Tekton, ArgoCD, and a container registry separately, then wire them together. OpenShift provides all three as managed operators with integrated authentication, RBAC, and Web Console visibility.

- **The pipeline should never directly deploy to the cluster.** In a GitOps model, the pipeline's last step is a Git commit, not a `kubectl apply`. This ensures the Git repository remains the single source of truth.

## Troubleshooting

### PipelineRun fails at `clone-source`

- **Symptom:** `Permission denied` or `Repository not found`
- **Cause:** The `git-credentials` secret is misconfigured or missing the `tekton.dev/git-0` annotation
- **Fix:**
  ```bash
  oc get secret git-credentials -o yaml | grep tekton.dev
  # Should show: tekton.dev/git-0: https://github.com
  ```

### PipelineRun fails at `update-gitops` (push rejected)

- **Symptom:** `remote: Permission to <repo> denied`
- **Cause:** The Git token does not have write access to the GitOps repository
- **Fix:** Regenerate the GitHub PAT with `repo` scope and update the secret:
  ```bash
  oc delete secret git-credentials
  oc create secret generic git-credentials \
    --type=kubernetes.io/basic-auth \
    --from-literal=username=<your-username> \
    --from-literal=password=<new-token>
  oc annotate secret git-credentials tekton.dev/git-0=https://github.com
  ```

### ArgoCD shows `OutOfSync` but does not sync

- **Symptom:** Application status is `OutOfSync` indefinitely
- **Cause:** ArgoCD does not have permission to create resources in the target namespace
- **Fix:**
  ```bash
  oc apply -f manifests/argocd-rbac-rolebinding.yaml
  ```

### ArgoCD shows `Unknown` health

- **Symptom:** Application health is `Unknown` or `Degraded`
- **Cause:** Pods are failing to start (usually image pull errors or SCC issues)
- **Fix:**
  ```bash
  oc get events -n pipelines-gitops-demo --sort-by=.lastTimestamp | tail -10
  oc describe pod -l app=demo-app -n pipelines-gitops-demo | grep -A 5 "Events:"
  ```

### Pipeline succeeds but ArgoCD does not pick up the change

- **Symptom:** GitOps repo has the new commit, but ArgoCD still shows old image
- **Cause:** ArgoCD default polling interval is 3 minutes
- **Fix:** Wait for the next poll, or reduce the interval:
  ```bash
  oc edit configmap argocd-cm -n openshift-gitops
  # Add: timeout.reconciliation: 60s
  ```
  Or configure a webhook from your Git host to ArgoCD for instant detection.

### Build fails with SCC errors

- **Symptom:** `unable to validate against any security context constraint`
- **Cause:** The build ServiceAccount lacks the required SCC
- **Fix:**
  ```bash
  oc adm policy add-scc-to-user privileged -z pipeline-gitops-sa
  ```
  In production, prefer fixing the Dockerfile to run as non-root (as the included `app/Dockerfile` does with `USER 1001`).

## Cleanup

```bash
# Option 1: Use the teardown script
chmod +x scripts/teardown.sh
./scripts/teardown.sh

# Option 2: Manual cleanup
# Delete the ArgoCD Application first (stops syncing)
oc delete application demo-app -n openshift-gitops

# Delete all resources by label
oc delete all -l tutorial-level=2,tutorial-module=M1 -n pipelines-gitops-demo

# Delete Tekton resources
oc delete pipeline,task,pipelinerun --all -n pipelines-gitops-demo

# Delete secrets and service accounts
oc delete secret git-credentials -n pipelines-gitops-demo
oc delete sa pipeline-gitops-sa -n pipelines-gitops-demo
oc delete rolebinding argocd-admin -n pipelines-gitops-demo

# Delete the project
oc delete project pipelines-gitops-demo
```

Optionally delete the two Git repositories you created (demo-app-source, demo-app-gitops).

## Next Steps

In **L2-M2.1 -- Operator Framework Concepts**, you will learn how OpenShift uses operators to manage complex applications and cluster services. You have already been using two operators in this CI/CD module (Pipelines and GitOps) -- now you will understand the Operator Framework that makes them work, including OLM (Operator Lifecycle Manager), CRDs, and the controller pattern.
