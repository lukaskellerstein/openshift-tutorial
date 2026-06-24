# L1-M1.2 — Installing OpenShift Local (CRC)

**Level:** Foundations
**Duration:** 30 min

## Overview

You already know how to spin up a local Kubernetes cluster with Minikube, kind, or k3d. OpenShift Local (formerly CodeReady Containers, still called `crc` on the CLI) gives you the same thing for OpenShift -- a single-node cluster running on your laptop. This lesson walks you through installing CRC, starting the cluster, logging in via both CLI and Web Console, and verifying that everything is working.

## Prerequisites

- Completed: [L1-M1.1 — Architecture Overview](../1_architecture_overview/README.md)
- A workstation meeting the minimum resource requirements (see below)
- A Red Hat account (free) to download CRC -- sign up at <https://console.redhat.com>

## K8s Context

In Kubernetes, you have several lightweight options for local clusters:

- **Minikube** -- runs a single-node cluster in a VM or container
- **kind** (Kubernetes IN Docker) -- runs control plane and workers as Docker containers
- **k3d** -- runs k3s (lightweight K8s) in Docker containers

All of these give you a working Kubernetes API server, scheduler, and kubelet. You interact with them using `kubectl` and a kubeconfig that the tool generates for you.

OpenShift Local (CRC) does the same thing, but it runs a full OpenShift 4.x cluster -- including the OAuth server, built-in image registry, the HAProxy router, the Web Console, Operator Lifecycle Manager, and all the OpenShift-specific controllers. This is why it has significantly higher resource requirements than Minikube or kind.

## Concepts

### What Is CRC?

CRC (Code Ready Containers) is Red Hat's tool for running a minimal, pre-configured OpenShift 4 cluster on your local machine. Under the hood, it runs a single-node OpenShift cluster inside a virtual machine.

Key things to understand:

- **It is a full OpenShift cluster**, not a stripped-down version. Every OpenShift API and operator is available.
- **It runs in a VM**, managed by the system's native hypervisor (HyperKit/Virtualization.framework on macOS, libvirt on Linux, Hyper-V on Windows).
- **It is a single-node cluster** -- the same node acts as both control plane and worker. This is fine for learning but not representative of production topology.
- **It ships a pre-built VM image** (called a "bundle") that contains a specific OpenShift version. You update the OpenShift version by downloading a new CRC release.
- **It includes a pull secret** mechanism -- you need a pull secret from Red Hat to pull the OpenShift container images.

### Resource Requirements

CRC is heavier than Minikube because it runs the full OpenShift stack. Here are the minimum and recommended requirements:

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPUs | 4 cores | 6+ cores |
| RAM | 9 GB (assigned to VM) | 16+ GB total system RAM |
| Disk | 35 GB | 50+ GB (images and builds consume space) |
| OS | macOS 12+, RHEL/Fedora/Ubuntu, Windows 10+ | Same |

> **Why so much?** OpenShift runs dozens of system pods (OAuth server, registry, router, monitoring, console, OLM, etc.) even at idle. This is the price of having a full platform on your laptop. Compare with Minikube, which runs just the core K8s components.

### CRC vs Minikube

| Aspect | Minikube / kind / k3d | CRC (OpenShift Local) |
|--------|----------------------|----------------------|
| What you get | Vanilla Kubernetes | Full OpenShift 4.x |
| Resource footprint | ~2 CPU, 2-4 GB RAM | ~4 CPU, 9+ GB RAM |
| CLI tool | `kubectl` | `oc` (superset of `kubectl`) |
| Auth | kubeconfig (no login flow) | OAuth login (`oc login`) |
| Web UI | K8s Dashboard (optional) | Full Web Console (built-in) |
| Ingress | Install an Ingress controller | HAProxy router pre-installed |
| Registry | Optional add-on | Built-in image registry |
| Time to start | ~1 minute | ~5-8 minutes |

## Step-by-Step

### Step 1: Download CRC

Go to <https://console.redhat.com/openshift/create/local> and download the CRC binary for your operating system. You will also need to copy your **pull secret** from the same page -- save it somewhere accessible.

On macOS, you can also install CRC via Homebrew:

```bash
brew install --cask crc
```

On Linux (Fedora/RHEL):

```bash
# Download the tar.gz from the Red Hat console, then:
tar xvf crc-linux-amd64.tar.xz
sudo mv crc-linux-*-amd64/crc /usr/local/bin/
```

Verify the binary is on your PATH:

```bash
crc version
```

Expected output (version numbers will vary):

```
CRC version: 2.44.0+c28cdb
OpenShift version: 4.16.7
Podman version: 5.0.1
```

### Step 2: Run CRC Setup

The `crc setup` command prepares your system -- it configures the hypervisor, sets up networking, and downloads the OpenShift VM bundle. This is a one-time operation.

```bash
crc setup
```

This will:

1. Check your system meets the requirements
2. Set up the hypervisor (HyperKit/Virtualization.framework on macOS, libvirt on Linux)
3. Download the OpenShift VM bundle (~4 GB)
4. Configure DNS and networking
5. Create the CRC configuration directory (`~/.crc/`)

Expected output (abbreviated):

```
INFO Using bundle path /Users/<you>/.crc/cache/crc_<platform>_amd64.crcbundle
INFO Checking minimum RAM requirements
INFO Checking if running as non-root
INFO Checking if crc-admin-helper executable is cached
INFO Checking if running on a supported CPU architecture
INFO Checking if HyperKit is installed
...
INFO Setup is complete, you can now run 'crc start' to start the instance
```

> **Note:** `crc setup` needs to run only once. If you upgrade CRC later, run `crc setup` again to apply the new configuration.

### Step 3: Configure Resources (Optional)

Before starting the cluster, you can adjust the resources allocated to the VM. If your machine has enough resources, increasing CPU and memory improves the experience significantly:

```bash
# View current configuration
crc config view

# Increase CPUs (default is 4)
crc config set cpus 6

# Increase memory in MiB (default is 9216, i.e., 9 GB)
crc config set memory 14336

# Increase disk size in GB (default is 31)
crc config set disk-size 50
```

> **Tip:** If you plan to run workloads with builds and multiple pods, bumping memory to 14 GB (14336 MiB) makes a noticeable difference. The default 9 GB is tight for anything beyond basic exploration.

### Step 4: Start the Cluster

Start the OpenShift cluster. The first start takes 5-10 minutes as it boots the VM and waits for all operators to stabilize.

```bash
crc start
```

When prompted, paste the pull secret you copied from the Red Hat console in Step 1.

Expected output (abbreviated):

```
INFO Checking if running as non-root
INFO Checking minimum RAM requirements
INFO Checking if HyperKit is installed
...
INFO Starting OpenShift instance
INFO Waiting for the cluster to be started...
INFO All operators are available. Ensuring stability...
INFO Operators are stable (2/3)...
INFO Operators are stable (3/3)...
INFO Adding crc-admin and crc-developer contexts to kubeconfig...
Started the OpenShift cluster.

The server is accessible via web console at:
  https://console-openshift-console.apps-crc.testing

Log in as administrator:
  Username: kubeadmin
  Password: AbCdE-FgHiJ-KlMnO-PqRsT

Log in as user:
  Username: developer
  Password: developer

Use the 'oc' command line interface:
  eval $(crc oc-env)
  oc login -u developer https://api.crc.testing:6443
```

> **Important:** Save the `kubeadmin` password shown in the output. It is unique to your CRC instance and is needed for cluster admin access.

### Step 5: Configure Your Shell

CRC ships its own `oc` binary. You need to add it to your PATH by running the `crc oc-env` command:

```bash
eval $(crc oc-env)
```

Verify the `oc` binary is now available:

```bash
oc version
```

Expected output:

```
Client Version: 4.16.7
Kustomize Version: v5.0.4-0.20230601165947-6ce0bf390ce3
Server Version: 4.16.7
Kubernetes Version: v1.29.7+6abe8a1
```

> **Tip:** Add `eval $(crc oc-env)` to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.) so the `oc` binary is available in every new terminal session.

### Step 6: Log In via CLI

Log in as the `developer` user (a regular user with limited permissions):

```bash
oc login -u developer -p developer https://api.crc.testing:6443
```

Expected output:

```
Login successful.

You don't have any projects. You can try to create a new project, by running

    oc new-project <projectname>
```

Now verify your identity:

```bash
oc whoami
```

```
developer
```

Try logging in as `kubeadmin` (cluster administrator):

```bash
oc login -u kubeadmin -p <password-from-crc-start> https://api.crc.testing:6443
```

```
Login successful.

You have access to 68 projects, the list has been suppressed. You can list all projects with 'oc projects'.

Using project "default".
```

> **K8s comparison:** In vanilla Kubernetes with Minikube, you just run `kubectl` and it picks up the kubeconfig -- there is no login step. OpenShift has a built-in OAuth server, so you authenticate with `oc login` to get a token. This token is stored in your kubeconfig automatically.

Switch back to the `developer` user for the rest of this tutorial:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
```

### Step 7: Log In via Web Console

Open the OpenShift Web Console in your browser:

```bash
crc console
```

Or navigate directly to: <https://console-openshift-console.apps-crc.testing>

> **Note:** Your browser will warn about an untrusted certificate. This is expected -- CRC uses self-signed certificates. Accept the warning and proceed.

1. You will see the OpenShift login page with an option to log in with `htpasswd_provider`
2. Log in as `developer` / `developer`
3. You will land in the **Developer** perspective of the Web Console
4. Switch to the **Administrator** perspective using the dropdown in the upper-left corner (you will need to log in as `kubeadmin` for full admin access)

### Step 8: Explore Basic Cluster State

Now that you are logged in, explore the cluster:

```bash
# List all nodes (CRC has just one)
oc get nodes
```

```
NAME                 STATUS   ROLES                         AGE   VERSION
crc-dzk9v-master-0   Ready    control-plane,master,worker   30d   v1.29.7+6abe8a1
```

```bash
# List all projects (namespaces) -- there are many system projects
oc get projects | head -20
```

```
NAME                                               DISPLAY NAME   STATUS
default                                                           Active
kube-node-lease                                                   Active
kube-public                                                       Active
kube-system                                                       Active
openshift                                                         Active
openshift-apiserver                                               Active
openshift-authentication                                          Active
openshift-cluster-machine-approver                                Active
openshift-cluster-node-tuning-operator                            Active
openshift-console                                                 Active
openshift-controller-manager                                      Active
...
```

```bash
# Check the cluster version
oc get clusterversion
```

```
NAME      VERSION   AVAILABLE   PROGRESSING   SINCE   STATUS
version   4.16.7    True        False         30d     Cluster version is 4.16.7
```

```bash
# Check the status of the OpenShift web console
oc get routes -n openshift-console
```

```
NAME        HOST/PORT                                        PATH  SERVICES    PORT   TERMINATION          WILDCARD
console     console-openshift-console.apps-crc.testing              console     https  reencrypt/Redirect   None
downloads   downloads-openshift-console.apps-crc.testing            downloads   http   edge/Redirect        None
```

### Step 9: Manage the Cluster Lifecycle

Here are the essential commands for managing your CRC cluster:

```bash
# Check CRC status
crc status
```

```
CRC VM:          Running
OpenShift:       Running (v4.16.7)
RAM Usage:       9216 MiB / 14336 MiB
Disk Usage:      18.5 GB / 50 GB (Inside the CRC VM)
Cache Usage:     19.2 GB
Cache Directory: /Users/<you>/.crc/cache
```

```bash
# Stop the cluster (preserves all state -- like suspending a VM)
crc stop

# Start it again (faster than the first start)
crc start

# Delete the cluster entirely (destroys all data)
crc delete

# After delete, you need 'crc start' again (which recreates from the bundle)
```

> **Important:** Always use `crc stop` rather than `crc delete` when you are done for the day. `crc stop` preserves your projects, deployments, and configurations. `crc delete` wipes everything and you start from scratch.

## Verification

Run the verification script included with this lesson to confirm everything is working:

```bash
# From this lesson's directory
bash scripts/verify-crc.sh
```

Or run these checks manually:

```bash
# 1. CRC is running
crc status | grep "OpenShift:.*Running"

# 2. oc is available
oc version --client

# 3. Can log in as developer
oc login -u developer -p developer https://api.crc.testing:6443

# 4. Can query the API server
oc get nodes

# 5. Web Console route exists
oc login -u kubeadmin -p $(cat ~/.crc/machines/crc/kubeadmin-password 2>/dev/null || echo '<your-kubeadmin-password>') https://api.crc.testing:6443
oc get routes -n openshift-console

# 6. Create and delete a test project
oc login -u developer -p developer https://api.crc.testing:6443
oc new-project crc-test
oc get project crc-test
oc delete project crc-test
```

All six checks should succeed. If any fail, see the troubleshooting tips below.

### Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| `crc start` hangs | Not enough resources | Increase CPUs/RAM: `crc config set cpus 6` |
| `oc login` fails with connection refused | Cluster not fully started | Wait a few minutes, check `crc status` |
| Browser cannot reach console | DNS not configured | Run `crc setup` again, or add hosts entry manually |
| "x509: certificate signed by unknown authority" | Expected with self-signed certs | Use `oc login --insecure-skip-tls-verify` (dev only) |
| Operators stuck in `Progressing` | First boot needs time | Wait 5-10 min, run `oc get clusteroperators` to check |
| VM fails to start | Hypervisor issue | Check hypervisor is installed: `crc setup` |
| Pull secret error | Invalid or expired pull secret | Download a fresh pull secret from console.redhat.com |

## K8s vs OpenShift Comparison

| Aspect | Kubernetes (Minikube/kind) | OpenShift (CRC) |
|--------|---------------------------|-----------------|
| Install tool | `minikube start` / `kind create cluster` | `crc setup && crc start` |
| Minimum RAM | 2-4 GB | 9 GB |
| Minimum CPUs | 2 | 4 |
| Disk space | ~5 GB | ~35 GB |
| Time to start | ~1 min | ~5-8 min |
| Authentication | kubeconfig (no login) | OAuth server + `oc login` |
| CLI | `kubectl` | `oc` (includes `kubectl`) |
| Web UI | Dashboard (optional install) | Full Web Console (pre-installed) |
| Container runtime | Docker / containerd | CRI-O |
| System namespaces | ~4 (kube-system, etc.) | ~60+ (openshift-*, kube-*) |
| Built-in features | Core K8s only | Registry, Router, OAuth, OLM, Console, Monitoring |

## Key Takeaways

- **CRC gives you a full OpenShift 4.x cluster** on your laptop -- not a stripped-down version. Every API and operator you would find in a production cluster is present.
- **Resource requirements are significantly higher** than Minikube or kind because OpenShift runs many platform services (OAuth, router, registry, console, OLM, monitoring) out of the box.
- **Authentication works differently from vanilla K8s.** OpenShift has a built-in OAuth server, so you use `oc login` to authenticate instead of just relying on kubeconfig certificates.
- **Two default users exist in CRC:** `developer` (regular user) and `kubeadmin` (cluster admin). In production, you would configure external identity providers.
- **Use `crc stop` to pause and `crc start` to resume** -- this preserves your work. Only use `crc delete` when you want a fresh start.

## Cleanup

CRC itself does not create any OpenShift resources that need cleanup. If you created the test project during verification:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc delete project crc-test
```

To stop the cluster when you are done (preserves state):

```bash
crc stop
```

To completely remove CRC and free all disk space:

```bash
crc delete
crc cleanup
```

## Next Steps

In [L1-M1.3 — CLI Tools: oc vs kubectl](../3_oc_vs_kubectl/README.md), you will explore the `oc` command in detail -- how it extends `kubectl`, what extra commands it provides, and when to use each tool. You will also learn about `oc` features like `oc new-app`, `oc new-project`, `oc adm`, and `oc debug` that have no `kubectl` equivalent.
