# L2-M1.2 --- Pipeline: Build, Test, Deploy

**Level:** Practitioner
**Duration:** 1 hr

## Overview

In this lesson you will build an end-to-end CI/CD pipeline on OpenShift using Tekton (OpenShift Pipelines). The pipeline clones a Git repository, builds a container image with Buildah, runs the test suite, deploys to a staging environment, and then promotes the exact same image to production. You already know how to string together CI steps in tools like GitHub Actions or Jenkins --- here you will do it the Kubernetes-native way with Tasks, Pipelines, PipelineRuns, and workspaces, all running as first-class resources inside the cluster.

## Prerequisites

- Completed: [L2-M1.1 --- OpenShift Pipelines (Tekton)](../1_openshift_pipelines_tekton/README.md)
- OpenShift cluster running (CRC or Developer Sandbox)
- OpenShift Pipelines Operator installed (from L2-M1.1)
- `tkn` CLI installed (optional but recommended)
- Familiarity with Tekton concepts: Task, Pipeline, PipelineRun, workspace (covered in L2-M1.1)

## K8s Context

In vanilla Kubernetes, CI/CD pipelines live outside the cluster. You configure GitHub Actions, GitLab CI, or Jenkins to build images, push them to an external registry, then `kubectl apply` a new Deployment. The pipeline tool has no native understanding of K8s resources --- it shells out to `kubectl`.

Tekton flips this model. Each CI step is a Pod. The pipeline definition is a Kubernetes custom resource. The pipeline controller watches for PipelineRun objects and schedules the work as Pods on your cluster. This means your CI/CD benefits from K8s RBAC, resource quotas, node scheduling, and observability --- exactly the same way your workloads do.

## Concepts

### Tasks --- the building blocks

A **Task** is a sequence of **Steps**, each running in its own container within a single Pod. Steps in a Task share a Pod filesystem, which makes passing files between steps trivial (just write to `/workspace`). However, Tasks run as separate Pods, so data must be passed explicitly via **workspaces** or **results**.

### Pipelines --- the orchestration layer

A **Pipeline** connects Tasks into a directed acyclic graph (DAG). You define ordering with `runAfter`, and the controller executes independent Tasks in parallel. For example, the "build" and "test" Tasks in this lesson can run concurrently after "clone" because they both only need the source code --- neither depends on the other's output.

### Workspaces --- shared data between Tasks

A **workspace** is Tekton's abstraction for shared storage. When you bind a workspace to a PersistentVolumeClaim (PVC), every Task in the Pipeline can read and write to the same volume. This is how the cloned source code flows from the clone Task to the build and test Tasks.

Key points about workspaces:
- A workspace in a Pipeline is mapped to a workspace in each Task.
- Backed by a PVC, the data persists across Task Pods.
- Multiple Tasks can use the same workspace, but Tekton schedules them sequentially if they share a `ReadWriteOnce` PVC (unless you use `ReadWriteMany` storage).

### Results --- lightweight data passing

For small values (a commit SHA, a test status), Tasks can emit **results** --- strings written to a file that the Pipeline controller reads. Results are ideal for passing metadata like the Git commit hash from the clone Task to the build Task, so the image gets tagged with the exact commit.

### Image promotion --- same image, different environment

A production-quality pipeline never rebuilds for production. It promotes the *exact image* that passed tests in staging. In OpenShift, the internal registry makes this straightforward: the image lives at a known address, and promoting means simply updating the Deployment in the production namespace to reference that same image digest.

### Cross-namespace deployment and RBAC

When a pipeline deploys to multiple namespaces, the pipeline's ServiceAccount needs permissions in each target namespace. OpenShift creates a `pipeline` ServiceAccount automatically in every project with the Pipelines Operator installed. You grant it the `edit` ClusterRole in the staging and production projects via RoleBindings.

## Step-by-Step

### Step 1: Create the projects

You need three OpenShift projects: one for the pipeline definitions, one for staging, and one for production. This separation mirrors real-world environments where CI infrastructure, staging workloads, and production workloads live in distinct namespaces with different RBAC policies.

```bash
oc new-project cicd-pipelines \
  --display-name="CI/CD Pipelines" \
  --description="Pipeline definitions and runs"

oc new-project cicd-staging \
  --display-name="Staging Environment" \
  --description="Staging deployment target"

oc new-project cicd-production \
  --display-name="Production Environment" \
  --description="Production deployment target"
```

Switch back to the pipelines project for the remaining steps:

```bash
oc project cicd-pipelines
```

> **Tip:** You can also run `scripts/setup.sh` to perform all setup steps at once.

### Step 2: Set up cross-namespace RBAC

The pipeline runs in `cicd-pipelines` but deploys to `cicd-staging` and `cicd-production`. The `pipeline` ServiceAccount needs the `edit` ClusterRole in both target namespaces. You also need `system:image-puller` so the production namespace can pull images built in staging.

```bash
oc apply -f manifests/rbac.yaml
```

Verify the RoleBindings:

```bash
oc get rolebinding pipeline-deploy-staging -n cicd-staging
oc get rolebinding pipeline-deploy-production -n cicd-production
oc get rolebinding pipeline-image-puller -n cicd-staging
```

Expected output:

```
NAME                      ROLE                               AGE
pipeline-deploy-staging   ClusterRole/edit                   5s

NAME                         ROLE                               AGE
pipeline-deploy-production   ClusterRole/edit                   5s

NAME                     ROLE                                  AGE
pipeline-image-puller    ClusterRole/system:image-puller       5s
```

**Why three separate projects?** In Kubernetes you might deploy everything to a single namespace during development. OpenShift encourages project-per-environment because projects carry default RBAC, resource quotas, and network policies. This mirrors how production clusters are organized --- the pipeline cannot accidentally modify production resources unless you explicitly grant it access.

### Step 3: Create the shared workspace PVC

The PVC provides persistent storage that all Tasks share. When the clone Task writes source code to this volume, the build and test Tasks can read it.

```bash
oc apply -f manifests/workspace-pvc.yaml
```

```bash
oc get pvc pipeline-workspace-pvc
```

Expected output:

```
NAME                     STATUS   VOLUME    CAPACITY   ACCESS MODES   STORAGECLASS   AGE
pipeline-workspace-pvc   Bound    pv0001    1Gi        RWO                           3s
```

> **Note on CRC:** CRC provides a default StorageClass with `ReadWriteOnce` access. This means Tasks sharing the PVC will run sequentially. In a production cluster with `ReadWriteMany` storage (e.g., NFS, CephFS via ODF), parallel Tasks can access the workspace concurrently.

### Step 4: Create the clone Task

This Task clones a Git repository into the shared workspace and emits the commit SHA as a result.

```bash
oc apply -f manifests/task-clone.yaml
```

Examine the Task:

```bash
tkn task describe git-clone-source
```

Expected output:

```
Name:        git-clone-source
Namespace:   cicd-pipelines

Input Resources: none
Output Resources: none

Params:
 NAME          TYPE     DESCRIPTION                                DEFAULT VALUE
 repo-url      string   The Git repository URL to clone             ---
 revision      string   The Git revision to check out               main

Results:
 NAME          DESCRIPTION
 commit-sha    The precise commit SHA that was checked out

Workspaces:
 NAME     DESCRIPTION
 source   Workspace where the source code will be cloned

Steps:
 NAME    IMAGE
 clone   registry.redhat.io/openshift-pipelines/...
```

Key design decisions in this Task:
- **`--depth 1`** keeps the clone fast by fetching only the latest commit.
- The **commit SHA result** is emitted so downstream Tasks can tag the image with the exact commit, enabling traceability from a running container back to the source.
- **Resource limits** are set --- Level 2 pipelines should always include them to prevent a runaway clone from consuming cluster resources.

### Step 5: Create the build Task

This Task builds a container image using Buildah (not Docker --- OpenShift uses Podman/Buildah) and pushes it to the internal registry.

```bash
oc apply -f manifests/task-build.yaml
```

```bash
tkn task describe build-image
```

Why Buildah instead of Docker?
- OpenShift does not run a Docker daemon. The container runtime is CRI-O.
- Buildah builds OCI-compliant images without a daemon, which is more secure (no privileged Docker socket).
- The `--storage-driver=vfs` flag is needed because the build runs in a non-privileged container. VFS is slower than overlay but does not require elevated kernel capabilities.
- In L1-M3.2, you learned about BuildConfigs and S2I. Here we use Buildah directly in a Task for maximum flexibility --- you could swap in S2I, Kaniko, or any other builder by changing the Task.

### Step 6: Create the test Task

This Task runs the application's test suite against the cloned source code.

```bash
oc apply -f manifests/task-test.yaml
```

```bash
tkn task describe run-tests
```

The test Task runs in parallel with the build Task (look at the Pipeline definition in the next step --- both have `runAfter: [clone]` but neither depends on the other). This is a common pattern: build and test are independent, and both must pass before deployment proceeds.

### Step 7: Create the deploy Task

This Task deploys the application to a target namespace by creating or updating a Deployment, Service, and Route.

```bash
oc apply -f manifests/task-deploy.yaml
```

```bash
tkn task describe deploy-app
```

The deploy Task is reusable --- the same Task deploys to staging and production, with only the `target-namespace` parameter changing. This is idiomatic Tekton: write generic Tasks, parameterize them, and compose them in Pipelines.

### Step 8: Create the Pipeline

Now connect all four Tasks into a Pipeline with the correct execution order:

```bash
oc apply -f manifests/pipeline.yaml
```

Visualize the Pipeline:

```bash
tkn pipeline describe build-test-deploy
```

Expected output:

```
Name:        build-test-deploy
Namespace:   cicd-pipelines

Params:
 NAME                    TYPE     DESCRIPTION                    DEFAULT VALUE
 git-url                 string   Git repository URL             ---
 git-revision            string   Git branch, tag, or commit     main
 app-name                string   Application name               pipeline-demo-app
 staging-namespace       string   Namespace for staging           ---
 production-namespace    string   Namespace for production        ---

Workspaces:
 NAME                DESCRIPTION
 shared-workspace    Shared workspace backed by a PVC

Tasks:
 NAME                TASKREF             RUNAFTER
 clone               git-clone-source    ---
 build               build-image         clone
 test                run-tests           clone
 deploy-staging      deploy-app          build, test
 deploy-production   deploy-app          deploy-staging
```

The execution DAG looks like this:

```
                    clone
                   /     \
                build    test
                   \     /
              deploy-staging
                    |
            deploy-production
```

- **clone** runs first.
- **build** and **test** run in parallel after clone completes (both have `runAfter: [clone]`).
- **deploy-staging** waits for both build and test to succeed (`runAfter: [build, test]`).
- **deploy-production** runs only after staging deployment succeeds.

### Step 9: Run the Pipeline

Create a PipelineRun to execute the pipeline. The manifest uses `generateName` (note the trailing dash), so `oc create` generates a unique name for each run.

```bash
oc create -f manifests/pipelinerun.yaml
```

Expected output:

```
pipelinerun.tekton.dev/build-test-deploy-run-xk7r2 created
```

### Step 10: Monitor the Pipeline execution

Watch the PipelineRun progress in real time:

```bash
# Using tkn CLI (recommended)
tkn pipelinerun logs -f --last

# Or using oc
oc get pipelinerun -w
```

Expected output (tkn logs):

```
[clone : clone] Cloning https://github.com/sclorg/nodejs-ex.git at revision master...
[clone : clone] Cloned commit: a1b2c3d4e5f6...
[clone : clone] --- Repository contents ---
[clone : clone] total 48
[clone : clone] -rw-r--r--  1 root root  1234 ... package.json
[clone : clone] -rw-r--r--  1 root root   567 ... server.js
...

[build : build-and-push] Building image ...
[build : build-and-push] STEP 1: FROM registry.access.redhat.com/ubi9/nodejs-18:latest
...
[build : build-and-push] Image built and pushed successfully

[test : run-tests] === Installing dependencies ===
[test : run-tests] === Running tests ===
[test : run-tests] All tests PASSED

[deploy-staging : deploy] Deploying pipeline-demo-app to namespace cicd-staging...
[deploy-staging : deploy] Creating new deployment...
[deploy-staging : deploy] Waiting for rollout to complete...
[deploy-staging : deploy] Deployment complete. Application URL: http://pipeline-demo-app-cicd-staging.apps-crc.testing

[deploy-production : deploy] Deploying pipeline-demo-app to namespace cicd-production...
[deploy-production : deploy] Deployment complete. Application URL: http://pipeline-demo-app-cicd-production.apps-crc.testing
```

You can also check the status with:

```bash
tkn pipelinerun describe --last
```

Expected output:

```
Name:           build-test-deploy-run-xk7r2
Namespace:      cicd-pipelines
Pipeline Ref:   build-test-deploy
Status:         Succeeded
Duration:       3m45s

Params:
 NAME                    VALUE
 git-url                 https://github.com/sclorg/nodejs-ex.git
 git-revision            master
 app-name                pipeline-demo-app
 staging-namespace       cicd-staging
 production-namespace    cicd-production

Taskruns:
 NAME                                    TASK               STATUS      DURATION
 build-test-deploy-run-xk7r2-clone       clone              Succeeded   15s
 build-test-deploy-run-xk7r2-build       build              Succeeded   2m10s
 build-test-deploy-run-xk7r2-test        test               Succeeded   45s
 build-test-deploy-run-xk7r2-deploy-st   deploy-staging     Succeeded   20s
 build-test-deploy-run-xk7r2-deploy-pr   deploy-production  Succeeded   15s
```

### Step 11: Verify the deployments

Check that the application is running in both environments:

```bash
# Staging
oc get deployment,svc,route -n cicd-staging
```

Expected output:

```
NAME                                READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/pipeline-demo-app   1/1     1            1           2m

NAME                        TYPE        CLUSTER-IP     PORT(S)    AGE
service/pipeline-demo-app   ClusterIP   172.30.x.x     8080/TCP   2m

NAME                                    HOST/PORT                                           ADMITTED
route.route.openshift.io/pipeline-...   pipeline-demo-app-cicd-staging.apps-crc.testing     True
```

```bash
# Production
oc get deployment,svc,route -n cicd-production
```

Verify both environments serve the same application:

```bash
STAGING_URL=$(oc get route pipeline-demo-app -n cicd-staging -o jsonpath='{.spec.host}')
PROD_URL=$(oc get route pipeline-demo-app -n cicd-production -o jsonpath='{.spec.host}')

echo "Staging:    http://${STAGING_URL}"
echo "Production: http://${PROD_URL}"

curl -s "http://${STAGING_URL}" | head -5
curl -s "http://${PROD_URL}" | head -5
```

### Step 12: Re-run the Pipeline with different parameters

One of the strengths of Tekton is that Pipelines are parameterized and reusable. Start a new run with `tkn`:

```bash
tkn pipeline start build-test-deploy \
  --param git-url=https://github.com/sclorg/nodejs-ex.git \
  --param git-revision=master \
  --param app-name=pipeline-demo-app \
  --param staging-namespace=cicd-staging \
  --param production-namespace=cicd-production \
  --workspace name=shared-workspace,claimName=pipeline-workspace-pvc \
  --showlog
```

This command creates a new PipelineRun and streams logs in one step. The `--showlog` flag is the equivalent of `tkn pipelinerun logs -f`.

### Step 13: Explore in the Web Console

Open the OpenShift Web Console and switch to the **Developer** perspective:

1. Navigate to **Pipelines** in the left sidebar.
2. Select the `cicd-pipelines` project.
3. Click on the `build-test-deploy` Pipeline to see its visual DAG.
4. Click on a PipelineRun to see the status of each Task, logs, and duration.
5. Switch to the **Topology** view in the `cicd-staging` and `cicd-production` projects to see the deployed applications.

The Web Console gives you a visual pipeline editor and run history that you do not get in vanilla Kubernetes with Tekton alone.

## Verification

Run these commands to confirm everything is working:

```bash
# 1. Pipeline exists
tkn pipeline list -n cicd-pipelines
# Expected: build-test-deploy listed with status

# 2. All Tasks exist
tkn task list -n cicd-pipelines
# Expected: git-clone-source, build-image, run-tests, deploy-app

# 3. PipelineRun completed
tkn pipelinerun list -n cicd-pipelines
# Expected: at least one run with STATUS "Succeeded"

# 4. Staging deployment is running
oc get pods -n cicd-staging
# Expected: pipeline-demo-app pod in Running state

# 5. Production deployment is running
oc get pods -n cicd-production
# Expected: pipeline-demo-app pod in Running state

# 6. Both routes respond
curl -s -o /dev/null -w "%{http_code}" \
  "http://$(oc get route pipeline-demo-app -n cicd-staging -o jsonpath='{.spec.host}')"
# Expected: 200

curl -s -o /dev/null -w "%{http_code}" \
  "http://$(oc get route pipeline-demo-app -n cicd-production -o jsonpath='{.spec.host}')"
# Expected: 200
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Pipeline engine | Install Tekton yourself (or use external CI) | OpenShift Pipelines Operator pre-packaged |
| Pipeline ServiceAccount | Create and configure manually | `pipeline` SA auto-created per project |
| Container builds | Need Docker daemon, Kaniko, or external builder | Buildah built in, no daemon required |
| Image registry | External (Docker Hub, ECR, GCR) | Internal registry at `image-registry.openshift-image-registry.svc:5000` |
| Cross-namespace deploy | `kubectl` with kubeconfig/RBAC | `oc` with project RBAC + `system:image-puller` |
| Pipeline visualization | Install Tekton Dashboard separately | Built into the OpenShift Web Console |
| Build security | Varies --- Docker socket is privileged | Buildah runs unprivileged, SCC-compliant |
| Image promotion | Push/pull from external registry | Tag within internal registry, same cluster |
| Pipeline triggers | Install Tekton Triggers separately | Included with OpenShift Pipelines Operator |
| Namespace isolation | Manual NetworkPolicy setup | Projects with default isolation and RBAC |

## Key Takeaways

- **Tasks are reusable building blocks.** The same `deploy-app` Task deploys to both staging and production --- only the parameters differ. Design Tasks to be generic and compose them in Pipelines.
- **Workspaces backed by PVCs pass data between Tasks.** Unlike CI systems that use artifact stores, Tekton uses Kubernetes-native persistent storage. This keeps everything within the cluster and under K8s RBAC.
- **Build and test can run in parallel.** The `runAfter` field creates a DAG, not a linear sequence. Exploiting parallelism reduces pipeline duration significantly in real-world pipelines with many test stages.
- **Cross-namespace deployment requires explicit RBAC.** OpenShift's project model enforces isolation by default. You must grant the pipeline ServiceAccount `edit` access in each target namespace --- this is a feature, not a limitation, because it makes your security posture auditable.
- **Image promotion means reusing the exact image, not rebuilding.** The production deployment references the same image SHA that was tested in staging. This guarantees that what you tested is what you deploy.

## Troubleshooting

### PipelineRun stuck in "Running" state

Check the TaskRun Pods for errors:

```bash
tkn pipelinerun describe --last
oc get pods -n cicd-pipelines
oc logs <pod-name> -c step-clone   # or step-build, step-run-tests, etc.
```

Common causes:
- **PVC not bound:** The StorageClass may not support dynamic provisioning. Run `oc get pvc` and check for `Pending` status.
- **Image pull errors:** The Tekton Task images may not be available. Check if the OpenShift Pipelines Operator is installed correctly.

### Build Task fails with permission denied

Buildah needs the `SETFCAP` capability. If your cluster has restrictive SCCs, the pipeline ServiceAccount may not have sufficient permissions:

```bash
oc adm policy add-scc-to-user anyuid -z pipeline -n cicd-pipelines
```

> **Warning:** Only grant `anyuid` if strictly necessary. In most clusters with the Pipelines Operator installed, the default `pipelines-scc` SCC is sufficient.

### Deploy Task cannot create resources in target namespace

The RoleBindings may not have been applied:

```bash
oc get rolebinding -n cicd-staging | grep pipeline
oc get rolebinding -n cicd-production | grep pipeline
```

If missing, re-apply:

```bash
oc apply -f manifests/rbac.yaml
```

### Tests fail but you want to proceed

In this lesson, the Pipeline will stop if tests fail. In a real-world scenario, you might want to run tests as a "soft gate" that reports results without blocking. You can achieve this by:

1. Removing the `test` Task from `deploy-staging`'s `runAfter` list.
2. Using a `finally` block to always run cleanup or notification Tasks regardless of test results.

### Pipeline workspace runs out of space

The default PVC is 1Gi. For larger repositories or build artifacts, increase the storage:

```bash
oc patch pvc pipeline-workspace-pvc -p '{"spec":{"resources":{"requests":{"storage":"5Gi"}}}}'
```

> **Note:** Not all StorageClasses support online PVC expansion. You may need to delete and recreate the PVC.

## Cleanup

Remove all resources created in this lesson:

```bash
# Option 1: Run the teardown script
./scripts/teardown.sh

# Option 2: Manual cleanup
# Delete all PipelineRuns first (they reference the PVC)
tkn pipelinerun delete --all -n cicd-pipelines -f

# Delete the projects (this removes everything inside them)
oc delete project cicd-production
oc delete project cicd-staging
oc delete project cicd-pipelines
```

> **Note:** Project deletion is asynchronous. It may take 30-60 seconds for all resources to be fully removed. You can monitor with `oc get projects | grep cicd`.

## Next Steps

In the next lesson, [L2-M1.3 --- OpenShift GitOps (ArgoCD)](../3_openshift_gitops_argocd/README.md), you will install the OpenShift GitOps Operator and learn how ArgoCD continuously reconciles your cluster state with a Git repository. Where Tekton handles the CI side (build and test), ArgoCD handles the CD side (deploy and maintain). In L2-M1.4, you will combine them into a full GitOps CI/CD workflow.
