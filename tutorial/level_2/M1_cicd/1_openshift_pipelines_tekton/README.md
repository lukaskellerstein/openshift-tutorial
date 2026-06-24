# L2-M1.1 --- OpenShift Pipelines (Tekton)

**Level:** Practitioner
**Duration:** 1 hr

## Overview

In Kubernetes, CI/CD is an external concern -- you pick a tool (Jenkins, GitHub Actions, GitLab CI), run it somewhere, and have it push images and apply manifests to your cluster. OpenShift flips this by offering a built-in, Kubernetes-native CI/CD engine: **OpenShift Pipelines**, which is a curated distribution of the **Tekton** project.

In this lesson you will install the OpenShift Pipelines operator, learn the Tekton object model (Tasks, Pipelines, PipelineRuns, Workspaces), build a real pipeline that clones a Git repo and builds a container image, and set up webhook-based triggers so that a `git push` automatically kicks off a build.

## Prerequisites

- Completed: Level 1 (all modules)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as a user with `cluster-admin` privileges (needed to install the operator)
- `oc` CLI installed and on PATH
- `tkn` CLI installed (optional but recommended --- [install guide](https://github.com/tektoncd/cli/releases))

## K8s Context

In vanilla Kubernetes, there is no built-in CI/CD system. You typically:

1. Run a CI server externally (Jenkins, GitHub Actions, CircleCI).
2. The CI server builds container images and pushes them to a registry.
3. The CI server runs `kubectl apply` or a Helm upgrade to deploy to the cluster.

Kubernetes does not know or care how images are built --- it only consumes them. Some teams install Tekton or Argo Workflows manually, but these are add-ons, not part of the platform.

If you have used Tekton on vanilla Kubernetes before, OpenShift Pipelines will feel familiar. The main differences are operator-managed installation, deeper integration with the OpenShift console, and pre-configured ClusterTasks that work with OpenShift's internal registry and build system.

## Concepts

### Tekton Object Model

Tekton introduces several Kubernetes Custom Resources:

| Resource | Purpose |
|----------|---------|
| **Task** | A sequence of steps that run in a single pod. Each step is a container. |
| **TaskRun** | An execution of a Task --- the actual pod that runs. |
| **Pipeline** | An ordered collection of Tasks with dependency management. |
| **PipelineRun** | An execution of a Pipeline --- creates TaskRuns for each Task. |
| **Workspace** | A shared volume (PVC, ConfigMap, Secret, or emptyDir) passed between Tasks. |

### Tekton Triggers

Triggers allow external events (like a GitHub webhook) to automatically create PipelineRuns:

| Resource | Purpose |
|----------|---------|
| **TriggerBinding** | Extracts fields from an incoming webhook payload and maps them to parameters. |
| **TriggerTemplate** | A template that stamps out a PipelineRun using the extracted parameters. |
| **EventListener** | An HTTP endpoint (Kubernetes Service) that receives webhooks, applies bindings, and invokes templates. |

### How It Fits Together

```
GitHub push webhook
        |
        v
  EventListener (HTTP endpoint exposed via Route)
        |
        v
  TriggerBinding (extracts repo URL, commit SHA from JSON)
        |
        v
  TriggerTemplate (stamps out a PipelineRun)
        |
        v
  PipelineRun --> Pipeline --> Task(s) --> Steps (containers)
```

### Why OpenShift Has This Built In

OpenShift targets enterprise teams that need a fully supported CI/CD platform out of the box. Rather than requiring every team to choose, install, and maintain their own CI tool:

- **Consistency**: every cluster has the same pipeline engine.
- **Security**: pipelines run inside the cluster under OpenShift RBAC and SCCs --- no external CI server needs cluster credentials.
- **Integration**: Tekton resources are first-class Kubernetes objects visible in the Web Console's Developer perspective.
- **Support**: Red Hat supports the operator and bundles Tekton versions tested against each OpenShift release.

### Comparison with Other CI/CD Tools

| Aspect | Jenkins | GitHub Actions | Tekton (OpenShift Pipelines) |
|--------|---------|----------------|------------------------------|
| Where it runs | Separate server (or pod in cluster) | GitHub cloud (or self-hosted runner) | Inside the cluster as K8s pods |
| Pipeline definition | Groovy Jenkinsfile | YAML workflow files | Kubernetes CRDs (YAML) |
| Scaling | Manage Jenkins agents | Managed by GitHub (or self-managed) | Each TaskRun is a pod, scales with cluster |
| State | Jenkins stores state internally | GitHub stores state | Kubernetes API stores state (PipelineRuns) |
| Reuse | Shared libraries | Reusable workflows, marketplace | ClusterTasks, Tekton Hub tasks |
| Cloud-native | Bolt-on (Kubernetes plugin) | External to cluster | Kubernetes-native (CRDs, pods, PVCs) |

## Step-by-Step

### Step 1: Install the OpenShift Pipelines Operator

The operator installs Tekton components (pipelines controller, triggers controller, dashboard integration) and keeps them updated.

**Option A: Via the Web Console (recommended for first-time install)**

1. Log in to the Web Console as `kubeadmin`.
2. Navigate to **Operators > OperatorHub**.
3. Search for **"Red Hat OpenShift Pipelines"**.
4. Click **Install**. Accept the defaults (All namespaces, Automatic approval).
5. Wait for the status to show **Succeeded**.

**Option B: Via the CLI**

```bash
# Log in as cluster-admin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Install the operator subscription
oc apply -f manifests/subscription-pipelines-operator.yaml
```

Wait for the operator to install (2-3 minutes):

```bash
# Watch the CSV status
oc get csv -n openshift-operators -w

# Expected output (after installation completes):
# NAME                                      DISPLAY                       VERSION   PHASE
# openshift-pipelines-operator-rh.v1.14.x   Red Hat OpenShift Pipelines   1.14.x    Succeeded
```

**Verify the installation:**

```bash
# Check that the Tekton pods are running
oc get pods -n openshift-pipelines

# Expected output:
# NAME                                                 READY   STATUS    RESTARTS   AGE
# tekton-operator-proxy-webhook-...                    1/1     Running   0          2m
# tekton-pipelines-controller-...                      1/1     Running   0          2m
# tekton-pipelines-webhook-...                         1/1     Running   0          2m
# tekton-triggers-controller-...                       1/1     Running   0          2m
# tekton-triggers-webhook-...                          1/1     Running   0          2m
# tkn-cli-serve-...                                    1/1     Running   0          2m

# Verify the Tekton CRDs are registered
oc api-resources | grep tekton

# Expected output (abbreviated):
# tasks                          tekton.dev/v1                  true    Task
# taskruns                       tekton.dev/v1                  true    TaskRun
# pipelines                      tekton.dev/v1                  true    Pipeline
# pipelineruns                   tekton.dev/v1                  true    PipelineRun
# triggerbindings                triggers.tekton.dev/v1beta1    true    TriggerBinding
# triggertemplates               triggers.tekton.dev/v1beta1    true    TriggerTemplate
# eventlisteners                 triggers.tekton.dev/v1beta1    true    EventListener
```

> **Note:** You only need to install the operator once per cluster. If you are using the Red Hat Developer Sandbox, the operator is already installed.

### Step 2: Create a Project

```bash
oc new-project pipelines-tutorial \
  --display-name="Tekton Pipelines Tutorial" \
  --description="L2-M1.1: OpenShift Pipelines (Tekton)"
```

Or use the setup script:

```bash
./scripts/setup.sh
```

### Step 3: Create and Run a Simple Task

Start with the simplest possible Task to understand the structure before building a full pipeline.

**Apply the greeting Task:**

```bash
oc apply -f manifests/task-greeting.yaml

# Expected output:
# task.tekton.dev/greeting created
```

**Inspect the Task:**

```bash
oc get tasks

# Expected output:
# NAME       AGE
# greeting   5s

# Describe it to see params and steps
oc describe task greeting
```

If you have the `tkn` CLI:

```bash
tkn task describe greeting

# Expected output:
# Name:        greeting
# Namespace:   pipelines-tutorial
#
# Params:
#  NAME       TYPE     DESCRIPTION                      DEFAULT VALUE
#  message    string   The greeting message to display   Hello from Tekton!
#
# Steps:
#  greet
```

**Run the Task:**

```bash
# Create a TaskRun from the manifest
oc create -f manifests/taskrun-greeting.yaml

# Expected output:
# taskrun.tekton.dev/greeting-run-xxxxx created
```

> **Note:** We use `oc create` (not `oc apply`) because the manifest uses `generateName`, which creates a uniquely named resource each time.

Or run it directly with `tkn`:

```bash
tkn task start greeting \
  --param message="Hello from the tkn CLI!" \
  --showlog

# Expected output:
# TaskRun started: greeting-run-xxxxx
# Waiting for logs to be available...
# [greet] =========================================
# [greet] Hello from the tkn CLI!
# [greet] Task executed at: Mon Jun 24 12:00:00 UTC 2026
# [greet] Running on node: crc-xxxxx
# [greet] =========================================
```

**Check the TaskRun status:**

```bash
oc get taskruns

# Expected output:
# NAME                  SUCCEEDED   REASON      STARTTIME   COMPLETIONTIME
# greeting-run-xxxxx    True        Succeeded   1m          30s

# View the logs
oc logs greeting-run-xxxxx-pod

# Or with tkn:
tkn taskrun logs greeting-run-xxxxx
```

**What just happened?**

When you created the TaskRun, Tekton's controller:
1. Created a Pod with one container per step (in this case, one container for the `greet` step).
2. Injected the parameter value into the step's script.
3. Ran the container to completion.
4. Recorded the status on the TaskRun CR.

This is fundamentally different from Jenkins (which runs steps in a long-lived agent) or GitHub Actions (which runs steps in a VM). Every Tekton step is an ephemeral container --- no persistent agent to manage.

### Step 4: Create a Task with Workspaces

Real pipelines need to pass data between Tasks (clone code in one Task, build it in the next). Tekton uses **Workspaces** for this --- a shared volume mounted into the pods.

**Apply the clone-and-list Task:**

```bash
oc apply -f manifests/task-clone-and-list.yaml

# Expected output:
# task.tekton.dev/clone-and-list created
```

**Run it with a workspace:**

```bash
tkn task start clone-and-list \
  --param repo-url=https://github.com/sclorg/nodejs-ex.git \
  --param revision=master \
  --workspace name=source,volumeClaimTemplateFile=- \
  --showlog <<'EOF'
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 500Mi
EOF

# Expected output:
# TaskRun started: clone-and-list-run-xxxxx
# Waiting for logs to be available...
# [clone] Cloning https://github.com/sclorg/nodejs-ex.git @ master...
# [clone] Clone complete.
# [list-files] Repository contents:
# [list-files] ---
# [list-files] total XX
# [list-files] -rw-r--r-- 1 1000 root  XXX ... package.json
# [list-files] -rw-r--r-- 1 1000 root  XXX ... server.js
# [list-files] ...
# [list-files] ---
# [list-files] Total files: XX
```

**Key observation:** the `clone` step wrote to the workspace, and the `list-files` step read from it. Both steps ran sequentially in the same pod, sharing the workspace volume.

### Step 5: Create the Build Image Task

**Apply the build-image Task:**

```bash
oc apply -f manifests/task-build-image.yaml

# Expected output:
# task.tekton.dev/build-image created
```

This Task uses **Buildah** to build a container image without Docker. It writes two **results** (image-digest and image-url) that downstream tasks or the pipeline can consume.

> **Important:** This Task requires the `SETFCAP` capability in its security context. The `pipeline` ServiceAccount (created automatically by the Pipelines operator) has the necessary SCC permissions. If you see permission errors, ensure you are running in a project where the `pipeline` SA exists.

### Step 6: Wire Tasks into a Pipeline

Now we combine the clone and build Tasks into a Pipeline.

**Apply the Pipeline:**

```bash
oc apply -f manifests/pipeline-clone-build.yaml

# Expected output:
# pipeline.tekton.dev/clone-and-build created
```

**Inspect the Pipeline:**

```bash
oc describe pipeline clone-and-build

# Or with tkn:
tkn pipeline describe clone-and-build

# Expected output:
# Name:        clone-and-build
# Namespace:   pipelines-tutorial
#
# Params:
#  NAME          TYPE     DESCRIPTION                      DEFAULT VALUE
#  repo-url      string   The Git repository URL           ---
#  revision      string   The Git branch or tag             main
#  image-name    string   The target image name             ---
#  image-tag     string   The target image tag              latest
#
# Workspaces:
#  NAME                DESCRIPTION
#  shared-workspace    Workspace shared between clone and build tasks
#
# Tasks:
#  NAME            TASKREF          RUNAFTER
#  fetch-source    clone-and-list   ---
#  build-image     build-image      fetch-source
```

Notice the `runAfter` relationship: `build-image` waits for `fetch-source` to complete, because it needs the cloned source code in the shared workspace.

### Step 7: Run the Pipeline

**Option A: From the manifest**

```bash
oc create -f manifests/pipelinerun-clone-build.yaml

# Expected output:
# pipelinerun.tekton.dev/clone-and-build-run-xxxxx created
```

**Option B: With the `tkn` CLI**

```bash
tkn pipeline start clone-and-build \
  --param repo-url=https://github.com/sclorg/nodejs-ex.git \
  --param revision=master \
  --param image-name=image-registry.openshift-image-registry.svc:5000/pipelines-tutorial/nodejs-ex \
  --param image-tag=latest \
  --workspace name=shared-workspace,volumeClaimTemplateFile=- \
  --showlog <<'EOF'
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF
```

**Monitor the PipelineRun:**

```bash
# List PipelineRuns
oc get pipelineruns

# Expected output:
# NAME                         SUCCEEDED   REASON    STARTTIME   COMPLETIONTIME
# clone-and-build-run-xxxxx    Unknown     Running   10s

# Watch logs in real-time
tkn pipelinerun logs clone-and-build-run-xxxxx -f

# Or list all TaskRuns spawned by the PipelineRun
oc get taskruns -l tekton.dev/pipelineRun=clone-and-build-run-xxxxx

# Expected output:
# NAME                                        SUCCEEDED   REASON      STARTTIME   COMPLETIONTIME
# clone-and-build-run-xxxxx-fetch-source-...  True        Succeeded   2m          1m
# clone-and-build-run-xxxxx-build-image-...   Unknown     Running     30s
```

**View in the Web Console:**

1. Switch to the **Developer** perspective.
2. Navigate to **Pipelines** in the left sidebar.
3. Click on **clone-and-build** to see the pipeline visualization.
4. Click on the PipelineRun to see task status, logs, and results.

The console shows a graphical representation of the pipeline with each task as a node, colored green (succeeded), blue (running), or red (failed).

### Step 8: Set Up Webhook Triggers

Now let us automate pipeline execution so that a `git push` automatically triggers a build.

**Apply the Trigger resources:**

```bash
# Apply all trigger components
oc apply -f manifests/trigger-binding.yaml
oc apply -f manifests/trigger-template.yaml
oc apply -f manifests/event-listener.yaml

# Expected output:
# triggerbinding.triggers.tekton.dev/github-push-binding created
# triggertemplate.triggers.tekton.dev/github-push-template created
# eventlistener.triggers.tekton.dev/github-push-listener created
```

Wait for the EventListener pod and service to be created:

```bash
# The EventListener controller automatically creates a pod and service
oc get pods -l eventlistener=github-push-listener

# Expected output (after ~30 seconds):
# NAME                                        READY   STATUS    RESTARTS   AGE
# el-github-push-listener-xxxxxxxxxx-xxxxx    1/1     Running   0          30s

oc get svc el-github-push-listener

# Expected output:
# NAME                      TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)
# el-github-push-listener   ClusterIP   172.30.xxx.xxx   <none>        8080/TCP,...
```

**Expose the EventListener via a Route:**

```bash
oc apply -f manifests/event-listener-route.yaml

# Expected output:
# route.route.openshift.io/github-webhook created

# Get the webhook URL
oc get route github-webhook -o jsonpath='{.spec.host}'

# Expected output:
# github-webhook-pipelines-tutorial.apps-crc.testing
```

The full webhook URL is:
```
https://github-webhook-pipelines-tutorial.apps-crc.testing
```

**Test the trigger locally (simulate a GitHub push event):**

```bash
WEBHOOK_URL=$(oc get route github-webhook -o jsonpath='https://{.spec.host}')

curl -k -X POST "${WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d '{
    "repository": {
      "clone_url": "https://github.com/sclorg/nodejs-ex.git"
    },
    "head_commit": {
      "id": "master",
      "message": "Test webhook trigger"
    }
  }'

# Expected output:
# {"eventListener":"github-push-listener","namespace":"pipelines-tutorial","eventListenerUID":"...","eventID":"..."}
```

**Verify a PipelineRun was created:**

```bash
oc get pipelineruns

# Expected output (a new run should appear):
# NAME                             SUCCEEDED   REASON    STARTTIME   COMPLETIONTIME
# clone-and-build-run-xxxxx        True        ...       5m          3m
# webhook-triggered-run-xxxxx      Unknown     Running   5s
```

**To configure a real GitHub webhook:**

1. Go to your GitHub repository > **Settings** > **Webhooks** > **Add webhook**.
2. Set **Payload URL** to `https://github-webhook-pipelines-tutorial.apps-crc.testing`.
3. Set **Content type** to `application/json`.
4. Select **Just the push event**.
5. Click **Add webhook**.

> **Note:** For CRC, the Route is only accessible locally. For a real GitHub webhook you need the cluster to be reachable from the internet (use Developer Sandbox or a cloud-hosted cluster).

## Verification

Run through this checklist to confirm everything is working:

```bash
# 1. Operator is installed and running
oc get csv -n openshift-operators | grep pipelines

# 2. All custom Tasks are created
oc get tasks -n pipelines-tutorial
# Expected: greeting, clone-and-list, build-image

# 3. Pipeline exists
oc get pipelines -n pipelines-tutorial
# Expected: clone-and-build

# 4. At least one successful PipelineRun
oc get pipelineruns -n pipelines-tutorial
# Expected: at least one with SUCCEEDED=True

# 5. Trigger components are in place
oc get eventlistener,triggerbinding,triggertemplate -n pipelines-tutorial
# Expected: github-push-listener, github-push-binding, github-push-template

# 6. Webhook Route is accessible
curl -sk "$(oc get route github-webhook -o jsonpath='https://{.spec.host}')" -o /dev/null -w "%{http_code}"
# Expected: 200 or 202 (the EventListener is listening)

# 7. Check in the Web Console
# Developer perspective > Pipelines > clone-and-build
# You should see the pipeline visualization and run history
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| CI/CD engine | None built-in; install Tekton, Argo, or use external CI | OpenShift Pipelines (Tekton) installed via operator |
| Installation | `kubectl apply` Tekton release YAMLs manually | One-click operator install from OperatorHub |
| Updates | Manual; track upstream Tekton releases | Operator manages upgrades automatically |
| Dashboard | Tekton Dashboard (separate install) | Integrated into OpenShift Web Console (Developer perspective) |
| ClusterTasks | Install from Tekton Hub manually | Pre-installed ClusterTasks for common operations (git-clone, buildah, s2i, openshift-client) |
| Image builds | Need Kaniko or DinD (Docker-in-Docker) | Buildah runs rootless; integrates with OpenShift internal registry |
| Webhook exposure | Create Ingress + cert manually | Create a Route (built-in TLS, as you learned in L1-M4.2) |
| Service accounts | Create and configure manually | `pipeline` SA created automatically with appropriate SCCs |
| Security | Configure RBAC and PSA yourself | SCCs restrict pipeline pods by default; operator configures least-privilege |
| Catalog | Tekton Hub (community) | Tekton Hub + Red Hat certified tasks |

## Key Takeaways

- **Tekton is Kubernetes-native CI/CD**: every pipeline concept (Task, Pipeline, PipelineRun) is a Kubernetes Custom Resource. There is no separate CI server to manage --- the cluster IS the CI server.
- **Workspaces are the glue**: Tasks pass data via shared volumes (PVCs). The PipelineRun provisions the storage, and Tekton mounts it into each Task pod. This is different from Jenkins (where the agent's filesystem is shared) or GitHub Actions (where artifacts are uploaded/downloaded).
- **Triggers close the loop**: TriggerBindings, TriggerTemplates, and EventListeners let you wire external events (webhooks) directly to PipelineRuns --- no middleware needed. The EventListener is just a pod with an HTTP endpoint behind a Route.
- **OpenShift makes it turnkey**: the operator installs everything, the Web Console visualizes pipelines, pre-built ClusterTasks handle common operations (git-clone, buildah, s2i), and the `pipeline` ServiceAccount is pre-configured with the right permissions.
- **Each step is a container**: unlike Jenkins (persistent agents) or GitHub Actions (persistent VMs), Tekton steps are ephemeral containers. This means perfect isolation, but also means you must explicitly share state via Workspaces.

## Troubleshooting

### TaskRun pod stuck in Pending

```bash
oc describe taskrun <name>
oc describe pod <taskrun-pod>
```

Common causes:
- **Insufficient resources**: CRC has limited CPU/memory. Check `oc describe node` for resource pressure.
- **PVC not provisioned**: If the workspace uses a PVC, ensure the StorageClass exists and has capacity.
- **Image pull errors**: Red Hat registry images (`registry.redhat.io`) require authentication. The CRC cluster is pre-configured, but Developer Sandbox may need a pull secret.

### Permission denied errors in build tasks

The `build-image` Task requires capabilities that the default `restricted` SCC does not allow. The Pipelines operator creates a `pipeline` ServiceAccount with `pipelines-scc` that grants the necessary permissions.

```bash
# Verify the pipeline SA exists
oc get sa pipeline -n pipelines-tutorial

# Check its SCC
oc get scc pipelines-scc -o yaml 2>/dev/null || echo "Using default operator SCC configuration"
```

If you see "unable to validate against any security context constraint," ensure the PipelineRun uses the `pipeline` ServiceAccount (this is the default).

### EventListener not receiving webhooks

```bash
# Check EventListener pod logs
oc logs -l eventlistener=github-push-listener

# Verify the Route is working
curl -vk "$(oc get route github-webhook -o jsonpath='https://{.spec.host}')"

# Check that the TriggerBinding field paths match the webhook payload structure
oc get triggerbinding github-push-binding -o yaml
```

Common issues:
- **Wrong payload structure**: the TriggerBinding paths (e.g., `$(body.repository.clone_url)`) must match the webhook provider's JSON structure exactly. GitHub, GitLab, and Bitbucket all have different payload formats.
- **Route not accessible**: on CRC, the Route is only reachable from the host machine. For real webhooks, use a cloud cluster.
- **Missing interceptors**: for production use, add a GitHub interceptor to validate webhook signatures and filter events.

### PipelineRun fails at build-image step on CRC

CRC has limited resources. The build step needs memory for Buildah:

```bash
# Check node resource availability
oc describe node crc | grep -A 5 "Allocated resources"

# If resources are tight, increase CRC resources
crc stop
crc config set cpus 6
crc config set memory 16384
crc start
```

## Cleanup

```bash
# Delete all tutorial resources
oc delete pipelinerun -l tutorial-level=2,tutorial-module=M1 -n pipelines-tutorial
oc delete taskrun -l tutorial-level=2,tutorial-module=M1 -n pipelines-tutorial
oc delete pipeline -l tutorial-level=2,tutorial-module=M1 -n pipelines-tutorial
oc delete task -l tutorial-level=2,tutorial-module=M1 -n pipelines-tutorial
oc delete eventlistener -l tutorial-level=2,tutorial-module=M1 -n pipelines-tutorial
oc delete triggertemplate -l tutorial-level=2,tutorial-module=M1 -n pipelines-tutorial
oc delete triggerbinding -l tutorial-level=2,tutorial-module=M1 -n pipelines-tutorial
oc delete route -l tutorial-level=2,tutorial-module=M1 -n pipelines-tutorial

# Clean up PVCs created by PipelineRuns
oc delete pvc -l tekton.dev/pipeline=clone-and-build -n pipelines-tutorial

# Delete the project
oc delete project pipelines-tutorial

# Or use the teardown script:
./scripts/teardown.sh
```

> **Note:** The OpenShift Pipelines operator remains installed cluster-wide. Uninstall it from the Web Console (Operators > Installed Operators) only if you no longer need it.

## Next Steps

In **L2-M1.2 --- Pipeline: Build, Test, Deploy**, you will build an end-to-end pipeline that goes beyond cloning and building. You will add testing stages, deploy to a staging environment, run integration tests, and promote the image to production --- a realistic CI/CD workflow using everything you learned in this lesson.
