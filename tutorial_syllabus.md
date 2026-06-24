# OpenShift Tutorial — Comprehensive Syllabus

**Audience:** Developers and DevOps engineers with solid Kubernetes knowledge who want to master OpenShift.

**Approach:** Each module starts from what you already know in Kubernetes, then shows the OpenShift way — what it adds, what it restricts, and why.

**Environment:** OpenShift Local (CRC) for local development, optionally Red Hat Developer Sandbox for cloud exercises.

---

## Level 1 — Foundations (Kubernetes → OpenShift)

> Goal: Understand what OpenShift adds on top of Kubernetes. Get comfortable with the platform, CLI, and core concepts that differ from vanilla K8s.

### M1: Platform Setup & Architecture

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Architecture Overview | 30 min | OpenShift vs Kubernetes: what's added (OAuth, Router, Registry, Operator Hub, Web Console). Control plane components. RHCOS nodes. |
| 2 | Installing OpenShift Local (CRC) | 30 min | Install CRC, start the cluster, log in via CLI and Web Console. Resource requirements and tuning. |
| 3 | CLI Tools: `oc` vs `kubectl` | 30 min | `oc` as a superset of `kubectl`. Key extra commands: `oc new-app`, `oc new-project`, `oc adm`, `oc login`, `oc whoami`. When to use which. |
| 4 | Web Console Tour | 20 min | Administrator vs Developer perspective. Topology view. Navigating projects, workloads, monitoring. |

### M2: Projects, Users & RBAC

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Projects vs Namespaces | 20 min | Projects = namespaces + metadata + RBAC defaults. `oc new-project`, annotations, display name, description. Self-provisioning. |
| 2 | Authentication & OAuth | 30 min | Built-in OAuth server. Identity providers (HTPasswd, LDAP, GitHub, OpenID Connect). `oc login`, tokens, kubeconfig. Contrast with K8s ServiceAccount tokens. |
| 3 | RBAC Deep Dive | 30 min | ClusterRoles, Roles, RoleBindings. Default roles (`admin`, `edit`, `view`, `cluster-admin`). `oc adm policy`. SCCs (Security Context Constraints) — the OpenShift equivalent of PSPs. |
| 4 | Security Context Constraints (SCCs) | 30 min | Why pods can't run as root by default. Built-in SCCs (`restricted`, `anyuid`, `privileged`). Assigning SCCs to service accounts. Common gotchas for K8s users. |

### M3: Application Deployment — The OpenShift Way

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | `oc new-app` & Source-to-Image (S2I) | 40 min | Deploy from Git, Docker image, or template. S2I build strategy: source code → image without a Dockerfile. Builder images. |
| 2 | BuildConfigs & Build Strategies | 40 min | Docker builds, S2I builds, Pipeline builds, Custom builds. BuildConfig triggers (webhook, image change, config change). `oc start-build`. |
| 3 | ImageStreams & Image Management | 30 min | ImageStreams vs direct image references. Tags, scheduled imports, image change triggers. Why OpenShift uses this abstraction. |
| 4 | DeploymentConfigs vs Deployments | 30 min | Legacy DeploymentConfig (DC) vs K8s Deployment. Triggers, lifecycle hooks, rolling vs recreate. When to use which (spoiler: prefer Deployments now). |
| 5 | Templates & Kustomize | 30 min | OpenShift Templates with parameters. `oc process`. Comparison with Helm and Kustomize (both also supported). |

### M4: Networking & Routes

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Services & Pod Networking | 20 min | Same as K8s, with OpenShift SDN (OVN-Kubernetes). Multus for multiple network interfaces. NetworkPolicy. |
| 2 | Routes vs Ingress | 30 min | Routes: OpenShift's native ingress. HAProxy-based router. Edge, passthrough, re-encrypt TLS termination. Route annotations. Comparison with K8s Ingress (also supported). |
| 3 | TLS & Certificates | 30 min | Auto-generated certificates. Custom certs on routes. Cert-manager integration. |
| 4 | Network Policies | 20 min | Same K8s NetworkPolicy, but with OpenShift defaults (deny-by-default in multi-tenant mode). Egress firewalls. |

### M5: Storage

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Persistent Storage Basics | 20 min | PVs, PVCs, StorageClasses — same as K8s. Default storage in CRC. |
| 2 | OpenShift-Specific Storage | 30 min | OpenShift Data Foundation (ODF, formerly OCS). CSI drivers. Dynamic provisioning. `oc set volume`. |
| 3 | ConfigMaps & Secrets | 20 min | Same as K8s, with `oc create configmap` / `oc create secret` shortcuts. Linking secrets to service accounts. |

### M6: Monitoring & Logging

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Built-in Monitoring Stack | 30 min | Prometheus + Grafana pre-installed. Cluster monitoring vs user workload monitoring. Enabling user workload monitoring. |
| 2 | Alerts & Metrics | 30 min | PrometheusRules, AlertManager, custom ServiceMonitors. Viewing alerts in the console. |
| 3 | Logging with OpenShift Logging | 30 min | Elasticsearch/Loki + Fluentd/Vector + Kibana/Console. ClusterLogging and ClusterLogForwarder CRDs. |
| 4 | Events & Debugging | 20 min | `oc get events`, `oc logs`, `oc debug`, `oc rsh`, `oc exec`. The `oc debug node/` trick for node-level debugging. |

---

## Level 2 — Practitioner (Real-World Workflows)

> Goal: Build and deploy real applications using OpenShift's full feature set. CI/CD, operators, service mesh, and day-2 operations.

### M1: CI/CD on OpenShift

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | OpenShift Pipelines (Tekton) | 1 hr | Tasks, Pipelines, PipelineRuns. TriggerBindings and TriggerTemplates. Comparison with Jenkins and GitHub Actions. |
| 2 | Pipeline: Build, Test, Deploy | 1 hr | End-to-end pipeline: clone → build image → run tests → deploy to staging → promote to production. |
| 3 | OpenShift GitOps (ArgoCD) | 1 hr | ArgoCD operator. Application CRD. Sync policies. Git repo structure for GitOps. App-of-apps pattern. |
| 4 | Pipelines + GitOps Together | 45 min | Tekton pipeline updates a Git repo, ArgoCD syncs the cluster. The full GitOps CI/CD flow. |

### M2: Operators

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Operator Framework Concepts | 30 min | What are Operators? OLM (Operator Lifecycle Manager). OperatorHub. CRDs and controllers. Operator maturity levels. |
| 2 | Installing & Managing Operators | 30 min | Install from OperatorHub via Console and CLI. Subscriptions, InstallPlans, CSVs. Approval strategies (auto vs manual). |
| 3 | Using Operators: Database Example | 1 hr | Deploy PostgreSQL or MongoDB via an operator. CRD-based configuration. Backup, restore, scaling — all via CRs. |
| 4 | Building a Simple Operator | 1.5 hr | Operator SDK. Scaffold a Go or Ansible-based operator. Reconciliation loop. Deploy to the cluster. |

### M3: Service Mesh & Serverless

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | OpenShift Service Mesh (Istio) | 1 hr | Install the Service Mesh operator. ServiceMeshControlPlane, ServiceMeshMemberRoll. Sidecar injection. Traffic management, mTLS. |
| 2 | Traffic Management & Canary | 45 min | VirtualServices, DestinationRules. Canary deployments, traffic splitting, circuit breakers. Kiali dashboard. |
| 3 | OpenShift Serverless (Knative) | 1 hr | Install Knative Serving and Eventing operators. Knative Services, scale-to-zero, revisions, traffic splitting. |
| 4 | Event-Driven Architecture | 45 min | Knative Eventing: brokers, triggers, channels, subscriptions. CloudEvents. Connecting to Kafka. |

### M4: Advanced Networking

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Egress & Ingress Control | 30 min | EgressFirewall, EgressIP, EgressRouter. Controlling outbound traffic. |
| 2 | Multi-Cluster Networking | 45 min | Submariner. Cross-cluster service discovery. Use cases: hybrid cloud, disaster recovery. |
| 3 | Load Balancing & DNS | 30 min | MetalLB for bare metal. External DNS. Global load balancing concepts. |

### M5: Security Hardening

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Image Security & Compliance | 30 min | Image signing, image policies. Red Hat container catalog. Quay registry scanning. |
| 2 | Pod Security & Admission | 30 min | SCCs in depth. Pod Security Admission (K8s PSA). OPA Gatekeeper / Kyverno on OpenShift. |
| 3 | Secrets Management | 30 min | Sealed Secrets, External Secrets Operator, HashiCorp Vault integration. Rotating secrets. |
| 4 | Compliance & Auditing | 30 min | Compliance Operator. OpenSCAP scans. CIS benchmarks for OpenShift. Audit logs. |

### M6: Developer Experience

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | OpenShift Dev Spaces (Eclipse Che) | 45 min | Cloud-based IDE. Devfiles. Workspace configuration. |
| 2 | odo — Developer CLI | 30 min | `odo` vs `oc`. Inner loop development. `odo dev` for live sync. Devfile-based components. |
| 3 | Helm on OpenShift | 30 min | Helm chart repositories in the console. Installing, upgrading, and managing Helm releases. Certified Helm charts. |
| 4 | Application Health & Autoscaling | 30 min | Liveness, readiness, startup probes (same as K8s). HPA, VPA, and Cluster Autoscaler on OpenShift. |

---

## Level 3 — Expert (Production & Operations)

> Goal: Operate OpenShift at scale. Multi-cluster management, advanced security, performance tuning, disaster recovery, and migration strategies.

### M1: Cluster Administration

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Installation Methods | 1 hr | IPI (Installer-Provisioned Infrastructure) vs UPI (User-Provisioned Infrastructure). Bare metal, AWS, Azure, GCP, vSphere. Agent-based installer. |
| 2 | Cluster Upgrades & Lifecycle | 45 min | OTA (Over-The-Air) upgrades. Upgrade channels (stable, fast, candidate). Pre-upgrade health checks. Rollback. |
| 3 | Node Management | 45 min | MachineSets, MachineConfigPools, MachineConfigs. Adding/removing worker nodes. Infra nodes. Taints and tolerations at scale. |
| 4 | etcd & Control Plane Operations | 30 min | etcd backup and restore. Control plane certificates. Disaster recovery for masters. |
| 5 | Resource Management & Quotas | 30 min | ResourceQuotas, LimitRanges, ClusterResourceQuotas. Capacity planning. Priority classes. |

### M2: Multi-Cluster & Hybrid Cloud

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Advanced Cluster Management (ACM) | 1 hr | RHACM: hub cluster + managed clusters. Cluster lifecycle, policy-based governance, application distribution. |
| 2 | Multi-Cluster Observability | 45 min | Centralized monitoring across clusters. Thanos-based metrics aggregation. Multi-cluster logging. |
| 3 | Multi-Cluster GitOps | 45 min | ApplicationSets in ArgoCD. Placement policies. Promoting across environments (dev → staging → prod) across clusters. |
| 4 | Hybrid & Edge Deployments | 45 min | OpenShift on bare metal, edge (SNO — Single Node OpenShift), MicroShift. Remote worker nodes. |

### M3: Performance & Troubleshooting

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Performance Tuning | 1 hr | Node Tuning Operator. Huge pages, CPU pinning, NUMA awareness. Performance profiles. |
| 2 | Troubleshooting Methodology | 1 hr | Systematic debugging: must-gather, `oc adm inspect`, sosreport. Debugging OOM kills, CrashLoopBackOff, image pull errors, scheduling failures. |
| 3 | Disaster Recovery | 45 min | etcd snapshot and restore. Recovering from quorum loss. Backing up cluster state. Velero for application-level backup. |
| 4 | Cost Management | 30 min | Cost Management Operator. Metering. Chargeback models. Resource optimization. |

### M4: Advanced Workloads

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | OpenShift Virtualization (KubeVirt) | 1 hr | Running VMs alongside containers. VirtualMachine CRD. VM migration. Use cases: legacy apps, Windows workloads. |
| 2 | OpenShift AI (RHOAI) | 1 hr | Red Hat OpenShift AI platform. JupyterHub, model serving, data science pipelines. GPU scheduling. |
| 3 | Stateful Workloads at Scale | 45 min | StatefulSets patterns. Operator-managed databases (CrunchyData PostgreSQL, Strimzi Kafka). Storage performance. |
| 4 | Batch & HPC Workloads | 30 min | Jobs, CronJobs, and OpenShift-specific scheduling. NVIDIA GPU Operator. MPI jobs. |

### M5: Migration & Capstones

| # | Lesson | Duration | Description |
|---|--------|----------|-------------|
| 1 | Migrating from Kubernetes to OpenShift | 1 hr | What changes: SCCs, Routes vs Ingress, image policies, default security. Migration toolkit for containers (MTC). Checklist and common pitfalls. |
| 2 | Migrating Legacy Apps to OpenShift | 45 min | Containerizing VM-based apps. S2I for legacy code. Strategies: lift-and-shift, refactor, replatform. |
| 3 | Capstone: Production-Ready Microservices | 2 hr | Deploy a multi-service app with: CI/CD pipeline, GitOps, service mesh, monitoring, autoscaling, network policies, proper RBAC. |
| 4 | Capstone: Multi-Cluster Platform | 2 hr | Set up a multi-cluster environment with ACM. Centralized policy, observability, and application deployment across clusters. |

---

## Appendices

### A: OpenShift vs Kubernetes — Quick Reference

| Concept | Kubernetes | OpenShift |
|---------|-----------|-----------|
| Namespace | `Namespace` | `Project` (superset) |
| Ingress | `Ingress` + controller | `Route` (built-in HAProxy) |
| Container registry | External (Docker Hub, etc.) | Built-in registry + ImageStreams |
| CI/CD | External (Jenkins, GitHub Actions) | OpenShift Pipelines (Tekton) built-in |
| GitOps | Install ArgoCD yourself | OpenShift GitOps operator |
| Monitoring | Install Prometheus yourself | Pre-installed Prometheus + Grafana |
| Logging | Install EFK yourself | OpenShift Logging operator |
| Service mesh | Install Istio yourself | OpenShift Service Mesh operator |
| Serverless | Install Knative yourself | OpenShift Serverless operator |
| Pod security | PodSecurity Admission | SCCs (more granular) |
| CLI | `kubectl` | `oc` (superset of `kubectl`) |
| Web UI | Dashboard (basic) | Full Web Console (Admin + Dev views) |
| Identity | External (OIDC, etc.) | Built-in OAuth server |
| Build | External (Docker, Kaniko) | BuildConfig + S2I (built-in) |
| Operators | Install OLM yourself | OLM + OperatorHub pre-installed |
| Node OS | Any Linux | RHCOS (immutable, managed) |

### B: Environment Setup Checklist

- [ ] CRC installed and running (`crc setup && crc start`)
- [ ] `oc` CLI installed and on PATH
- [ ] Logged in as `developer` and `kubeadmin`
- [ ] Web Console accessible at https://console-openshift-console.apps-crc.testing
- [ ] Sufficient resources: 4+ CPUs, 16+ GB RAM, 35+ GB disk

### C: Useful Resources

- [OpenShift Documentation](https://docs.openshift.com/)
- [OpenShift Interactive Learning](https://learn.openshift.com/)
- [Red Hat Developer Sandbox](https://developers.redhat.com/developer-sandbox) (free cloud cluster)
- [Kubernetes to OpenShift Migration Guide](https://docs.openshift.com/)
- [Operator SDK](https://sdk.operatorframework.io/)
- [CRC (OpenShift Local)](https://crc.dev/crc/)
