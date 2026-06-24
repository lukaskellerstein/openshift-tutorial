# L3-M5.4 — Capstone: Multi-Cluster Platform

**Level:** Expert
**Duration:** 2 hr

## Overview

This capstone brings together everything you have learned across all three levels of this tutorial. You will build a production-grade multi-cluster OpenShift platform using Red Hat Advanced Cluster Management (RHACM). Starting from the Kubernetes concept of managing multiple clusters manually with kubeconfig contexts, you will set up a hub-spoke architecture where a central hub cluster governs two or more spoke (managed) clusters with centralized policy enforcement, multi-cluster observability, ApplicationSet-based workload distribution, and disaster recovery capabilities.

By the end of this capstone, you will have a fully operational multi-cluster platform that mirrors what enterprises run in production -- complete with governance policies, cross-cluster monitoring, GitOps-driven application delivery, and tested failover procedures.

## Prerequisites

- Completed: All Level 1, Level 2, and Level 3 modules
- Specifically: L3-M2.1 (Advanced Cluster Management), L3-M2.2 (Multi-Cluster Observability), L3-M2.3 (Multi-Cluster GitOps)
- Specifically: L3-M3.3 (Disaster Recovery), L2-M1.3 (OpenShift GitOps / ArgoCD)
- Three OpenShift clusters available:
  - **Hub cluster**: OpenShift 4.14+ with RHACM operator installed (minimum 16 GB RAM, 8 CPUs)
  - **Spoke cluster 1** ("production-east"): OpenShift 4.14+
  - **Spoke cluster 2** ("production-west"): OpenShift 4.14+
- `oc` CLI installed (v4.14+)
- `kubectl` CLI installed (for comparisons)
- Git repository accessible by all clusters (for GitOps)
- Cluster admin access on all three clusters

> **Note:** If you do not have three separate clusters, you can simulate this setup using a single cluster as the hub and importing it as a "local-cluster" managed cluster. Some DR scenarios will be limited in that configuration.

## K8s Context

In vanilla Kubernetes, managing multiple clusters means:

- Switching between kubeconfig contexts manually (`kubectl config use-context`)
- No built-in way to enforce policies across clusters
- Installing and managing Prometheus, Grafana, ArgoCD, and other tooling independently on each cluster
- Manual disaster recovery with Velero backups and ad hoc restore procedures
- No centralized view of workload health across clusters

Federation (KubeFed) was the upstream attempt to solve multi-cluster orchestration, but it never reached production maturity and has been effectively deprecated. The CNCF is exploring newer approaches (e.g., Multi-Cluster Services API), but none provide the integrated governance-observability-deployment story that RHACM delivers.

## Concepts

### Architecture Overview

RHACM uses a hub-spoke model. The hub cluster runs the management plane; spoke clusters run workloads. This is fundamentally different from the K8s federation model, which tried to make all clusters peers.

```
+------------------------------------------------------------------+
|                        RHACM HUB CLUSTER                         |
|                                                                  |
|  +------------------+  +------------------+  +----------------+  |
|  | Cluster Lifecycle |  | Policy Engine    |  | App Lifecycle  |  |
|  | Management       |  | (Governance)     |  | (GitOps)       |  |
|  +--------+---------+  +--------+---------+  +-------+--------+  |
|           |                      |                    |           |
|  +--------+---------+  +--------+---------+  +-------+--------+  |
|  | ManagedCluster   |  | PlacementRules / |  | ApplicationSet |  |
|  | CRDs             |  | Placements       |  | Controller     |  |
|  +--------+---------+  +--------+---------+  +-------+--------+  |
|           |                      |                    |           |
|  +--------+----------------------+--------------------+--------+ |
|  |              Multi-Cluster Observability                    | |
|  |    (Thanos + Grafana + AlertManager aggregation)            | |
|  +-----+-------------------------------------------+----------+ |
|        |                                           |             |
+--------+-------------------------------------------+-------------+
         |                                           |
    +----+----+                                 +----+----+
    |  Spoke  |                                 |  Spoke  |
    |   #1    |                                 |   #2    |
    | (east)  |                                 | (west)  |
    |         |                                 |         |
    | kluster-|                                 | kluster-|
    | let     |                                 | let     |
    | agent   |                                 | agent   |
    +---------+                                 +---------+
```

### Key Components

**Cluster Lifecycle Management** manages the full lifecycle of spoke clusters -- provisioning, importing, upgrading, and decommissioning. Each spoke runs a `klusterlet` agent that maintains a secure channel back to the hub.

**Policy-Based Governance** enforces organizational standards across all managed clusters. Policies can audit or enforce configurations such as required labels, image source restrictions, resource quotas, network policies, and compliance standards (CIS benchmarks, NIST).

**Application Lifecycle** distributes workloads across clusters using ArgoCD ApplicationSets with placement-based targeting. This builds on the GitOps concepts from L2-M1.3 and L3-M2.3 but adds cluster-aware scheduling.

**Multi-Cluster Observability** aggregates metrics from all managed clusters into a centralized Thanos instance on the hub. This extends what you learned in L3-M2.2 with production hardening -- retention policies, storage sizing, and alerting across clusters.

**Disaster Recovery** combines etcd backups (L3-M1.4), Velero application backups (L3-M3.3), and RHACM's ability to redistribute workloads to surviving clusters when a cluster fails.

### Why RHACM Over DIY Multi-Cluster?

| Concern | DIY (K8s) | RHACM (OpenShift) |
|---------|-----------|-------------------|
| Cluster inventory | Kubeconfig files, manual tracking | ManagedCluster CRDs, auto-discovery |
| Policy enforcement | Install OPA/Kyverno per cluster | Centralized policy engine with templates |
| Monitoring | Prometheus federation or Thanos per cluster | Integrated Thanos with auto-collection |
| App distribution | Manual ArgoCD per cluster | ApplicationSets with placement rules |
| Cluster upgrades | Manual, per-cluster | Orchestrated from hub with rollout strategies |
| DR / failover | Manual Velero + DNS switching | Policy-driven workload redistribution |

## Step-by-Step

### Step 1: Verify Hub Cluster and RHACM Installation

Confirm RHACM is installed and healthy on your hub cluster.

```bash
# Log in to the hub cluster
oc login -u admin https://api.hub-cluster.example.com:6443

# Verify RHACM operator is installed
oc get csv -n open-cluster-management | grep advanced-cluster-management

# Check that all RHACM pods are running
oc get pods -n open-cluster-management --field-selector=status.phase!=Running

# If the above returns pods, wait for them to be ready
oc wait --for=condition=Ready pods --all -n open-cluster-management --timeout=300s

# Verify the MultiClusterHub CR is in Running phase
oc get multiclusterhub -n open-cluster-management
```

Expected output:
```
NAME                 STATUS    AGE
multiclusterhub      Running   2d
```

If RHACM is not installed, apply the operator subscription:

```bash
oc apply -f manifests/rhacm-operator-subscription.yaml
```

### Step 2: Import Spoke Clusters

Import both spoke clusters into the hub. Each spoke needs a `ManagedCluster` resource on the hub and a `klusterlet` agent deployed on the spoke.

```bash
# Create ManagedCluster resources for both spokes
oc apply -f manifests/managed-cluster-east.yaml
oc apply -f manifests/managed-cluster-west.yaml
```

Now generate the import commands for each spoke. RHACM creates a secret containing the klusterlet deployment manifests:

```bash
# For spoke-east: extract the import command
oc get secret production-east-import -n production-east \
  -o jsonpath='{.data.crds\.yaml}' | base64 -d > /tmp/east-crds.yaml
oc get secret production-east-import -n production-east \
  -o jsonpath='{.data.import\.yaml}' | base64 -d > /tmp/east-import.yaml

# Log in to spoke-east and apply
oc login -u admin https://api.production-east.example.com:6443
oc apply -f /tmp/east-crds.yaml
oc apply -f /tmp/east-import.yaml

# Repeat for spoke-west
oc login -u admin https://api.hub-cluster.example.com:6443
oc get secret production-west-import -n production-west \
  -o jsonpath='{.data.crds\.yaml}' | base64 -d > /tmp/west-crds.yaml
oc get secret production-west-import -n production-west \
  -o jsonpath='{.data.import\.yaml}' | base64 -d > /tmp/west-import.yaml

oc login -u admin https://api.production-west.example.com:6443
oc apply -f /tmp/west-crds.yaml
oc apply -f /tmp/west-import.yaml
```

Switch back to the hub and verify both clusters are joined:

```bash
oc login -u admin https://api.hub-cluster.example.com:6443
oc get managedclusters
```

Expected output:
```
NAME               HUB ACCEPTED   MANAGED CLUSTER URLS                          JOINED   AVAILABLE   AGE
local-cluster      true           https://api.hub-cluster.example.com:6443      True     True        2d
production-east    true           https://api.production-east.example.com:6443  True     True        5m
production-west    true           https://api.production-west.example.com:6443  True     True        3m
```

Alternatively, use the automated import script:

```bash
./scripts/import-spoke-cluster.sh production-east https://api.production-east.example.com:6443 admin
```

### Step 3: Apply Cluster Labels and ManagedClusterSets

Labels drive placement decisions. Apply environment and region labels, then group clusters into sets:

```bash
# Apply labels to managed clusters
oc label managedcluster production-east \
  environment=production \
  region=us-east \
  tier=primary \
  --overwrite

oc label managedcluster production-west \
  environment=production \
  region=us-west \
  tier=secondary \
  --overwrite

# Create a ManagedClusterSet to group production clusters
oc apply -f manifests/managed-cluster-set.yaml

# Bind the cluster set to the target namespace for ApplicationSets
oc apply -f manifests/managed-cluster-set-binding.yaml
```

### Step 4: Deploy Centralized Policy Governance

Policies enforce organizational standards across all managed clusters. We will deploy a policy set covering security baselines, resource governance, and compliance.

```bash
# Apply the policy namespace
oc apply -f manifests/policy-namespace.yaml

# Deploy security policies
oc apply -f manifests/policy-restricted-scc.yaml
oc apply -f manifests/policy-network-policies.yaml
oc apply -f manifests/policy-resource-quotas.yaml
oc apply -f manifests/policy-image-policies.yaml

# Deploy the placement rule for policy targeting
oc apply -f manifests/policy-placement.yaml
```

Verify policy compliance across clusters:

```bash
# Check policy status
oc get policy -A

# Detailed compliance view
oc get policy -n platform-policies -o custom-columns=\
NAME:.metadata.name,\
REMEDIATION:.spec.remediationAction,\
COMPLIANT:.status.compliant
```

Expected output:
```
NAME                       REMEDIATION   COMPLIANT
policy-restricted-scc      enforce       Compliant
policy-network-policies    enforce       Compliant
policy-resource-quotas     inform        NonCompliant
policy-image-policies      enforce       Compliant
```

> **Failure Mode -- Policy Violation:** When a policy is set to `inform`, non-compliance generates alerts but does not block workloads. When set to `enforce`, RHACM actively remediates the managed cluster. If a spoke cluster's klusterlet loses connectivity, policies queue and apply upon reconnection. Check `oc get managedcluster <name> -o jsonpath='{.status.conditions}'` to diagnose connectivity issues.

### Step 5: Configure Multi-Cluster Observability

Deploy the Observability add-on to collect metrics from all managed clusters into a centralized Thanos instance on the hub.

```bash
# Create the observability namespace and object storage secret
oc apply -f manifests/observability-namespace.yaml
oc apply -f manifests/observability-s3-secret.yaml

# Deploy the MultiClusterObservability CR
oc apply -f manifests/multi-cluster-observability.yaml
```

Wait for observability components to be ready:

```bash
oc get pods -n open-cluster-management-observability --watch

# Verify the observability addon is enabled on managed clusters
oc get managedclusteraddon -A | grep observability
```

Expected output:
```
production-east    observability-controller   True    5m
production-west    observability-controller   True    5m
```

Access the Grafana dashboard on the hub:

```bash
oc get route grafana -n open-cluster-management-observability \
  -o jsonpath='{.spec.host}'
```

> **Failure Mode -- Metrics Gap:** If a spoke cluster becomes unreachable, the Thanos sidecar on that spoke stops pushing metrics. The hub Grafana will show gaps in the graphs. When connectivity restores, Thanos backfills from the local Prometheus on the spoke (up to the retention window, typically 24h for the local write-ahead log). For persistent gaps, check `oc logs -n open-cluster-management-addon-observability -l component=metrics-collector` on the spoke.

### Step 6: Deploy Applications Across Clusters with ApplicationSets

Use ArgoCD ApplicationSets to deploy a sample multi-tier application to both spoke clusters, driven by Git and placement rules.

First, ensure OpenShift GitOps is installed on the hub and spoke clusters:

```bash
# Verify ArgoCD is running on the hub
oc get pods -n openshift-gitops | grep argocd

# Apply the ApplicationSet that targets production clusters
oc apply -f manifests/applicationset-multi-cluster.yaml
```

The ApplicationSet uses a cluster generator that reads ManagedCluster labels to determine targets:

```bash
# Verify ApplicationSet created Applications for each cluster
oc get applications -n openshift-gitops

# Check sync status
oc get applications -n openshift-gitops -o custom-columns=\
NAME:.metadata.name,\
SYNC:.status.sync.status,\
HEALTH:.status.health.status,\
CLUSTER:.spec.destination.server
```

Expected output:
```
NAME                          SYNC     HEALTH    CLUSTER
capstone-app-production-east  Synced   Healthy   https://api.production-east.example.com:6443
capstone-app-production-west  Synced   Healthy   https://api.production-west.example.com:6443
```

Deploy the sample application manifests that the ApplicationSet references:

```bash
# These manifests live in your Git repo and are referenced by the ApplicationSet
# For this capstone, apply them directly to see them in action
oc apply -f manifests/sample-app-namespace.yaml
oc apply -f manifests/sample-app-deployment.yaml
oc apply -f manifests/sample-app-service.yaml
oc apply -f manifests/sample-app-route.yaml
oc apply -f manifests/sample-app-networkpolicy.yaml
```

> **Failure Mode -- ApplicationSet Drift:** If someone manually modifies a resource on a spoke cluster, ArgoCD detects drift and flags the Application as "OutOfSync." With `selfHeal: true` (configured in our ApplicationSet), ArgoCD automatically reverts the change. Without it, drift accumulates silently. Always enable self-heal in production. Monitor with `oc get applications -n openshift-gitops -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.sync.status}{"\n"}{end}'`.

### Step 7: Set Up Disaster Recovery Between Clusters

Configure cross-cluster disaster recovery so workloads can fail over from the primary cluster (east) to the secondary (west).

```bash
# Install Velero on both spoke clusters (if not already present)
# This builds on L3-M3.3 where you learned Velero basics

# On the hub, deploy the DR policy that ensures Velero is configured on all production clusters
oc apply -f manifests/policy-velero-config.yaml

# Deploy the scheduled backup configuration
oc apply -f manifests/dr-backup-schedule.yaml
```

Test a failover scenario:

```bash
# Run the DR drill script
./scripts/dr-failover-drill.sh production-east production-west
```

The script performs these steps:
1. Takes a final Velero backup on production-east
2. Verifies the backup is stored in the shared S3 bucket
3. Simulates cluster failure by cordoning and draining workloads on production-east
4. Triggers a Velero restore on production-west
5. Updates the ApplicationSet placement to prefer production-west
6. Verifies the application is healthy on production-west
7. Updates DNS/Route to point to production-west

Manual failover procedure:

```bash
# 1. Verify the latest backup exists
oc login -u admin https://api.production-east.example.com:6443
velero backup get

# 2. On the west cluster, restore from backup
oc login -u admin https://api.production-west.example.com:6443
velero restore create --from-backup <latest-backup-name>

# 3. On the hub, update placement to exclude the failed cluster
oc login -u admin https://api.hub-cluster.example.com:6443
oc label managedcluster production-east status=failed --overwrite

# 4. Verify the ApplicationSet reacts by removing the east Application
oc get applications -n openshift-gitops

# 5. Verify workloads are running on west
oc login -u admin https://api.production-west.example.com:6443
oc get pods -n capstone-app
```

> **Failure Mode -- Split Brain:** The most dangerous DR scenario is when the hub loses connectivity to a spoke but the spoke is still running. Workloads on both clusters may serve traffic simultaneously with inconsistent data. Mitigate this with:
> - **Fencing:** Automatically cordon the suspect cluster via STONITH-style mechanisms
> - **Quorum:** Use an external arbiter (e.g., a third-site witness) to determine which cluster is authoritative
> - **Data replication:** Use synchronous replication for stateful workloads (e.g., CrunchyData PostgreSQL with streaming replication) so data consistency is maintained
>
> Always test your DR procedures regularly. Schedule quarterly DR drills as part of your operational runbook.

### Step 8: Production Hardening and Operational Readiness

Apply final production-hardening configurations:

```bash
# Deploy alerting rules for multi-cluster platform health
oc apply -f manifests/alerting-rules.yaml

# Deploy the platform health dashboard
oc apply -f manifests/grafana-dashboard-platform.yaml
```

Verify the complete platform:

```bash
# Run the platform verification script
./scripts/verify-platform.sh
```

## Verification

Run the following checks to confirm your multi-cluster platform is fully operational:

```bash
# 1. All managed clusters are joined and available
oc get managedclusters -o custom-columns=\
NAME:.metadata.name,\
JOINED:.status.conditions[?(@.type==\"ManagedClusterJoined\")].status,\
AVAILABLE:.status.conditions[?(@.type==\"ManagedClusterConditionAvailable\")].status

# 2. All policies are evaluated (Compliant or NonCompliant with inform)
oc get policy -A -o custom-columns=\
NAMESPACE:.metadata.namespace,\
NAME:.metadata.name,\
COMPLIANT:.status.compliant

# 3. Observability is collecting metrics from all clusters
oc get managedclusteraddon -A | grep observability

# 4. ApplicationSets have generated Applications for all target clusters
oc get applications -n openshift-gitops

# 5. Sample app is reachable on all spoke clusters
for cluster in production-east production-west; do
  echo "--- $cluster ---"
  APP_URL=$(oc get application capstone-app-${cluster} -n openshift-gitops \
    -o jsonpath='{.status.sync.revision}')
  echo "Sync revision: $APP_URL"
done

# 6. Velero backups are completing successfully
oc login -u admin https://api.production-east.example.com:6443
velero backup get --selector app=capstone-app

# 7. Check the Web Console
echo "Hub Console: $(oc whoami --show-console)"
echo "Navigate to: All Clusters > Overview for the multi-cluster dashboard"
```

### Verification Checklist

- [ ] Hub cluster shows all managed clusters as "Available"
- [ ] Governance policies are evaluated on all clusters
- [ ] Multi-cluster Grafana shows metrics from all clusters
- [ ] ApplicationSet has created ArgoCD Applications for each target cluster
- [ ] Applications are "Synced" and "Healthy" on all clusters
- [ ] Velero backups complete successfully on a schedule
- [ ] DR failover drill completed successfully
- [ ] DNS/Route failover points to the correct cluster
- [ ] Alerting rules fire correctly (test with a synthetic alert)

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift (RHACM) |
|--------|-----------|-------------------|
| Multi-cluster management | Manual kubeconfig switching; KubeFed (deprecated) | ManagedCluster CRDs with automatic agent registration |
| Cluster inventory | External CMDB or spreadsheet | ManagedClusterSets with labels, live status |
| Policy governance | Install OPA/Gatekeeper per cluster, no aggregation | Centralized policy engine with templates and compliance dashboard |
| Policy remediation | Manual or per-cluster tooling | `inform` or `enforce` per policy, hub-driven |
| Cross-cluster monitoring | Prometheus federation or per-cluster Thanos | Integrated Thanos with automatic metric collection |
| Multi-cluster alerting | AlertManager per cluster, manual aggregation | Centralized AlertManager with multi-cluster context |
| Application deployment | ArgoCD with manual cluster registration | ApplicationSets with ManagedCluster-aware generators |
| Workload placement | Manual target selection | Label-based Placement and PlacementRules |
| Disaster recovery | Velero per cluster, manual restore | Coordinated backup/restore with policy-driven failover |
| Cluster upgrades | Manual, per cluster | Orchestrated from hub with rolling upgrade strategies |
| Compliance reporting | Build custom tooling | Built-in compliance dashboard with CIS/NIST frameworks |
| Hub-spoke communication | N/A (no native hub-spoke) | Encrypted gRPC channel via klusterlet agent |

## Key Takeaways

- RHACM transforms multi-cluster Kubernetes from a manual operational burden into a governed, observable, and automated platform. The hub-spoke model provides a single control plane for cluster lifecycle, policy enforcement, and workload distribution.

- Policy-based governance is the foundation of multi-cluster security at scale. Rather than configuring each cluster individually (the K8s approach), RHACM policies declare the desired state and enforce or audit compliance across all clusters simultaneously.

- ApplicationSets with cluster generators eliminate the need to manually register clusters with ArgoCD. When a new cluster joins the hub and matches the label selector, workloads are automatically deployed -- this is the GitOps promise fulfilled at multi-cluster scale.

- Disaster recovery in a multi-cluster environment requires more than just backups. You need coordinated failover procedures, data replication strategies for stateful workloads, split-brain prevention, and regular DR drills. RHACM provides the orchestration layer, but you must design the data consistency model.

- Multi-cluster observability with Thanos aggregation gives operators a single-pane-of-glass view across all clusters. Combined with multi-cluster alerting rules, this enables proactive issue detection before users are affected.

## Cleanup

```bash
# Log in to the hub cluster
oc login -u admin https://api.hub-cluster.example.com:6443

# Remove ApplicationSets (this removes all generated Applications)
oc delete applicationset capstone-multi-cluster-app -n openshift-gitops

# Remove policies
oc delete policy --all -n platform-policies
oc delete namespace platform-policies

# Remove observability
oc delete multiclusterobservability observability
oc delete namespace open-cluster-management-observability

# Remove managed cluster set binding and set
oc delete managedclustersetbinding production-clusters -n openshift-gitops
oc delete managedclusterset production-clusters

# Remove sample app from spoke clusters
for ctx in production-east production-west; do
  oc login -u admin https://api.${ctx}.example.com:6443
  oc delete namespace capstone-app
done

# Optionally detach spoke clusters (from hub)
oc login -u admin https://api.hub-cluster.example.com:6443
oc delete managedcluster production-east
oc delete managedcluster production-west

# Remove Velero backups
velero backup delete --all --confirm

# Remove alerting rules and dashboards
oc delete -f manifests/alerting-rules.yaml
oc delete -f manifests/grafana-dashboard-platform.yaml
```

> **Note:** Deleting `ManagedCluster` resources triggers the klusterlet removal on the spoke clusters. Wait for the detach process to complete before decommissioning spoke clusters.

## Next Steps

**Tutorial Complete!**

Congratulations -- you have completed the entire OpenShift Tutorial, from Level 1 Foundations through Level 3 Expert. You now have hands-on experience with:

- **Level 1:** Platform fundamentals -- projects, RBAC, SCCs, builds, routes, storage, monitoring
- **Level 2:** Real-world workflows -- CI/CD pipelines, operators, service mesh, serverless, security hardening
- **Level 3:** Production operations -- cluster administration, multi-cluster management, performance tuning, disaster recovery, and this capstone multi-cluster platform

### Recommended Next Steps for Your Career

1. **Get certified:** Pursue the Red Hat Certified Specialist in OpenShift Administration (EX280) or the Red Hat Certified Engineer (RHCE) with OpenShift specialization.

2. **Build your own operators:** Extend the Operator SDK knowledge from L2-M2.4 to build domain-specific operators for your organization's workloads.

3. **Contribute to the community:** Share your experience through blog posts, conference talks, or contributions to OpenShift-related open source projects.

4. **Stay current:** OpenShift releases every ~4 months. Follow the [OpenShift release notes](https://docs.openshift.com/container-platform/latest/release_notes/ocp-4-release-notes.html) and test new features in a dev environment.

5. **Practice disaster recovery:** Schedule regular DR drills using the procedures from L3-M3.3 and this capstone. The worst time to test your DR plan is during an actual disaster.
