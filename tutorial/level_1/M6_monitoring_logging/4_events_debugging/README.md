# L1-M6.4 — Events & Debugging

**Level:** Foundations
**Duration:** 20 min

## Overview

When something goes wrong in Kubernetes, you reach for `kubectl describe`, `kubectl logs`, and `kubectl exec`. OpenShift keeps all of those (via `oc`) and adds purpose-built debugging tools: `oc debug` creates a disposable copy of a pod with a root shell, `oc rsh` gives you a remote shell without the `-- /bin/sh` boilerplate, and `oc debug node/` drops you onto a node's filesystem for host-level troubleshooting. This lesson teaches a systematic debugging workflow using a deliberately broken deployment.

## Prerequisites

- Completed: L1-M3.1 (oc new-app & Source-to-Image)
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI installed and on your PATH

## K8s Context

In Kubernetes, your debugging toolkit is:

- `kubectl get events` -- see cluster events (scheduling, pulling images, container crashes).
- `kubectl logs <pod>` -- read container stdout/stderr.
- `kubectl exec -it <pod> -- /bin/sh` -- open a shell inside a running container.
- `kubectl describe <resource>` -- see resource details and recent events.
- `kubectl top nodes` / `kubectl top pods` -- resource usage (requires metrics-server).

These all work. But there is no built-in way to create a debug copy of a pod, SSH into a node through the API server, or get a root shell when your container runs as non-root. You have to work around these limitations with `kubectl debug` (added in K8s 1.18 as alpha, still evolving) or by SSHing into nodes directly.

## Concepts

### oc debug -- disposable debug pods

`oc debug deployment/<name>` creates a temporary copy of a pod from the deployment's template, overrides the entrypoint to `/bin/sh`, and gives you an interactive shell. When you exit, the debug pod is deleted. This is invaluable when:

- The container's entrypoint crashes immediately (CrashLoopBackOff) -- you cannot `exec` into a crashing container, but `oc debug` starts a fresh copy with a shell instead of the failing entrypoint.
- You need root access -- `oc debug` can run as root with `--as-root`, bypassing the restricted SCC for investigation purposes.
- You want to inspect the container image without affecting the running workload.

### oc rsh -- simplified remote shell

`oc rsh <pod>` is shorthand for `oc exec -it <pod> -- /bin/sh`. Less typing, same result. It connects to a running pod -- unlike `oc debug`, which creates a new pod.

### oc debug node/ -- node-level access

`oc debug node/<node-name>` creates a privileged pod on the specified node with the host filesystem mounted at `/host`. This replaces SSH access to nodes. You can inspect systemd journals, check kubelet logs, examine disk usage, and troubleshoot networking -- all through the API server, no SSH keys required.

### oc adm top -- resource usage

`oc adm top nodes` and `oc adm top pods` show CPU and memory consumption, similar to `kubectl top` but available through the `oc adm` subcommand. Requires the metrics stack (pre-installed on OpenShift).

### Systematic debugging workflow

When a pod is not behaving as expected, follow this order:

1. **Events** -- `oc get events` to see what the cluster is reporting.
2. **Describe** -- `oc describe pod/<name>` for detailed status, conditions, and events on that specific resource.
3. **Logs** -- `oc logs <pod>` to read application output.
4. **Shell** -- `oc rsh <pod>` (if running) or `oc debug deployment/<name>` (if crashing) to investigate interactively.
5. **Node** -- `oc debug node/<name>` if the issue is at the node level (disk, networking, kubelet).
6. **Resources** -- `oc adm top pods` / `oc adm top nodes` to check for resource pressure.

## Step-by-Step

### Step 1: Create a project for debugging exercises

```bash
oc new-project debug-lab --display-name="Debug Lab" --description="Events and debugging practice"
```

**Expected output:**
```
Now using project "debug-lab" on server "https://api.crc.testing:6443".
```

### Step 2: Deploy a working application first

Deploy a healthy application so you can see what normal looks like before breaking things.

```bash
oc apply -f manifests/working-deployment.yaml
oc apply -f manifests/service.yaml
```

Wait for the pod to become ready:

```bash
oc get pods -w
```

**Expected output:**
```
NAME                               READY   STATUS    RESTARTS   AGE
hello-debug-<hash>                 1/1     Running   0          15s
```

Press `Ctrl+C` once you see `Running`.

### Step 3: View events for the healthy deployment

```bash
# See all events in the project, sorted by time
oc get events --sort-by='.lastTimestamp'
```

**Expected output:**
```
LAST SEEN   TYPE     REASON              OBJECT                              MESSAGE
10s         Normal   Scheduled           pod/hello-debug-5d4f8b7c9-xk2lm    Successfully assigned debug-lab/hello-debug-...
9s          Normal   Pulling             pod/hello-debug-5d4f8b7c9-xk2lm    Pulling image "openshift/hello-openshift"
7s          Normal   Pulled              pod/hello-debug-5d4f8b7c9-xk2lm    Successfully pulled image ...
7s          Normal   Created             pod/hello-debug-5d4f8b7c9-xk2lm    Created container hello-debug
6s          Normal   Started             pod/hello-debug-5d4f8b7c9-xk2lm    Started container hello-debug
10s         Normal   SuccessfulCreate    replicaset/hello-debug-5d4f8b7c9   Created pod: hello-debug-5d4f8b7c9-xk2lm
10s         Normal   ScalingReplicaSet   deployment/hello-debug              Scaled up replica set hello-debug-5d4f8b7c9 to 1
```

These are healthy events: Scheduled, Pulled, Created, Started. This is your baseline.

### Step 4: Use oc logs to read container output

```bash
# View logs from the running pod
oc logs deployment/hello-debug

# Follow logs in real time (Ctrl+C to stop)
oc logs -f deployment/hello-debug

# View previous container logs (useful after a restart)
oc logs deployment/hello-debug --previous
```

**Expected output:**
```
serving on 8888
serving on 8080
```

The `--previous` flag retrieves logs from the last terminated container instance -- essential for debugging CrashLoopBackOff scenarios where the current container keeps restarting.

### Step 5: Use oc rsh for a remote shell

`oc rsh` connects to a running pod. No need to remember the `-- /bin/sh` syntax.

```bash
# Get a shell into the running pod
oc rsh deployment/hello-debug

# Inside the pod, run some commands:
# Check the running process
ps aux
# Check environment variables
env | head -10
# Check network connectivity
cat /etc/resolv.conf
# Exit the shell
exit
```

**Expected output:**
```
$ oc rsh deployment/hello-debug
sh-4.4$ ps aux
PID   USER     TIME  COMMAND
    1 1000680  0:00  /hello-openshift
   14 1000680  0:00  /bin/sh
   20 1000680  0:00  ps aux
sh-4.4$ exit
```

Notice the user is a high-numbered UID (like `1000680`), not root. This is OpenShift's restricted SCC in action.

### Step 6: Use oc exec for one-off commands

When you need to run a single command without an interactive shell:

```bash
# Run a single command inside the pod
oc exec deployment/hello-debug -- cat /etc/os-release

# Check what user the container is running as
oc exec deployment/hello-debug -- id
```

**Expected output:**
```
$ oc exec deployment/hello-debug -- id
uid=1000680000(1000680000) gid=0(root) groups=0(root),1000680000
```

### Step 7: Deploy the broken application

Now deploy a deliberately broken deployment that will fail to start.

```bash
oc apply -f manifests/broken-deployment.yaml
```

Watch the pod status:

```bash
oc get pods -w
```

**Expected output:**
```
NAME                               READY   STATUS             RESTARTS   AGE
broken-app-<hash>                  0/1     ImagePullBackOff   0          10s
```

Press `Ctrl+C`. The pod is stuck in `ImagePullBackOff` because the image does not exist.

### Step 8: Debug with events and describe

Follow the systematic debugging workflow:

```bash
# Step 1: Check events for errors
oc get events --sort-by='.lastTimestamp' --field-selector reason=Failed
```

**Expected output:**
```
LAST SEEN   TYPE      REASON   OBJECT                           MESSAGE
5s          Warning   Failed   pod/broken-app-<hash>            Failed to pull image "quay.io/does-not-exist/fake-image:latest"
5s          Warning   Failed   pod/broken-app-<hash>            Error: ImagePullBackOff
```

```bash
# Step 2: Describe the pod for detailed error information
oc describe pod -l app=broken-app
```

**Expected output (key sections):**
```
...
Events:
  Type     Reason     Age   From               Message
  ----     ------     ----  ----               -------
  Normal   Scheduled  30s   default-scheduler  Successfully assigned debug-lab/broken-app-...
  Normal   Pulling    29s   kubelet            Pulling image "quay.io/does-not-exist/fake-image:latest"
  Warning  Failed     28s   kubelet            Failed to pull image "quay.io/does-not-exist/fake-image:latest": ...
  Warning  Failed     28s   kubelet            Error: ErrImagePull
  Normal   BackOff    15s   kubelet            Back-off pulling image "quay.io/does-not-exist/fake-image:latest"
  Warning  Failed     15s   kubelet            Error: ImagePullBackOff
```

The events tell the story: the image does not exist. In a real scenario, this could be a typo in the image name, missing credentials for a private registry, or a network issue.

### Step 9: Fix and redeploy with a crashing app

Now let us see a different failure mode. Deploy an app that starts but crashes immediately:

```bash
oc apply -f manifests/crashing-deployment.yaml
```

Watch the pod:

```bash
oc get pods -w
```

**Expected output (after a few seconds):**
```
NAME                               READY   STATUS             RESTARTS      AGE
crashing-app-<hash>                0/1     CrashLoopBackOff   2 (10s ago)   30s
```

Press `Ctrl+C`.

```bash
# Check the logs to see why it crashed
oc logs deployment/crashing-app
```

**Expected output:**
```
Starting up...
ERROR: Missing required config file at /etc/app/config.yaml
Exiting with error code 1
```

The application is telling you exactly what is wrong -- it expects a config file that does not exist.

### Step 10: Use oc debug to investigate the crashing pod

You cannot `oc rsh` into a crashing pod because the container is not running. This is where `oc debug` shines:

```bash
# Create a debug copy of the pod with a shell
oc debug deployment/crashing-app
```

Inside the debug pod:

```bash
# Check if the config file exists
ls -la /etc/app/
# It does not exist -- that is the problem

# Check the filesystem
ls /

# Exit when done investigating
exit
```

**Expected output:**
```
Starting pod/crashing-app-debug ...
Pod IP: 10.217.0.58
If you don't see a command prompt, try pressing enter.
sh-4.4$ ls -la /etc/app/
ls: cannot access '/etc/app/': No such file or directory
sh-4.4$ exit

Removing debug pod ...
```

Notice that the debug pod is automatically removed when you exit. Your running (crashing) deployment is unaffected.

### Step 11: Use oc debug with --as-root

Sometimes you need root access to check file permissions, install debugging tools, or inspect system directories:

```bash
# Run a debug pod as root (requires cluster-admin or appropriate SCC)
oc debug deployment/crashing-app --as-root
```

Inside the pod (as root):

```bash
# Now you are root
id
# uid=0(root) gid=0(root) groups=0(root)

# You can install debugging tools
# dnf install -y tcpdump strace   # (on UBI-based images)

exit
```

Note: `--as-root` requires the `system:admin` or `cluster-admin` role in most configurations. As the `developer` user, you may not have permission. Switch to `kubeadmin` if needed.

### Step 12: Check resource usage with oc adm top

```bash
# View node resource usage (requires cluster-admin)
oc login -u kubeadmin -p $(cat ~/.crc/machines/crc/kubeadmin-password) https://api.crc.testing:6443

oc adm top nodes
```

**Expected output:**
```
NAME                 CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
crc-<id>-master-0    1200m        30%    8192Mi          52%
```

```bash
# View pod resource usage in the debug-lab project
oc adm top pods -n debug-lab
```

**Expected output:**
```
NAME                           CPU(cores)   MEMORY(bytes)
hello-debug-5d4f8b7c9-xk2lm   1m           5Mi
```

```bash
# Switch back to developer
oc login -u developer -p developer https://api.crc.testing:6443
oc project debug-lab
```

`oc adm top` is useful for identifying pods that consume excessive CPU or memory -- a common cause of OOMKilled restarts and throttled performance.

### Step 13: Debug at the node level with oc debug node/

When the issue is at the node level (disk pressure, kubelet problems, networking), `oc debug node/` gives you a privileged pod with the host filesystem:

```bash
# Get the node name
oc get nodes

# Start a debug session on the node (requires cluster-admin)
oc login -u kubeadmin -p $(cat ~/.crc/machines/crc/kubeadmin-password) https://api.crc.testing:6443

oc debug node/$(oc get nodes -o jsonpath='{.items[0].metadata.name}')
```

Inside the node debug pod:

```bash
# The host filesystem is mounted at /host
# Switch to the host root
chroot /host

# Now you are on the node itself
# Check disk usage
df -h

# Check kubelet status
systemctl status kubelet

# View kubelet logs
journalctl -u kubelet --tail=20

# Check container runtime
crictl ps | head -10

# Exit chroot and pod
exit
exit
```

**Expected output:**
```
Starting pod/crc-<id>-master-0-debug ...
To use host binaries, run `chroot /host`
Pod IP: 192.168.126.11
If you don't see a command prompt, try pressing enter.
sh-4.4# chroot /host
sh-5.1# df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda4        31G   18G   13G  59% /
...
sh-5.1# exit
sh-4.4# exit

Removing debug pod ...
```

This replaces SSH entirely. In production OpenShift clusters running RHCOS (Red Hat CoreOS), the nodes are immutable -- you are not supposed to SSH into them. `oc debug node/` is the supported way to troubleshoot at the host level.

```bash
# Switch back to developer
oc login -u developer -p developer https://api.crc.testing:6443
oc project debug-lab
```

## Verification

Run these commands to confirm you have practiced each debugging tool:

```bash
# 1. Events -- verify you can see events
oc get events --sort-by='.lastTimestamp' | tail -5
# Expected: list of recent events with types Normal and Warning

# 2. Logs -- verify log access
oc logs deployment/hello-debug
# Expected: "serving on 8888" / "serving on 8080"

# 3. rsh -- verify you can get a shell into a running pod
oc rsh deployment/hello-debug -- id
# Expected: uid=<high-number> gid=0(root)

# 4. describe -- verify broken pod shows errors
oc describe pod -l app=broken-app | grep -A 3 "Warning"
# Expected: Failed to pull image messages

# 5. debug -- verify you can create a debug pod
oc debug deployment/hello-debug -- id
# Expected: uid=<high-number>, then "Removing debug pod ..."
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| View events | `kubectl get events` | `oc get events` (identical) |
| View logs | `kubectl logs <pod>` | `oc logs <pod>` (identical) |
| Remote shell | `kubectl exec -it <pod> -- /bin/sh` | `oc rsh <pod>` (shorthand) |
| One-off command | `kubectl exec <pod> -- <cmd>` | `oc exec <pod> -- <cmd>` (identical) |
| Debug crashing pod | `kubectl debug <pod> --image=busybox` (requires K8s 1.18+, copies the pod) | `oc debug deployment/<name>` (creates a shell-overridden copy from the deployment template) |
| Debug as root | `kubectl debug` with `--profile=general` (K8s 1.27+) | `oc debug --as-root` (straightforward flag) |
| Node-level access | SSH into the node | `oc debug node/<name>` (no SSH needed, host FS at /host) |
| Resource usage | `kubectl top nodes/pods` (requires metrics-server install) | `oc adm top nodes/pods` (metrics pre-installed) |
| Describe resources | `kubectl describe` | `oc describe` (identical) |
| Project overview | Multiple `kubectl get` commands | `oc status` (shows relationships) |

## Key Takeaways

- **Follow a systematic debugging order**: events, describe, logs, shell, node, resources -- this avoids guesswork and catches the problem at the right level.
- **oc debug creates disposable pods** -- it overrides the entrypoint with a shell so you can investigate crashing containers that `oc rsh` / `oc exec` cannot reach.
- **oc debug node/ replaces SSH** -- on RHCOS nodes, this is the supported debugging path. The host filesystem is mounted at `/host`, and you use `chroot /host` to access node binaries.
- **oc rsh is a convenience wrapper** -- it saves you from typing `oc exec -it <pod> -- /bin/sh` every time, but both approaches work.
- **oc adm top comes pre-configured** -- unlike vanilla Kubernetes where you must install metrics-server, OpenShift ships with the monitoring stack ready to go.

## Cleanup

```bash
# Delete all resources created in this lesson
oc delete all -l tutorial-level=1,tutorial-module=M6 -n debug-lab

# Delete the project
oc delete project debug-lab

# Verify it is gone
oc projects
```

## Next Steps

Congratulations -- you have completed Level 1 (Foundations). You now understand how OpenShift extends Kubernetes across platform setup, projects and RBAC, application deployment, networking, storage, and monitoring.

In **Level 2 -- L2-M1.1 (OpenShift Pipelines / Tekton)**, you will build on these foundations to create real CI/CD pipelines using OpenShift's built-in Tekton-based pipeline engine. You will define Tasks, Pipelines, and Triggers to automate the build-test-deploy workflow you have been doing manually.
