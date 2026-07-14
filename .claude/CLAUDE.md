# OpenShift Tutorial Project

## Purpose

This is a project-based OpenShift tutorial for developers who already know Kubernetes. It contains three tutorial tracks:

- **OpenShift Platform** (`tutorial/`) — the prerequisite track covering core OpenShift capabilities (Routes, Service Mesh, CI/CD, GitOps, monitoring, serverless) using the "ShopInsights" application.
- **Red Hat AI Ecosystem** (`tutorial_ai/01_redhat_ai/`) — Podman AI Lab, RHEL AI, Granite models, model optimization, and cross-tier workflows.
- **OpenShift AI** (`tutorial_ai/02_openshift_ai/`) — model serving, fine-tuning, RAG, pipelines, agents, evaluation, and governance on the OpenShift AI platform.

Each track has a `syllabus.md` file with the full lesson/module breakdown. Consult those for structure and scope — do not rely on this file for lesson listings.

## Technical Stack

### Platform Track
- **Platform**: OpenShift 4.x (Red Hat OpenShift Container Platform)
- **CLI**: `oc` (primary), `kubectl` (for comparisons)
- **CI/CD**: OpenShift Pipelines (Tekton), OpenShift GitOps (ArgoCD)
- **Service Mesh**: OpenShift Service Mesh (Istio-based)
- **Serverless**: OpenShift Serverless (Knative)
- **Monitoring**: Built-in Prometheus + Grafana stack
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

## Rules for the AI Agent

### Where to find information
- **Syllabus and lesson structure**: read the track's `syllabus.md` file (`tutorial/syllabus.md`, `tutorial_ai/01_redhat_ai/syllabus.md`, `tutorial_ai/02_openshift_ai/syllabus.md`).
- **K8s ↔ OpenShift mapping**: see `k8s_vs_openshift.md` in the repo root.
- **Detailed conventions**: modular rule files in `.claude/rules/`:
  - `tutorial-structure.md` — layout and file conventions for both tracks
  - `lesson-content.md` — how to write README.md lesson guides
  - `manifest-standards.md` — YAML manifest conventions and patterns
  - `k8s-to-openshift.md` — how to frame K8s→OpenShift comparisons

### Content creation rules
- Every lesson's primary deliverable is its `README.md`. Follow the format in `.claude/rules/lesson-content.md`.
- All YAML manifests go in the lesson's `manifests/` directory. Follow `.claude/rules/manifest-standards.md`.
- All files must exist on disk — scripts reference them via `oc apply -f` or `sed` + pipe. Never embed file contents inline in scripts.
- Platform track: always start from the K8s concept the reader already knows, then show the OpenShift way.
- AI tracks: assume the reader completed the Platform track and knows OpenShift.

### Naming conventions
- Platform track lesson dirs: `L<NN>_snake_case_name/`
- AI track module dirs: `M<N>_snake_case_name/`
- AI track lesson dirs: `<N>_snake_case_name/`
- Manifest files: descriptive names (`deployment.yaml`, `route-edge-tls.yaml`, `k8s-ingress.yaml`)

### Environment assumptions
- Platform track: Red Hat Developer Sandbox (recommended) or OpenShift Local (CRC). Some lessons need cluster-admin — note this in prerequisites.
- AI tracks: Red Hat Demo Platform (GPU cluster with admin access).
