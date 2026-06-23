# OpenShift Tutorial Project

## Purpose

This is a comprehensive, three-level tutorial for OpenShift targeting developers and DevOps engineers who already know Kubernetes. Every lesson starts from a Kubernetes concept the reader knows, then shows the OpenShift equivalent — what it adds, what it restricts, and why.

The tutorial is structured in three progressive levels:
- **Level 1 — Foundations**: Kubernetes → OpenShift. Touch every major platform difference (~20-30 min lessons).
- **Level 2 — Practitioner**: Real-world workflows — CI/CD, operators, service mesh, security (~45-90 min lessons).
- **Level 3 — Expert**: Production operations — multi-cluster, performance, migration, capstones.

The full syllabus lives in `tutorial_syllabus.md` — always consult it for module structure, lesson topics, and time estimates before creating or modifying any lesson.

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
tutorial_syllabus.md                # Master syllabus — the source of truth
tutorial/
  level_1/                          # Level 1: Foundations
    M1_platform_setup/
    M2_projects_users_rbac/
    M3_application_deployment/
    M4_networking_routes/
    M5_storage/
    M6_monitoring_logging/
  level_2/                          # Level 2: Practitioner
    M1_cicd/
    M2_operators/
    M3_service_mesh_serverless/
    M4_advanced_networking/
    M5_security_hardening/
    M6_developer_experience/
  level_3/                          # Level 3: Expert
    M1_cluster_administration/
    M2_multi_cluster/
    M3_performance_troubleshooting/
    M4_advanced_workloads/
    M5_migration_capstones/
```

Each lesson is a self-contained directory:
```
N_lesson_name/
  README.md             # Lesson guide with explanation, steps, expected output
  manifests/            # YAML manifests (Deployments, Routes, BuildConfigs, etc.)
  scripts/              # Shell scripts for setup, teardown, demos
  app/                  # Application source code (if the lesson deploys an app)
  .gitignore            # Ignore temp files, credentials
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
