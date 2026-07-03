# OpenShift Tutorial Project

## Purpose

This is a project-based OpenShift tutorial for developers who already know Kubernetes. One application ("ShopInsights"), ten lessons, ~8 hours. Each lesson adds an OpenShift capability to the same microservices stack — Routes, Service Mesh, CI/CD, GitOps, monitoring, and serverless.

## Technical Stack

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
- **Operator SDK**: for building custom operators (Level 2)

## Project Layout

```
tutorial/
  README.md                        # Tutorial overview
  shared_app/                      # ShopInsights application source code
    products-service/
    orders-service/
    analytics-service/
    dashboard-ui/
  L01_deploy_microservices/
  L02_expose_externally/
  L03_service_mesh/
  L04_builds_and_images/
  L05_projects/
  L06_auth_and_identity/
  L07_monitoring_and_logging/
  L08_cicd_pipeline/
  L09_gitops/
  L10_serverless/
k8s_vs_openshift.md                # Full K8s ↔ OpenShift resource mapping
tutorial_syllabus.md               # Original comprehensive syllabus (reference)
```

Each lesson is a self-contained directory:
```
LNN_lesson_name/
  README.md             # Lesson guide with explanation, steps, expected output
  manifests/            # YAML manifests (Deployments, Routes, BuildConfigs, etc.)
  scripts/              # Shell scripts for setup, teardown, demos
```

## Environment Setup

### OpenShift Local (CRC)
```bash
crc setup
crc start
eval $(crc oc-env)
oc login -u developer -p developer https://api.crc.testing:6443
```

### Key URLs (CRC)
| Service | URL |
|---------|-----|
| API Server | https://api.crc.testing:6443 |
| Web Console | https://console-openshift-console.apps-crc.testing |
| OAuth | https://oauth-openshift.apps-crc.testing |

### Default Users (CRC)
- `kubeadmin` / `<password from crc start>` — cluster admin
- `developer` / `developer` — regular user

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
