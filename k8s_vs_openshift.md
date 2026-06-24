# Kubernetes vs OpenShift — Resource Comparison

A comprehensive mapping of Kubernetes resources to their OpenShift equivalents, additions, and enhancements.

## Core Workload Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| Pod | `Pod` | `Pod` (identical) | Same API, but OpenShift enforces SCCs (restricted by default — no root) |
| Deployment | `apps/v1 Deployment` | `apps/v1 Deployment` (identical) | Preferred for all workloads on both platforms |
| ReplicaSet | `apps/v1 ReplicaSet` | `apps/v1 ReplicaSet` (identical) | Managed by Deployments on both |
| StatefulSet | `apps/v1 StatefulSet` | `apps/v1 StatefulSet` (identical) | Same API |
| DaemonSet | `apps/v1 DaemonSet` | `apps/v1 DaemonSet` (identical) | Same API |
| Job | `batch/v1 Job` | `batch/v1 Job` (identical) | Same API |
| CronJob | `batch/v1 CronJob` | `batch/v1 CronJob` (identical) | Same API |

## Networking Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| Service | `v1 Service` (ClusterIP, NodePort, LoadBalancer) | `v1 Service` (identical) | Same API |
| Ingress | `networking.k8s.io/v1 Ingress` + install your own controller | `networking.k8s.io/v1 Ingress` (supported) | Works on OpenShift, but Routes are the native option |
| Route | — | `route.openshift.io/v1 Route` | OpenShift-native ingress. HAProxy-based, pre-installed. Supports edge, passthrough, re-encrypt TLS. |
| IngressController | Varies by implementation | `operator.openshift.io/v1 IngressController` | Manages the HAProxy-based OpenShift router |
| NetworkPolicy | `networking.k8s.io/v1 NetworkPolicy` | `networking.k8s.io/v1 NetworkPolicy` (identical) | Same API; OpenShift uses OVN-Kubernetes by default |
| EgressFirewall | — | `k8s.ovn.org/v1 EgressFirewall` | Controls outbound traffic per namespace |
| EgressIP | — | `k8s.ovn.org/v1 EgressIP` | Assigns stable source IPs for egress traffic |
| EndpointSlice | `discovery.k8s.io/v1 EndpointSlice` | `discovery.k8s.io/v1 EndpointSlice` (identical) | Same API |

## Namespace & Project Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| Namespace | `v1 Namespace` | `v1 Namespace` (identical) | Works on OpenShift unchanged |
| Project | — | `project.openshift.io/v1 Project` | Superset of Namespace: adds display name, description, default RBAC, self-provisioning |
| ProjectRequest | — | `project.openshift.io/v1 ProjectRequest` | Creates a Project with default role bindings via a template |

## Build & Image Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| BuildConfig | — | `build.openshift.io/v1 BuildConfig` | Defines how to build images. Strategies: Source (S2I), Docker, Custom, Pipeline (legacy). |
| Build | — | `build.openshift.io/v1 Build` | A single execution of a BuildConfig |
| ImageStream | — | `image.openshift.io/v1 ImageStream` | Abstraction over image references. Enables triggers, rollback, and scheduled imports. |
| ImageStreamTag | — | `image.openshift.io/v1 ImageStreamTag` | A specific tag within an ImageStream |
| ImageStreamImage | — | `image.openshift.io/v1 ImageStreamImage` | An image by digest within an ImageStream |
| ImageStreamImport | — | `image.openshift.io/v1 ImageStreamImport` | Import external images into an ImageStream |
| ImageStreamMapping | — | `image.openshift.io/v1 ImageStreamMapping` | Used internally by the build system |

## Authentication & Authorization Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| ServiceAccount | `v1 ServiceAccount` | `v1 ServiceAccount` (identical) | Same API |
| ClusterRole | `rbac.authorization.k8s.io/v1 ClusterRole` | `rbac.authorization.k8s.io/v1 ClusterRole` (identical) | Same API; OpenShift adds default roles: `admin`, `edit`, `view`, `basic-user`, `self-provisioner` |
| Role | `rbac.authorization.k8s.io/v1 Role` | `rbac.authorization.k8s.io/v1 Role` (identical) | Same API |
| ClusterRoleBinding | `rbac.authorization.k8s.io/v1 ClusterRoleBinding` | `rbac.authorization.k8s.io/v1 ClusterRoleBinding` (identical) | Same API |
| RoleBinding | `rbac.authorization.k8s.io/v1 RoleBinding` | `rbac.authorization.k8s.io/v1 RoleBinding` (identical) | Same API |
| OAuth | — | `config.openshift.io/v1 OAuth` | Configures the built-in OAuth server and identity providers |
| OAuthClient | — | `oauth.openshift.io/v1 OAuthClient` | Registers an OAuth client for token-based auth |
| OAuthAccessToken | — | `oauth.openshift.io/v1 OAuthAccessToken` | Represents an issued OAuth token |
| User | — | `user.openshift.io/v1 User` | Represents an authenticated user |
| Group | — | `user.openshift.io/v1 Group` | Groups of users for RBAC bindings |
| Identity | — | `user.openshift.io/v1 Identity` | Maps a user to an identity provider |

## Security Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| Pod Security Admission | Namespace labels (`pod-security.kubernetes.io/*`) | Namespace labels (supported) | Works on OpenShift 4.11+, but SCCs remain the primary enforcement |
| SecurityContextConstraints | — | `security.openshift.io/v1 SecurityContextConstraints` | OpenShift's pod security mechanism. Built-in: `restricted-v2`, `nonroot-v2`, `hostnetwork-v2`, `anyuid`, `hostaccess`, `privileged` |
| RangeAllocation | — | `security.openshift.io/v1 RangeAllocation` | Manages UID/GID range assignments per namespace |

## Configuration & Storage Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| ConfigMap | `v1 ConfigMap` | `v1 ConfigMap` (identical) | Same API |
| Secret | `v1 Secret` | `v1 Secret` (identical) | Same API; `oc create secret` adds shortcuts |
| PersistentVolume | `v1 PersistentVolume` | `v1 PersistentVolume` (identical) | Same API |
| PersistentVolumeClaim | `v1 PersistentVolumeClaim` | `v1 PersistentVolumeClaim` (identical) | Same API |
| StorageClass | `storage.k8s.io/v1 StorageClass` | `storage.k8s.io/v1 StorageClass` (identical) | Same API; CRC ships a default StorageClass |
| CSIDriver | `storage.k8s.io/v1 CSIDriver` | `storage.k8s.io/v1 CSIDriver` (identical) | Same API |

## Autoscaling Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| HorizontalPodAutoscaler | `autoscaling/v2 HPA` | `autoscaling/v2 HPA` (identical) | Same API |
| VerticalPodAutoscaler | Install `vertical-pod-autoscaler` add-on | `autoscaling.openshift.io/v1 VPA` | Pre-available via operator |
| ClusterAutoscaler | Cloud-specific add-on (e.g., `cluster-autoscaler`) | `autoscaling.openshift.io/v1 ClusterAutoscaler` | Integrated with Machine API |
| MachineAutoscaler | — | `autoscaling.openshift.io/v1beta1 MachineAutoscaler` | Autoscales MachineSets (node count) |

## Machine API Resources (OpenShift Only)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| Machine | — | `machine.openshift.io/v1beta1 Machine` | Represents a single node (VM/physical) |
| MachineSet | — | `machine.openshift.io/v1beta1 MachineSet` | Declarative node scaling (like ReplicaSet for nodes) |
| MachineHealthCheck | — | `machine.openshift.io/v1beta1 MachineHealthCheck` | Auto-remediates unhealthy nodes |
| MachineConfig | — | `machineconfiguration.openshift.io/v1 MachineConfig` | Configures node OS (kernel params, files, systemd units) |
| MachineConfigPool | — | `machineconfiguration.openshift.io/v1 MachineConfigPool` | Groups nodes for MachineConfig application (worker, master, infra) |

## Operator Lifecycle Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| CustomResourceDefinition | `apiextensions.k8s.io/v1 CRD` | `apiextensions.k8s.io/v1 CRD` (identical) | Same API |
| CatalogSource | Install OLM yourself | `operators.coreos.com/v1alpha1 CatalogSource` | OLM pre-installed; defines operator catalogs |
| Subscription | — (with OLM) | `operators.coreos.com/v1alpha1 Subscription` | Subscribes to an operator from a catalog |
| ClusterServiceVersion | — (with OLM) | `operators.coreos.com/v1alpha1 ClusterServiceVersion` | Describes an operator version and its requirements |
| InstallPlan | — (with OLM) | `operators.coreos.com/v1alpha1 InstallPlan` | Tracks the installation/upgrade of an operator |
| OperatorGroup | — (with OLM) | `operators.coreos.com/v1 OperatorGroup` | Defines which namespaces an operator watches |
| OperatorCondition | — (with OLM) | `operators.coreos.com/v2 OperatorCondition` | Communicates operator health to OLM |

## Monitoring Resources

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| ServiceMonitor | Install `kube-prometheus-stack` yourself | `monitoring.coreos.com/v1 ServiceMonitor` | Pre-installed with cluster monitoring |
| PodMonitor | Install `kube-prometheus-stack` yourself | `monitoring.coreos.com/v1 PodMonitor` | Pre-installed with cluster monitoring |
| PrometheusRule | Install `kube-prometheus-stack` yourself | `monitoring.coreos.com/v1 PrometheusRule` | Pre-installed; defines alerting/recording rules |
| AlertmanagerConfig | Install yourself | `monitoring.coreos.com/v1beta1 AlertmanagerConfig` | Namespace-scoped Alertmanager routing |
| Prometheus | Install yourself | `monitoring.coreos.com/v1 Prometheus` | Managed by the cluster monitoring operator |
| Alertmanager | Install yourself | `monitoring.coreos.com/v1 Alertmanager` | Managed by the cluster monitoring operator |

## CI/CD Resources (Tekton — OpenShift Pipelines)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| Task | Install Tekton yourself | `tekton.dev/v1 Task` | Pre-installed via OpenShift Pipelines operator |
| ClusterTask | Install Tekton yourself | `tekton.dev/v1beta1 ClusterTask` | Cluster-scoped task (deprecated in favor of Resolver) |
| Pipeline | Install Tekton yourself | `tekton.dev/v1 Pipeline` | Chains Tasks together |
| PipelineRun | Install Tekton yourself | `tekton.dev/v1 PipelineRun` | Single execution of a Pipeline |
| TaskRun | Install Tekton yourself | `tekton.dev/v1 TaskRun` | Single execution of a Task |
| EventListener | Install Tekton Triggers yourself | `triggers.tekton.dev/v1beta1 EventListener` | Receives webhooks and triggers PipelineRuns |
| TriggerBinding | Install Tekton Triggers yourself | `triggers.tekton.dev/v1beta1 TriggerBinding` | Extracts fields from webhook payloads |
| TriggerTemplate | Install Tekton Triggers yourself | `triggers.tekton.dev/v1beta1 TriggerTemplate` | Stamps out resources from trigger data |

## GitOps Resources (ArgoCD — OpenShift GitOps)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| Application | Install ArgoCD yourself | `argoproj.io/v1alpha1 Application` | Pre-installed via OpenShift GitOps operator |
| ApplicationSet | Install ArgoCD yourself | `argoproj.io/v1alpha1 ApplicationSet` | Multi-cluster/multi-env application generation |
| AppProject | Install ArgoCD yourself | `argoproj.io/v1alpha1 AppProject` | Scopes source repos and destination clusters |
| ArgoCD | — | `argoproj.io/v1beta1 ArgoCD` | OpenShift GitOps operator CR to manage ArgoCD instances |

## Service Mesh Resources (Istio — OpenShift Service Mesh)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| VirtualService | Install Istio yourself | `networking.istio.io/v1beta1 VirtualService` | Pre-installed via Service Mesh operator |
| DestinationRule | Install Istio yourself | `networking.istio.io/v1beta1 DestinationRule` | Traffic policies, circuit breakers, mTLS |
| Gateway | Install Istio yourself | `networking.istio.io/v1beta1 Gateway` | Mesh ingress/egress configuration |
| PeerAuthentication | Install Istio yourself | `security.istio.io/v1beta1 PeerAuthentication` | mTLS policies |
| ServiceMeshControlPlane | — | `maistra.io/v2 ServiceMeshControlPlane` | OpenShift-specific: configures the entire mesh |
| ServiceMeshMemberRoll | — | `maistra.io/v1 ServiceMeshMemberRoll` | OpenShift-specific: enrolls namespaces in the mesh |

## Serverless Resources (Knative — OpenShift Serverless)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| Knative Service | Install Knative yourself | `serving.knative.dev/v1 Service` | Scale-to-zero, revisions, traffic splitting |
| Revision | Install Knative yourself | `serving.knative.dev/v1 Revision` | Immutable snapshot of a Service |
| Broker | Install Knative yourself | `eventing.knative.dev/v1 Broker` | Event routing hub |
| Trigger | Install Knative yourself | `eventing.knative.dev/v1 Trigger` | Filters events from a Broker to a subscriber |
| KnativeServing | — | `operator.knative.dev/v1beta1 KnativeServing` | OpenShift Serverless operator CR |
| KnativeEventing | — | `operator.knative.dev/v1beta1 KnativeEventing` | OpenShift Serverless operator CR |

## Virtualization Resources (OpenShift Only)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| VirtualMachine | — | `kubevirt.io/v1 VirtualMachine` | Declarative VM lifecycle (start, stop, restart) |
| VirtualMachineInstance | — | `kubevirt.io/v1 VirtualMachineInstance` | Running VM instance (like Pod for VMs) |
| DataVolume | — | `cdi.kubevirt.io/v1beta1 DataVolume` | Import VM disk images from URL, registry, or PVC |

## Cluster Configuration Resources (OpenShift Only)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| ClusterVersion | — | `config.openshift.io/v1 ClusterVersion` | Cluster version and upgrade state |
| Infrastructure | — | `config.openshift.io/v1 Infrastructure` | Platform type, API URLs, cloud provider info |
| Ingress (config) | — | `config.openshift.io/v1 Ingress` | Cluster-wide ingress configuration (domain, certs) |
| Network | — | `config.openshift.io/v1 Network` | Cluster networking configuration (SDN, CIDRs) |
| Proxy | — | `config.openshift.io/v1 Proxy` | Cluster-wide proxy settings |
| DNS | — | `config.openshift.io/v1 DNS` | Cluster DNS configuration |
| APIServer | — | `config.openshift.io/v1 APIServer` | API server configuration (encryption, audit, certs) |
| Scheduler | — | `config.openshift.io/v1 Scheduler` | Scheduler profiles and policies |
| FeatureGate | — | `config.openshift.io/v1 FeatureGate` | Enable/disable feature gates |
| Image (config) | — | `config.openshift.io/v1 Image` | Cluster image policy (registries, signing) |
| Console | — | `operator.openshift.io/v1 Console` | Web Console configuration |
| ClusterOperator | — | `config.openshift.io/v1 ClusterOperator` | Health status of each built-in operator |

## Logging Resources (OpenShift Only)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| ClusterLogging | — | `logging.openshift.io/v1 ClusterLogging` | Configures the logging stack (Loki/ES + collector) |
| ClusterLogForwarder | — | `logging.openshift.io/v1 ClusterLogForwarder` | Routes logs to internal/external destinations |

## Compliance Resources (OpenShift Only)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| ComplianceScan | — | `compliance.openshift.io/v1alpha1 ComplianceScan` | Runs an OpenSCAP compliance scan |
| ComplianceSuite | — | `compliance.openshift.io/v1alpha1 ComplianceSuite` | Groups multiple scans into a suite |
| ComplianceRemediation | — | `compliance.openshift.io/v1alpha1 ComplianceRemediation` | Auto-generated fix for a compliance finding |
| ScanSettingBinding | — | `compliance.openshift.io/v1alpha1 ScanSettingBinding` | Binds scan settings to profiles |

## Multi-Cluster Resources (RHACM)

| Resource | Kubernetes | OpenShift | Notes |
|----------|-----------|-----------|-------|
| ManagedCluster | — | `cluster.open-cluster-management.io/v1 ManagedCluster` | A cluster managed by the ACM hub |
| Placement | — | `cluster.open-cluster-management.io/v1beta1 Placement` | Selects target clusters for workload distribution |
| Policy | — | `policy.open-cluster-management.io/v1 Policy` | Governance policy applied across clusters |
| MultiClusterObservability | — | `observability.open-cluster-management.io/v1beta2 MultiClusterObservability` | Fleet-wide metrics aggregation |

---

## Summary

| Category | K8s Resources | OpenShift-Only Resources | Shared (Identical API) |
|----------|:------------:|:------------------------:|:---------------------:|
| Workloads | 7 | 0 | 7 |
| Networking | 4 | 4 (Route, EgressFirewall, EgressIP, IngressController) | 4 |
| Namespaces | 1 | 2 (Project, ProjectRequest) | 1 |
| Builds & Images | 0 | 7 (BuildConfig, ImageStream, etc.) | 0 |
| Auth & Identity | 5 | 6 (OAuth, User, Group, Identity, etc.) | 5 |
| Security | 0 | 2 (SCC, RangeAllocation) | 1 (PSA) |
| Storage & Config | 6 | 0 | 6 |
| Autoscaling | 1 | 3 (ClusterAutoscaler, MachineAutoscaler, VPA) | 1 |
| Machine API | 0 | 5 | 0 |
| Operators (OLM) | 1 (CRD) | 6 (Subscription, CSV, etc.) | 1 |
| Monitoring | 0 | 6 (pre-installed) | 0 |
| CI/CD (Tekton) | 0 | 8 (pre-installed) | 0 |
| GitOps (ArgoCD) | 0 | 4 (pre-installed) | 0 |
| Service Mesh | 0 | 6 (pre-installed) | 0 |
| Serverless | 0 | 6 (pre-installed) | 0 |
| Virtualization | 0 | 3 | 0 |
| Cluster Config | 0 | 12 | 0 |
| Logging | 0 | 2 | 0 |
| Compliance | 0 | 4 | 0 |
| Multi-Cluster | 0 | 4 | 0 |

**Key takeaway:** Every standard Kubernetes resource works unchanged on OpenShift. OpenShift adds ~85 additional resource types across builds, security, machine management, and pre-integrated platform services (monitoring, CI/CD, mesh, serverless, GitOps) that you would otherwise install and manage yourself on vanilla Kubernetes.
