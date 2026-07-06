# OpenShift Platform Tutorial: Syllabus

## Philosophy

This tutorial is a single, flat track of 13 progressive lessons. One application — **ShopInsights** — runs through all lessons. Each lesson adds an OpenShift capability on top of the previous ones.

The reader already knows Kubernetes. Every lesson starts from the K8s concept they know and bridges to the OpenShift equivalent. The goal is not to teach Kubernetes — it's to show what OpenShift adds, changes, or simplifies.

## Target Audience

- Developers and platform engineers who know **Kubernetes** (Deployments, Services, Ingress, RBAC, Helm)
- Familiar with **containerization** (Docker/Podman)
- Have existing experience with tools like **Traefik**, **Keycloak**, and vanilla K8s clusters
- Want to understand OpenShift — not every feature, but the ones that matter for running real microservices

## Technical Stack

- **Platform**: OpenShift 4.x (Red Hat OpenShift Container Platform)
- **CLI**: `oc` (primary), `kubectl` (for K8s comparisons)
- **CI/CD**: OpenShift Pipelines (Tekton), GitHub Actions
- **GitOps**: OpenShift GitOps (ArgoCD)
- **Service Mesh**: OpenShift Service Mesh (Istio ambient mode)
- **Serverless**: OpenShift Serverless (Knative)
- **Monitoring**: Built-in Prometheus + Grafana stack, Loki for logs
- **Auth**: OpenShift OAuth (cluster), Keycloak/RHSSO (application)
- **Container runtime**: Podman (not Docker)

## The Application

**ShopInsights** is an e-commerce analytics platform:

- **Products Service** — product catalog (Python/FastAPI, DuckDB)
- **Orders Service** — order processing and history (Python/FastAPI, DuckDB)
- **Analytics Service** — aggregates data from Products + Orders (Python/FastAPI, DuckDB)
- **Dashboard UI** — React frontend for browsing products, viewing orders, and analytics charts

Source code lives in `shared_app/`. Each lesson's manifests deploy or modify this stack.

## Prerequisites

- OpenShift cluster running (Red Hat Demo Platform, Developer Sandbox, or CRC)
- `oc` CLI installed and on PATH
- Basic Kubernetes knowledge (Deployments, Services, PVCs, ConfigMaps)

### Environment Options

| Option | Admin Access | Resources | Best For |
|--------|-------------|-----------|----------|
| **Red Hat Demo Platform** (recommended) | Full cluster-admin | Full cluster with GPUs | All lessons |
| Developer Sandbox | No admin | Shared, limited | L01-L04, L06-L07 only |
| OpenShift Local (CRC) | Full cluster-admin | Limited by your machine | All lessons, but slow |

## Lessons

| # | Lesson | Duration | What You'll Learn |
|---|--------|----------|-------------------|
| L01 | [Projects](L01_projects/) | 20 min | Projects vs Namespaces. Create the ShopInsights project, multi-environment setup (dev + staging). |
| L02 | [Build & Image Resources](L02_builds_and_images/) | 1 hr | BuildConfig, S2I, ImageStreams — the cluster builds your code. Internal registry. |
| L03 | [Deploy the Microservices Stack](L03_deploy_microservices/) | 45 min | Deploy 3 services + UI from ImageStreams with health probes, resource limits, ConfigMaps, Secrets. The SCC "no root" gotcha. |
| L04 | [Expose Services Externally](L04_expose_externally/) | 45 min | Routes with TLS. Route replaces Traefik for HTTP/HTTPS ingress. |
| L05 | [Service Mesh with Istio](L05_service_mesh/) | 1 hr | Istio ambient mode (ztunnel + waypoint proxies), automatic mTLS, canary deployments, Kiali, circuit breakers. |
| L06 | [Cluster Authentication & RBAC](L06_auth_and_identity/) | 45 min | OAuth, users, RBAC. OAuth replaces Keycloak for cluster auth. |
| L07 | [Monitoring & Logging](L07_monitoring_and_logging/) | 1.5–2 hrs | Custom Prometheus metrics from Python, ServiceMonitor, alerts, log forwarding with Loki. |
| L08 | [CI/CD Pipeline (Tekton)](L08_cicd_pipeline/) | 1 hr 15 min | Tekton pipeline: GitHub → test → build → push to GHCR → deploy. |
| L09 | [GitOps with ArgoCD](L09_gitops/) | 1 hr | ArgoCD, Kustomize overlays, drift detection, auto-heal. |
| L10 | [Serverless (Knative)](L10_serverless/) | 45 min | Scale-to-zero, cold starts, eventing. |
| L11 | [Application Auth (Keycloak)](L11_app_auth_keycloak/) | 75 min | Three auth patterns: user OIDC login, JWT-protected APIs, service-to-service (client credentials). |
| L12 | [Custom Monitoring Dashboards (Grafana)](L12_monitoring_and_logging_grafana/) | 45 min | Custom Grafana dashboards for application metrics and logging. |
| L13 | [External CI/CD (GitHub Actions)](L13_cicd_pipeline_github_actions/) | 45 min | GitHub Actions pipeline: build, push to GHCR, deploy to OpenShift. |

**Total: 13 lessons, ~11-12 hours**

## Lesson Dependencies

```
L01 Projects
 └── L02 Builds & Images
      └── L03 Deploy Microservices
           ├── L04 Expose Externally
           │    └── L05 Service Mesh (requires cluster-admin)
           ├── L06 Authentication & RBAC
           ├── L07 Monitoring & Logging
           │    └── L12 Custom Grafana Dashboards
           ├── L08 CI/CD Pipeline (Tekton, requires cluster-admin)
           │    └── L13 External CI/CD (GitHub Actions)
           ├── L09 GitOps (requires cluster-admin)
           ├── L10 Serverless (requires cluster-admin)
           └── L11 Application Auth (Keycloak)
```

Lessons L04-L13 all depend on the deployed stack from L01-L03. Within that group, each is largely self-contained — you can take them in any order, though the dependency tree above shows the most natural sequence.

## Admin Access Requirements

Some lessons install cluster-wide operators and require `cluster-admin`:

| Lesson | Requires cluster-admin | Why |
|--------|----------------------|-----|
| L01-L04 | No | Standard user operations |
| L05 | **Yes** | Installs Service Mesh operator |
| L06 | No | Uses existing OAuth; views RBAC |
| L07 | No | Uses user workload monitoring |
| L08 | **Yes** | Installs Tekton Pipelines operator |
| L09 | **Yes** | Installs ArgoCD operator |
| L10 | **Yes** | Installs Knative Serving operator |
| L11 | **Yes** | Installs Keycloak operator |
| L12 | No | Uses existing Grafana/monitoring stack |
| L13 | No | External CI (GitHub Actions), no operator install |

If you're on the Developer Sandbox (no admin), you can complete L01-L04, L06-L07, L12, and L13.

## Key OpenShift Concepts Covered

| Concept | K8s Equivalent | Lesson |
|---------|---------------|--------|
| Projects | Namespaces (with extra metadata + RBAC) | L01 |
| BuildConfig | No equivalent (external CI needed) | L02 |
| ImageStreams | No equivalent (direct image refs) | L02 |
| S2I (Source-to-Image) | No equivalent (needs Dockerfile) | L02 |
| Routes | Ingress (but pre-installed, more features) | L04 |
| Security Context Constraints (SCC) | Pod Security Standards | L03 |
| OAuth + HTPasswd | No built-in auth | L06 |
| OpenShift Service Mesh | Manual Istio install | L05 |
| OpenShift Pipelines | Manual Tekton install | L08 |
| OpenShift GitOps | Manual ArgoCD install | L09 |
| OpenShift Serverless | Manual Knative install | L10 |

## Lesson Directory Convention

Each lesson lives in `L<NN>_snake_case_name/` and contains:

```
LNN_lesson_name/
  README.md             # Lesson guide (primary deliverable)
  manifests/            # YAML manifests
  scripts/              # Shell scripts for setup, teardown, demos
```

## Next Steps

After completing this track, continue to the **OpenShift AI** tutorial (`tutorial_ai/openshift_ai/`) — 66 lessons across 3 levels covering model serving, fine-tuning, RAG, agents, pipelines, and production AI operations on OpenShift.
