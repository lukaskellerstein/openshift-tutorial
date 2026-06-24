# L3-M1.1 — Installation Methods

**Level:** Expert
**Duration:** 1 hr

## Overview

In Kubernetes, you likely bootstrapped your clusters with `kubeadm`, `kops`, or a managed service like EKS/GKE/AKS. OpenShift replaces all of those with its own installer (`openshift-install`) and introduces two fundamentally different approaches: IPI (Installer-Provisioned Infrastructure) and UPI (User-Provisioned Infrastructure). This lesson dissects both methods, compares them to what you know from the Kubernetes world, walks through the `install-config.yaml` structure, and covers the newer agent-based installer. By the end, you will understand which installation method to choose for a given environment and how to plan a production-grade OpenShift deployment.

## Prerequisites

- Completed: All Level 1 and Level 2 modules
- Strong understanding of Kubernetes cluster bootstrapping (kubeadm, kops, or managed K8s)
- Familiarity with infrastructure concepts: DNS, load balancers, DHCP, PXE boot
- Access to cloud provider documentation (AWS, Azure, GCP) or bare metal/vSphere environment
- An understanding of TLS certificates and PKI fundamentals

## K8s Context

In vanilla Kubernetes, cluster installation is a "bring your own adventure" experience:

- **kubeadm** handles the control plane bootstrap but you provision machines yourself, configure networking, install a CNI plugin, set up a load balancer for the API server, and manage certificates. It is deliberately modular --- you assemble the pieces.
- **kops** automates cloud infrastructure provisioning (primarily AWS) and runs kubeadm under the hood, giving you a more opinionated but still flexible path.
- **Managed services** (EKS, GKE, AKS) hide the control plane entirely --- you only manage worker nodes and pay for the abstraction.

In all cases, day-2 upgrades, certificate rotation, and OS management are separate concerns you handle with external tools (Ansible, Terraform, cloud provider APIs).

OpenShift takes a radically different approach: the installer provisions infrastructure, bootstraps the cluster, configures the OS (RHCOS), sets up monitoring, logging, an internal registry, an OAuth server, and an ingress router --- all as a single atomic operation. Understanding why OpenShift made this choice is key to operating it effectively.

## Concepts

### The OpenShift Installer (`openshift-install`)

The `openshift-install` binary is the single entry point for creating OpenShift clusters. Unlike kubeadm (which only handles the Kubernetes control plane), `openshift-install` manages the full stack:

```
+------------------------------------------------------------------+
|                      openshift-install                           |
|                                                                  |
|  +------------------+  +------------------+  +----------------+  |
|  | Infrastructure   |  | Bootstrap        |  | Day-1          |  |
|  | Provisioning     |  | Machine          |  | Operators      |  |
|  | (Terraform/API)  |  | (temporary node) |  | (CVO, MCO...)  |  |
|  +------------------+  +------------------+  +----------------+  |
|                                                                  |
|  +------------------+  +------------------+  +----------------+  |
|  | RHCOS Images     |  | Ignition         |  | Certificate    |  |
|  | (immutable OS)   |  | Configs          |  | Management     |  |
|  +------------------+  +------------------+  +----------------+  |
+------------------------------------------------------------------+
```

### IPI vs UPI: Two Philosophies

**IPI (Installer-Provisioned Infrastructure)** is the "batteries included" approach. The installer creates all cloud resources (VPCs, subnets, security groups, load balancers, DNS records, compute instances) using embedded Terraform modules (or cloud APIs). You provide credentials and a config file; it handles everything else.

**UPI (User-Provisioned Infrastructure)** is the "bring your own infrastructure" approach. You provision the machines, DNS, load balancers, and networking yourself. The installer generates Ignition configs that you feed to RHCOS machines during boot. This gives you full control but requires deep infrastructure knowledge.

```
IPI Flow:
                                                    
  install-config.yaml                               
        |                                           
        v                                           
  openshift-install create cluster                  
        |                                           
        +---> Creates infrastructure (Terraform/API)
        +---> Provisions bootstrap machine          
        +---> Boots control plane nodes (Ignition)  
        +---> Installs day-1 operators              
        +---> Removes bootstrap machine             
        +---> Cluster ready                         
                                                    
UPI Flow:
                                                    
  install-config.yaml                               
        |                                           
        v                                           
  openshift-install create manifests                
        |                                           
        v                                           
  openshift-install create ignition-configs         
        |                                           
        v                                           
  YOU provision: DNS, LB, machines, storage         
  YOU boot machines with Ignition configs           
        |                                           
        v                                           
  openshift-install wait-for bootstrap-complete     
        |                                           
        v                                           
  YOU remove the bootstrap machine                  
        |                                           
        v                                           
  openshift-install wait-for install-complete       
```

### The Bootstrap Process

Both IPI and UPI use a temporary bootstrap machine that runs a minimal Kubernetes API server. The bootstrap machine:

1. Boots from an RHCOS image with an Ignition config
2. Starts a temporary etcd and API server
3. Creates the real control plane nodes
4. Hands off to the permanent control plane
5. Is destroyed after the control plane is healthy

```
                   Bootstrap Sequence
                                                    
  +-------------------+                             
  | Bootstrap Machine |----+                        
  | (temporary)       |    |                        
  |  - etcd (temp)    |    |  1. Bootstrap API      
  |  - API (temp)     |    |     serves initial     
  |  - MCS            |    |     machine configs    
  +-------------------+    |                        
                           |                        
      +--------------------+--------------------+   
      |                    |                    |   
      v                    v                    v   
  +-----------+    +-----------+    +-----------+   
  | Master 0  |    | Master 1  |    | Master 2  |   
  | (RHCOS)   |    | (RHCOS)   |    | (RHCOS)   |   
  |  - etcd   |    |  - etcd   |    |  - etcd   |   
  |  - API    |    |  - API    |    |  - API    |   
  +-----------+    +-----------+    +-----------+   
      2. Permanent control plane forms              
      3. Bootstrap machine is removed               
```

### Agent-Based Installer

The agent-based installer is a newer method designed primarily for disconnected and bare metal environments. Instead of relying on Terraform or manual PXE boot, it creates a bootable ISO that contains the Assisted Installer agent. Machines boot from this ISO, discover each other, and self-assemble into a cluster.

```
Agent-Based Flow:
                                                    
  install-config.yaml + agent-config.yaml           
        |                                           
        v                                           
  openshift-install agent create image              
        |                                           
        v                                           
  Boot all machines from the agent ISO              
        |                                           
        v                                           
  Agents discover each other via rendezvous IP      
        |                                           
        v                                           
  Assisted Installer validates and installs         
        |                                           
        v                                           
  Cluster ready                                     
```

Key advantages of the agent-based installer:
- No bootstrap machine needed (agents coordinate among themselves)
- Works in disconnected/air-gapped environments
- No cloud APIs or Terraform required
- Supports bare metal, vSphere, and platform `none`

### Supported Platforms

| Platform | IPI | UPI | Agent-Based | Notes |
|----------|-----|-----|-------------|-------|
| AWS | Yes | Yes | No | Most mature IPI support |
| Azure | Yes | Yes | No | Includes Azure Stack Hub |
| GCP | Yes | Yes | No | Supports Shared VPC |
| vSphere | Yes | Yes | Yes | Requires vCenter for IPI |
| Bare Metal | Yes* | Yes | Yes | IPI uses BMC/IPMI |
| OpenStack | Yes | Yes | No | Red Hat OpenStack Platform |
| IBM Cloud | Yes | No | No | VPC infrastructure |
| Nutanix | Yes | No | Yes | AOS + Prism Central |
| None | No | Yes | Yes | Platform-agnostic |

*Bare metal IPI requires Baseboard Management Controller (BMC) access (IPMI/Redfish).

### RHCOS: The Immutable Node OS

Unlike Kubernetes where you can run any Linux distribution on nodes, OpenShift control plane nodes **must** run Red Hat Enterprise Linux CoreOS (RHCOS). Workers can run RHCOS or RHEL, but RHCOS is strongly recommended.

RHCOS is:
- **Immutable**: no package manager (`rpm-ostree` for atomic updates)
- **Configured via Ignition**: node configuration is declarative and applied at boot
- **Managed by the Machine Config Operator (MCO)**: changes are rolled out as MachineConfig resources
- **Auto-updating**: the OS updates are part of cluster upgrades (covered in L3-M1.2)

This is a fundamental difference from Kubernetes, where node OS management is entirely your responsibility.

### install-config.yaml Structure

The `install-config.yaml` is the single configuration file that drives the entire installation. It replaces the equivalent of kubeadm's `ClusterConfiguration`, cloud provider Terraform variables, and network configuration --- all in one file.

Key sections:

```yaml
apiVersion: v1
metadata:
  name: my-cluster            # Cluster name (used in DNS)
baseDomain: example.com        # Base domain (cluster API at api.<name>.<baseDomain>)

# Control plane configuration
controlPlane:
  name: master
  replicas: 3                  # Always 3 for production
  platform:
    aws:                       # Platform-specific machine config
      type: m6i.xlarge
      rootVolume:
        size: 120
        type: gp3

# Worker configuration
compute:
  - name: worker
    replicas: 3                # Minimum 2 for production
    platform:
      aws:
        type: m6i.2xlarge
        rootVolume:
          size: 120
          type: gp3

# Networking
networking:
  networkType: OVNKubernetes   # OVN-K or OpenShiftSDN
  clusterNetwork:
    - cidr: 10.128.0.0/14
      hostPrefix: 23
  serviceNetwork:
    - 172.30.0.0/16
  machineNetwork:
    - cidr: 10.0.0.0/16

# Platform-specific
platform:
  aws:
    region: us-east-1

# Pull secret (from cloud.redhat.com)
pullSecret: '...'

# SSH key for node access
sshKey: 'ssh-rsa ...'
```

### DNS Requirements

OpenShift has strict DNS requirements that differ significantly from a typical kubeadm setup:

| Record | Type | Target | Purpose |
|--------|------|--------|---------|
| `api.<cluster>.<domain>` | A/CNAME | Load balancer (API) | Kubernetes API access |
| `api-int.<cluster>.<domain>` | A/CNAME | Load balancer (API, internal) | Internal API access |
| `*.apps.<cluster>.<domain>` | A/CNAME | Load balancer (Ingress) | Route/Ingress wildcard |
| `etcd-<N>.<cluster>.<domain>` | A | Control plane node N | etcd peer communication (UPI) |
| `_etcd-server-ssl._tcp.<cluster>.<domain>` | SRV | etcd nodes | etcd service discovery (UPI) |

IPI creates these automatically. For UPI, you must create them before installation.

### Load Balancer Requirements

Two load balancers are required:

```
External LB (api.<cluster>.<domain>):
  - Port 6443 (API) --> Control plane nodes
  - Port 22623 (MCS) --> Control plane nodes (bootstrap only)
                                                    
Ingress LB (*.apps.<cluster>.<domain>):
  - Port 80  (HTTP)  --> Worker/infra nodes (router pods)
  - Port 443 (HTTPS) --> Worker/infra nodes (router pods)
```

### Failure Modes and Recovery

Understanding what can go wrong during installation is critical for production deployments:

**Bootstrap failures:**
- **Symptom**: `wait-for bootstrap-complete` times out
- **Diagnosis**: SSH into the bootstrap machine, check `journalctl -b -f -u bootkube.service`
- **Common causes**: DNS misconfiguration, unreachable machine config server, pull secret expired
- **Recovery**: Fix the root cause and re-run the installer from scratch (bootstrap is not resumable)

**Control plane failures:**
- **Symptom**: Not all control plane nodes join
- **Diagnosis**: Check Ignition config delivery, verify network connectivity to bootstrap MCS on port 22623
- **Common causes**: Firewall rules blocking port 22623 or 6443, incorrect Ignition configs
- **Recovery**: Re-provision the failed node with correct Ignition config

**Worker node failures:**
- **Symptom**: CSRs pending approval, nodes not joining
- **Diagnosis**: `oc get csr`, check for pending CSRs
- **Common causes**: Clock skew, DNS resolution failures, expired certificates
- **Recovery**: Approve CSRs with `oc adm certificate approve <csr-name>`, fix underlying issue

**Post-install operator degradation:**
- **Symptom**: `oc get clusteroperators` shows degraded operators
- **Diagnosis**: `oc describe co/<operator-name>`, check operator logs
- **Common causes**: Missing storage class (for image-registry), insufficient resources, network policy blocking
- **Recovery**: Address the specific operator's requirements (e.g., configure storage for registry)

## Step-by-Step

### Step 1: Examine the install-config.yaml Structure

The `install-config.yaml` is the foundation of every OpenShift installation. Let us examine a production-grade configuration for AWS IPI.

Review the sample config:

```bash
# View the production install-config for AWS IPI
cat manifests/install-config-aws-ipi.yaml
```

```yaml
# manifests/install-config-aws-ipi.yaml (excerpt)
apiVersion: v1
metadata:
  name: production-cluster
baseDomain: example.com
controlPlane:
  name: master
  replicas: 3
  platform:
    aws:
      type: m6i.xlarge
      rootVolume:
        size: 120
        type: gp3
        iops: 3000
      zones:
        - us-east-1a
        - us-east-1b
        - us-east-1c
compute:
  - name: worker
    replicas: 3
    platform:
      aws:
        type: m6i.2xlarge
        rootVolume:
          size: 250
          type: gp3
          iops: 3000
        zones:
          - us-east-1a
          - us-east-1b
          - us-east-1c
networking:
  networkType: OVNKubernetes
  clusterNetwork:
    - cidr: 10.128.0.0/14
      hostPrefix: 23
  serviceNetwork:
    - 172.30.0.0/16
  machineNetwork:
    - cidr: 10.0.0.0/16
platform:
  aws:
    region: us-east-1
pullSecret: '<your-pull-secret>'
sshKey: '<your-ssh-public-key>'
```

Key production considerations:
- **3 control plane nodes** spread across availability zones for HA
- **gp3 volumes** with explicit IOPS for predictable etcd performance
- **OVNKubernetes** as the network plugin (the modern default, replacing OpenShiftSDN)
- **Separate machine network CIDR** from cluster and service networks

### Step 2: Understand the IPI Installation Workflow

For IPI, the installer handles everything. Here is the exact sequence:

```bash
# 1. Create an installation directory
mkdir ~/ocp-install && cd ~/ocp-install

# 2. Place your install-config.yaml in the directory
cp install-config.yaml ~/ocp-install/

# 3. Run the installer (this will consume install-config.yaml)
# IMPORTANT: The installer DELETES install-config.yaml after reading it.
# Always keep a backup!
cp install-config.yaml install-config.yaml.bak

# 4. Create the cluster (IPI - full automation)
openshift-install create cluster --dir ~/ocp-install --log-level=info

# This will:
# - Create VPC, subnets, security groups, IAM roles
# - Launch a bootstrap EC2 instance
# - Launch 3 control plane EC2 instances
# - Launch 3 worker EC2 instances
# - Create Route53 DNS records
# - Create ELB/NLB load balancers
# - Wait for bootstrap to complete (~30 min)
# - Remove the bootstrap machine
# - Wait for all operators to be available (~15-45 min)

# 5. After completion, credentials are in:
# ~/ocp-install/auth/kubeconfig    - kubeconfig for cluster access
# ~/ocp-install/auth/kubeadmin-password - initial admin password
```

```bash
# Export kubeconfig and verify
export KUBECONFIG=~/ocp-install/auth/kubeconfig
oc whoami
# Output: system:admin

oc get nodes
# Output: 3 master + 3 worker nodes in Ready state

oc get clusterversion
# Output: cluster version and update availability

oc get clusteroperators
# Output: all cluster operators and their status
```

### Step 3: Understand the UPI Installation Workflow

UPI gives you full control but requires more manual steps. Here is the workflow:

```bash
# 1. Create manifests from install-config.yaml
openshift-install create manifests --dir ~/ocp-install

# This generates:
# ~/ocp-install/manifests/    - Kubernetes manifests
# ~/ocp-install/openshift/    - OpenShift-specific manifests

# 2. (Optional) Customize manifests before generating Ignition configs
# For example, remove machines/machinesets for UPI:
rm -f ~/ocp-install/openshift/99_openshift-cluster-api_master-machines-*.yaml
rm -f ~/ocp-install/openshift/99_openshift-cluster-api_worker-machineset-*.yaml

# 3. Generate Ignition configs
openshift-install create ignition-configs --dir ~/ocp-install

# This generates:
# ~/ocp-install/bootstrap.ign  - Bootstrap node config
# ~/ocp-install/master.ign     - Control plane node config
# ~/ocp-install/worker.ign     - Worker node config
# ~/ocp-install/auth/           - kubeconfig and kubeadmin password
```

For UPI, you must provision infrastructure yourself:

```bash
# Example: DNS records you must create (e.g., with Route53 CLI or your DNS provider)
# api.production-cluster.example.com     -> API load balancer
# api-int.production-cluster.example.com -> Internal API load balancer
# *.apps.production-cluster.example.com  -> Ingress load balancer

# Example: Load balancers you must create
# API LB:     TCP 6443 -> control plane nodes
#             TCP 22623 -> bootstrap + control plane nodes (MCS)
# Ingress LB: TCP 80 -> worker/infra nodes
#             TCP 443 -> worker/infra nodes

# Boot machines with Ignition configs
# For bare metal: PXE boot with RHCOS + Ignition
# For vSphere: Upload RHCOS OVA, set Ignition via vApp properties
# For cloud: Create instances with Ignition as user-data

# Wait for bootstrap to complete
openshift-install wait-for bootstrap-complete --dir ~/ocp-install --log-level=info
# This waits up to 30 minutes for the bootstrap process

# After bootstrap is complete, remove the bootstrap machine
# and update the API load balancer to remove the bootstrap target

# Approve worker CSRs (workers need manual CSR approval in UPI)
oc get csr -o go-template='{{range .items}}{{if not .status}}{{.metadata.name}}{{"\n"}}{{end}}{{end}}' | xargs oc adm certificate approve

# Wait for installation to complete
openshift-install wait-for install-complete --dir ~/ocp-install --log-level=info
```

### Step 4: Explore the Agent-Based Installer

The agent-based installer simplifies bare metal and disconnected installations:

```bash
# View the agent-config sample
cat manifests/agent-config-baremetal.yaml
```

```yaml
# The agent-config.yaml defines host-level configuration
# that the agent-based installer uses during discovery
```

```bash
# 1. Create both config files in your install directory
mkdir ~/ocp-agent-install && cd ~/ocp-agent-install
cp install-config.yaml agent-config.yaml ~/ocp-agent-install/

# 2. Generate the agent ISO
openshift-install agent create image --dir ~/ocp-agent-install

# This creates:
# ~/ocp-agent-install/agent.x86_64.iso  - Bootable ISO with embedded agents

# 3. Boot all machines from the ISO
# The machine with the rendezvous IP becomes the temporary coordinator

# 4. Monitor the installation
openshift-install agent wait-for bootstrap-complete --dir ~/ocp-agent-install
openshift-install agent wait-for install-complete --dir ~/ocp-agent-install
```

### Step 5: Compare install-config.yaml Across Platforms

Review the platform-specific install-config files to understand the differences:

```bash
# Compare AWS vs vSphere vs bare metal configurations
diff manifests/install-config-aws-ipi.yaml manifests/install-config-vsphere-ipi.yaml
diff manifests/install-config-aws-ipi.yaml manifests/install-config-baremetal-upi.yaml
```

Key platform differences:

| Aspect | AWS IPI | vSphere IPI | Bare Metal UPI |
|--------|---------|-------------|----------------|
| Machine types | EC2 instance types | CPU/memory/disk specs | Physical specs |
| Storage | EBS volumes (gp3) | VMDK via datastore | Local or SAN |
| DNS | Route53 (auto) | Manual or external | Manual |
| Load Balancer | ELB/NLB (auto) | HAProxy (manual) | HAProxy/MetalLB |
| Node provisioning | EC2 API | vCenter API | PXE/IPMI/BMC |

### Step 6: Validate a Cluster Post-Installation

After any installation method completes, run these validation steps:

```bash
# Check cluster version
oc get clusterversion
# Should show: Available=True, Progressing=False

# Check all cluster operators
oc get clusteroperators
# All should show: Available=True, Progressing=False, Degraded=False

# Check node health
oc get nodes -o wide
# All nodes should be Ready, correct roles, correct version

# Check critical pods
oc get pods -n openshift-etcd
oc get pods -n openshift-apiserver
oc get pods -n openshift-controller-manager
oc get pods -n openshift-ingress
oc get pods -n openshift-image-registry

# Run the cluster health check script
./scripts/validate-cluster.sh

# Check etcd health (critical for production)
oc rsh -n openshift-etcd $(oc get pods -n openshift-etcd -l app=etcd -o name | head -1) \
  etcdctl endpoint health --cluster

# Verify the web console is accessible
oc get routes -n openshift-console
# Access the console URL in your browser
```

### Step 7: Compare with kubeadm

To solidify the conceptual mapping, here is how an OpenShift IPI installation maps to what you would do with kubeadm:

```bash
# kubeadm equivalent steps (for mental comparison):
#
# 1. Provision VMs/machines           <- openshift-install does this (IPI)
# 2. Install container runtime        <- RHCOS ships CRI-O pre-installed
# 3. Install kubelet, kubeadm         <- RHCOS ships kubelet pre-configured
# 4. kubeadm init                     <- openshift-install create cluster
# 5. Install CNI (Calico, Flannel)    <- OVN-Kubernetes installed by default
# 6. kubeadm join (workers)           <- Workers auto-join via MCS + Ignition
# 7. Install Ingress controller       <- HAProxy router pre-installed
# 8. Install monitoring (Prometheus)  <- Monitoring stack pre-installed
# 9. Install dashboard                <- Web Console pre-installed
# 10. Configure auth                  <- OAuth server pre-installed
# 11. Set up certificate rotation     <- Handled by OpenShift operators
# 12. Configure node OS updates       <- MCO handles RHCOS updates
```

## Verification

After studying this lesson, verify your understanding by answering these questions and running these checks:

### Knowledge Verification

1. Can you explain the difference between IPI and UPI and when to use each?
2. Can you describe the bootstrap process and what happens if it fails?
3. Do you understand the DNS requirements for an OpenShift installation?
4. Can you explain why OpenShift uses RHCOS and how it differs from managing your own node OS?

### Practical Verification (on CRC or existing cluster)

```bash
# CRC is itself an OpenShift installation --- examine its configuration

# Check the cluster version and installation details
oc get clusterversion version -o yaml | grep -A5 "desired"

# View the install-config used (if available in the cluster)
oc get configmap -n kube-system cluster-config-v1 -o yaml

# Check the infrastructure platform
oc get infrastructure cluster -o jsonpath='{.status.platform}{"\n"}'
# CRC will show: None

# Check the network configuration
oc get network cluster -o yaml | grep -A10 "spec:"

# List the cluster operators --- these are the day-1 operators installed during setup
oc get clusteroperators --sort-by=.metadata.name

# Check for any degraded operators
oc get co -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Degraded")].status}{"\n"}{end}'

# Examine the machine config pool (MCO-managed node configuration)
oc get machineconfigpool
oc get machineconfig --sort-by=.metadata.creationTimestamp
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes (kubeadm/kops) | OpenShift (IPI/UPI) |
|--------|--------------------------|---------------------|
| Installer | `kubeadm init` / `kops create` | `openshift-install create cluster` |
| Infrastructure | Manual or Terraform | IPI: automated; UPI: manual |
| Node OS | Any Linux (Ubuntu, CentOS, etc.) | RHCOS (immutable, managed) |
| Node config | Ansible/Puppet/Chef + SSH | Ignition configs (declarative, boot-time) |
| CNI plugin | Choose and install yourself | OVN-Kubernetes pre-installed |
| Ingress | Install Nginx/Traefik yourself | HAProxy router pre-installed |
| Monitoring | Install Prometheus yourself | Prometheus + Grafana pre-installed |
| Authentication | Configure OIDC/webhook yourself | OAuth server pre-installed |
| Certificate mgmt | kubeadm certs + manual renewal | Automated operator-managed rotation |
| OS upgrades | apt/yum + reboot | MCO atomic updates (cluster upgrade) |
| Day-1 operators | Install yourself | ~30 operators installed automatically |
| Bootstrap | kubeadm init on first node | Temporary bootstrap machine (auto-removed) |
| Air-gap install | Possible but complex | Agent-based installer or mirrored registries |
| Minimum nodes | 1 (single node) | 3 masters + 2 workers (prod); 1 (SNO) |
| Upgrade path | kubeadm upgrade (manual) | OTA via CVO (over-the-air, managed) |

## Key Takeaways

- **IPI is the recommended path** for cloud environments where you want the installer to manage infrastructure end-to-end. It eliminates an entire class of infrastructure provisioning errors and produces a consistent, supportable cluster.
- **UPI is necessary** when you have strict infrastructure requirements (existing VPCs, specific network topologies, compliance constraints) or platforms where IPI is not supported. It requires deep infrastructure expertise but gives you full control.
- **The agent-based installer bridges the gap** for bare metal and disconnected environments, removing the need for a separate bootstrap machine and PXE infrastructure while still supporting air-gapped installations.
- **RHCOS and Ignition are fundamental architectural choices**, not optional features. The immutable OS + declarative configuration model eliminates configuration drift and enables atomic, cluster-wide upgrades --- something impossible with traditional K8s node management.
- **The install-config.yaml is the single source of truth** for cluster installation. Unlike kubeadm's multiple config files, Terraform variables, and Ansible inventories, OpenShift consolidates everything into one document --- understand its structure thoroughly.

## Cleanup

This lesson is primarily conceptual and does not create cluster resources. If you generated any local installer artifacts during exploration:

```bash
# Remove local installer directories
rm -rf ~/ocp-install
rm -rf ~/ocp-agent-install

# CAUTION: On a real cluster, the install directory contains:
#   auth/kubeconfig       - cluster admin credentials
#   auth/kubeadmin-password - initial admin password
#   metadata.json          - infrastructure identifiers needed for cluster destruction
#   terraform.tfstate      - Terraform state (IPI only)
#
# NEVER delete these files on a real cluster unless you have:
# 1. Exported credentials to a secure vault
# 2. Backed up metadata.json (needed for `openshift-install destroy cluster`)
# 3. Backed up terraform.tfstate (IPI only, needed for infrastructure teardown)

# To destroy an IPI cluster (this deletes ALL cloud resources):
# openshift-install destroy cluster --dir ~/ocp-install --log-level=info
```

## Next Steps

In **L3-M1.2 --- Cluster Upgrades and Lifecycle**, you will learn how OpenShift handles over-the-air (OTA) upgrades through the Cluster Version Operator (CVO), upgrade channels (stable, fast, candidate), pre-upgrade health checks, and what to do when an upgrade goes wrong. The immutable RHCOS nodes and operator-managed architecture you learned about in this lesson are what make zero-downtime rolling upgrades possible.
