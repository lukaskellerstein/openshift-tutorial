# OpenShift Tutorial Project

## Purpose

This is a project-based OpenShift tutorial for developers who already know Kubernetes. It contains three tutorial tracks:

- **OpenShift Platform** (`tutorial/`) — 10 lessons, ~8 hours. One application ("ShopInsights") across all lessons. Each lesson adds an OpenShift capability — Routes, Service Mesh, CI/CD, GitOps, monitoring, and serverless.
- **OpenShift AI** (`tutorial_ai/openshift_ai/`) — 66 lessons across 3 levels, ~56-67 hours. Model serving (KServe/vLLM), fine-tuning, RAG, pipelines, agents, evaluation, and governance on the OpenShift AI platform.
- **Red Hat AI Ecosystem** (`tutorial_ai/redhat_ai/`) — 15 lessons across 2 levels, ~11-15 hours. Podman AI Lab, RHEL AI, InstructLab, Granite models, and Validated Patterns.

The Platform track is a prerequisite for the AI tracks. The Red Hat AI Ecosystem track provides context for OpenShift AI but can be taken independently.

## Technical Stack

### Platform Track
- **Platform**: OpenShift 4.x (Red Hat OpenShift Container Platform)
- **Local environment**: OpenShift Local (CRC) — Code Ready Containers
- **Cloud sandbox**: Red Hat Developer Sandbox (free, optional)
- **CLI**: `oc` (primary), `kubectl` (for comparisons)
- **CI/CD**: OpenShift Pipelines (Tekton), OpenShift GitOps (ArgoCD)
- **Service Mesh**: OpenShift Service Mesh (Istio-based)
- **Serverless**: OpenShift Serverless (Knative)
- **Monitoring**: Built-in Prometheus + Grafana stack
- **Logging**: OpenShift Logging (Loki/Elasticsearch + Fluentd/Vector)
- **Container runtime**: Podman (not Docker)

### AI Tracks
- **OpenShift AI**: Red Hat OpenShift AI operator (DataScienceCluster CR)
- **Model serving**: KServe, vLLM, ModelMesh
- **Training**: Training Operator, CodeFlare, Ray
- **Evaluation**: TrustyAI, EvalHub, lm-eval-harness, Garak
- **Pipelines**: Kubeflow Pipelines (DataSciencePipelines)
- **Registry**: Model Registry (governance)
- **Local AI**: Podman AI Lab, RHEL AI, InstructLab
- **Models**: IBM Granite family (Apache 2.0), Gemma
- **Environment**: Red Hat Demo Platform (GPU cluster with admin access)

## Project Layout

```
tutorial/                              # Platform track (flat, 10 lessons)
  shared_app/                          #   ShopInsights application source
    products-service/
    orders-service/
    analytics-service/
    dashboard-ui/
  L01_projects/
  L02_builds_and_images/
  ...
  L10_serverless/
tutorial_ai/
  openshift_ai/                        # OpenShift AI track (3 levels, 66 lessons)
    syllabus.md
    manifests/                         #   Working manifests (KServe, vLLM, etc.)
    level_1/                           #   Foundations: setup, serving, fine-tuning
      M1_platform_setup/
      M2_model_serving/
      ...
    level_2/                           #   Practitioner: RAG, agents, pipelines
    level_3/                           #   Expert: governance, evaluation, production
  redhat_ai/                           # Red Hat AI Ecosystem track (2 levels, 15 lessons)
    syllabus.md
    level_1/                           #   Foundations: Podman AI Lab, RHEL AI, Granite
    level_2/                           #   Practitioner: InstructLab, cross-tier workflows
  README.md                            #   AI tutorial overview and environment setup
k8s_vs_openshift.md                    # Full K8s ↔ OpenShift resource mapping
```

### Platform Track Lessons

Each lesson is a self-contained directory with a flat numbering scheme:
```
LNN_lesson_name/
  README.md             # Lesson guide with explanation, steps, expected output
  manifests/            # YAML manifests (Deployments, Routes, BuildConfigs, etc.)
  scripts/              # Shell scripts for setup, teardown, demos
```

### AI Track Lessons

AI lessons use a three-level structure with modules:
```
level_N/
  M<N>_module_name/
    <N>_lesson_name/
      README.md
      manifests/
      scripts/
      app/              # Optional application code
```

## Environment Setup

### Platform Track — Red Hat Developer Sandbox (recommended)
1. Sign up at sandbox.redhat.com and launch your sandbox
2. Web console → username (top-right) → **Copy login command** → **Display Token**
3. `oc login --token=sha256~XXXXX --server=https://api.sandbox-xxx.openshiftapps.com:6443`

Tokens expire daily. Some lessons (L05, L08, L09, L10) need cluster-admin — use CRC for those.

### Platform Track — OpenShift Local (CRC)
```bash
crc setup
crc start
eval $(crc oc-env)
oc login -u developer -p developer https://api.crc.testing:6443
```

#### Key URLs (CRC)
| Service | URL |
|---------|-----|
| API Server | https://api.crc.testing:6443 |
| Web Console | https://console-openshift-console.apps-crc.testing |
| OAuth | https://oauth-openshift.apps-crc.testing |

#### Default Users (CRC)
- `kubeadmin` / `<password from crc start>` — cluster admin
- `developer` / `developer` — regular user

### AI Track — Red Hat Demo Platform
The OpenShift AI track requires the [Red Hat Demo Platform](https://catalog.demo.redhat.com/) — a pre-configured cluster with GPUs and full admin access. The Developer Sandbox lacks cluster-admin (can't install operators), and CRC has no GPU.

## Key Commands

- `crc setup` — initial CRC setup
- `crc start` — start the local OpenShift cluster
- `crc stop` — stop the cluster (preserves state)
- `crc delete` — remove the cluster entirely
- `oc login` — authenticate to the cluster
- `oc new-project <name>` — create a project (namespace)
- `oc new-app` — deploy an application
- `oc apply -f <manifest.yaml>` — apply YAML (same as kubectl)
- `oc get routes` — list exposed routes
- `oc debug <pod>` — debug a running pod
- `oc adm` — administrative commands

## Rules

Modular instructions are in `.claude/rules/`. They cover:
- `tutorial-structure.md` — three-level layout and file conventions
- `lesson-content.md` — how to write README.md lesson guides
- `manifest-standards.md` — YAML manifest conventions and patterns
- `k8s-to-openshift.md` — how to frame K8s→OpenShift comparisons
