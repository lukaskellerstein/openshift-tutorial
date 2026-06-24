# L2-M6.1 --- OpenShift Dev Spaces (Eclipse Che)

**Level:** Practitioner
**Duration:** 45 min

## Overview

In Kubernetes, developer environments are a "bring your own laptop" affair --- every developer installs their own IDE, language runtimes, CLI tools, and database clients locally. This leads to "works on my machine" problems, painful onboarding, and configuration drift across the team. OpenShift addresses this with **Dev Spaces**, a cloud-based IDE built on **Eclipse Che** that runs developer workspaces as pods inside the cluster.

In this lesson you will install the Dev Spaces operator, understand the **CheCluster** Custom Resource that configures the platform, learn the **devfile** specification for workspace-as-code, and create devfiles for a Node.js and a Quarkus project that your team can use to get productive in minutes instead of hours.

## Prerequisites

- Completed: Level 1 (all modules)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as a user with `cluster-admin` privileges (needed to install the operator)
- `oc` CLI installed and on PATH
- CRC configured with at least 6 CPUs and 16 GB RAM (Dev Spaces is resource-intensive)

> **CRC Resource Note:** Dev Spaces requires significant resources. If your CRC instance has the default 4 CPUs / 9 GB RAM, increase them before starting:
> ```bash
> crc stop
> crc config set cpus 6
> crc config set memory 16384
> crc start
> ```

## K8s Context

In vanilla Kubernetes, there is no built-in developer workspace solution. Teams that want cloud-based IDEs typically:

1. Install Eclipse Che (the upstream project) via Helm, manually managing CRDs, ingress, and OAuth.
2. Use third-party tools like Gitpod, GitHub Codespaces, or VS Code Remote to containers.
3. Run nothing at all --- developers work entirely on their local machines.

Each approach requires significant setup, has no integration with the cluster's identity provider, and must be maintained separately from the platform. Eclipse Che on vanilla K8s needs an Ingress controller, a cert-manager, an OAuth provider, and careful RBAC configuration --- none of which come out of the box.

If you have used Eclipse Che on Kubernetes before, Dev Spaces will feel familiar. The key differences are operator-managed lifecycle, automatic integration with OpenShift OAuth, and a curated set of container images tested against each OpenShift release.

## Concepts

### What Is Dev Spaces?

Dev Spaces is Red Hat's productized distribution of **Eclipse Che** --- a Kubernetes-native platform that provisions developer workspaces as pods. Each workspace is a set of containers running in the cluster, providing:

- A full IDE (VS Code --- via the `che-code` editor --- or JetBrains via JetBrains Gateway)
- Language runtimes, compilers, and CLI tools
- Access to cluster-internal services (databases, APIs) without port-forwarding
- Persistent storage for source code and caches
- Pre-configured environment variables, secrets, and endpoints

The critical insight: your development environment runs in the same cluster as your application, using the same network, storage, and identity system. There is no gap between "local dev" and "deployed."

### The Devfile Specification

A **devfile** is a YAML file (`devfile.yaml`) that lives in the root of a Git repository and describes the workspace configuration. Think of it as a `Dockerfile` for development environments --- but instead of building a single container, it defines an entire workspace with multiple containers, commands, and endpoints.

The devfile schema (version 2.x) defines:

| Section | Purpose |
|---------|---------|
| `metadata` | Name, version, language, project type |
| `projects` | Git repositories to clone into the workspace |
| `components` | Containers (tools, databases, sidecars), volumes, and Kubernetes resources |
| `commands` | Build, run, test, and debug commands available in the IDE |
| `events` | Lifecycle hooks (preStart, postStart, preStop, postStop) |

### CheCluster Custom Resource

The **CheCluster** CR is the single point of configuration for the entire Dev Spaces platform. When you create a CheCluster in the `openshift-devspaces` namespace, the operator deploys:

- **Che Server** --- the API server that manages workspace lifecycle
- **Dashboard** --- the web UI where users create and manage workspaces
- **Devfile Registry** --- a catalog of pre-built devfile templates
- **Plugin Registry** --- VS Code extensions available to workspaces
- **Gateway** --- the Traefik-based ingress that routes to workspace pods

The CheCluster CR lets you configure:

- Resource limits for workspace containers
- Storage strategy (per-user or per-workspace PVCs)
- Idle timeout and workspace limits per user
- Default editor and components
- Git service integrations (GitHub, GitLab, Bitbucket OAuth)
- TLS and authentication settings

### DevWorkspace Operator

Under the hood, Dev Spaces uses the **DevWorkspace Operator** to manage individual workspaces. When a user starts a workspace, the system:

1. Reads the devfile from the Git repository (or the dashboard input).
2. Creates a **DevWorkspace** Custom Resource in the user's namespace.
3. The DevWorkspace Operator translates the devfile into Kubernetes objects: a Pod with the specified containers, PVCs for storage, Services for endpoints, and Routes for public-facing ports.
4. The user connects to the workspace via their browser or a local IDE.

```
User creates workspace (Dashboard or URL)
        |
        v
  Dev Spaces Server reads devfile.yaml
        |
        v
  Creates DevWorkspace CR in user namespace
        |
        v
  DevWorkspace Operator reconciles:
    - Pod (one container per devfile component)
    - PVC (persistent storage for source code)
    - Services + Routes (exposed endpoints)
        |
        v
  User connects via browser (VS Code in browser)
  or via local IDE (JetBrains Gateway)
```

### Why OpenShift Has This Built In

| Concern | Without Dev Spaces | With Dev Spaces |
|---------|-------------------|-----------------|
| **Onboarding** | Install IDE, runtimes, tools, configure env vars --- hours to days | Open a URL, click "Create Workspace" --- minutes |
| **Consistency** | "Works on my machine" | Every developer gets the same environment |
| **Security** | Source code on laptops, credentials in local files | Source code stays in the cluster, OAuth-integrated |
| **Resource usage** | Every developer runs databases, build tools locally | Shared cluster resources, idle timeout reclaims capacity |
| **Inner loop** | Code locally, push, wait for CI, debug remotely | Code in the cluster, test against real services instantly |

Enterprise teams care deeply about these concerns. Dev Spaces turns the development environment into a managed platform service, just like CI/CD or monitoring.

## Step-by-Step

### Step 1: Install the Dev Spaces Operator

The operator installs the DevWorkspace Operator (a dependency) and the Dev Spaces components.

**Option A: Via the Web Console (recommended for first-time install)**

1. Log in to the Web Console as `kubeadmin`.
2. Navigate to **Operators > OperatorHub**.
3. Search for **"Red Hat OpenShift Dev Spaces"**.
4. Click **Install**. Accept the defaults (All namespaces, Automatic approval).
5. Wait for the status to show **Succeeded** (2-5 minutes).

**Option B: Via the CLI**

```bash
# Log in as cluster-admin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Install the operator subscription
oc apply -f manifests/subscription-devspaces-operator.yaml
```

Wait for the operator to install:

```bash
# Watch the CSV status
oc get csv -n openshift-operators -w

# Expected output (after installation completes):
# NAME                              DISPLAY                        VERSION   PHASE
# devspacesoperator.v3.x.x          Red Hat OpenShift Dev Spaces   3.x.x     Succeeded
```

**Verify the installation:**

```bash
# Check that the DevWorkspace Operator is also installed (it is a dependency)
oc get csv -n openshift-operators | grep -E 'devspaces|devworkspace'

# Expected output:
# devspacesoperator.v3.x.x             Red Hat OpenShift Dev Spaces       3.x.x    Succeeded
# devworkspace-operator.v0.x.x         DevWorkspace Operator              0.x.x    Succeeded

# Verify the CRDs are registered
oc api-resources | grep -E 'checluster|devworkspace'

# Expected output:
# checlusters                          org.eclipse.che/v2                true    CheCluster
# devworkspaces                        workspace.devfile.io/v1alpha2    true    DevWorkspace
# devworkspacetemplates                workspace.devfile.io/v1alpha2    true    DevWorkspaceTemplate
```

> **Note:** The operator installs cluster-wide. You only need to do this once per cluster. On the Red Hat Developer Sandbox, Dev Spaces is already installed.

### Step 2: Create the Dev Spaces Namespace

Dev Spaces components run in a dedicated namespace:

```bash
oc create namespace openshift-devspaces

# Expected output:
# namespace/openshift-devspaces created
```

Or use the setup script, which handles the entire installation:

```bash
./scripts/setup.sh
```

### Step 3: Deploy the CheCluster Instance

The CheCluster CR tells the operator to deploy the actual Dev Spaces platform.

**For CRC (resource-constrained):**

```bash
oc apply -f manifests/checluster-minimal.yaml

# Expected output:
# checluster.org.eclipse.che/devspaces created
```

**For production or Developer Sandbox:**

```bash
oc apply -f manifests/checluster.yaml

# Expected output:
# checluster.org.eclipse.che/devspaces created
```

The key differences between the two manifests:

| Setting | Minimal (CRC) | Full (Production) |
|---------|---------------|-------------------|
| Default container memory | 1Gi limit | 2Gi limit |
| Default container CPU | 500m limit | 1 core limit |
| Max workspaces per user | 2 | Unlimited |
| Idle timeout | 30 minutes | Disabled |
| Metrics | Disabled | Enabled |

**Wait for all components to come up** (5-10 minutes on CRC):

```bash
# Watch the CheCluster phase
oc get checluster devspaces -n openshift-devspaces -w

# Expected output (eventually):
# NAME        ISACTIVE   STATUS
# devspaces   true       Available

# Check the pods
oc get pods -n openshift-devspaces

# Expected output:
# NAME                                        READY   STATUS    RESTARTS   AGE
# che-gateway-xxxxxxxxxx-xxxxx                1/1     Running   0          3m
# devspaces-xxxxxxxxxx-xxxxx                  1/1     Running   0          3m
# devspaces-dashboard-xxxxxxxxxx-xxxxx        1/1     Running   0          3m
# plugin-registry-xxxxxxxxxx-xxxxx            1/1     Running   0          3m
# devfile-registry-xxxxxxxxxx-xxxxx           1/1     Running   0          3m
```

**Get the Dev Spaces dashboard URL:**

```bash
oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.cheURL}'

# Expected output:
# https://devspaces.apps-crc.testing
```

Open this URL in your browser. You will be redirected to OpenShift's OAuth login page --- log in with your OpenShift credentials (`developer` / `developer` for CRC).

### Step 4: Explore the CheCluster Configuration

Before creating workspaces, understand what the operator deployed:

```bash
# View the full CheCluster status
oc get checluster devspaces -n openshift-devspaces -o yaml | grep -A 20 'status:'

# Expected output (abbreviated):
# status:
#   chePhase: Active
#   cheURL: https://devspaces.apps-crc.testing
#   cheVersion: 3.x.x
#   devfileRegistryURL: https://devspaces.apps-crc.testing/devfile-registry
#   pluginRegistryURL: https://devspaces.apps-crc.testing/plugin-registry
#   gatewayPhase: Established

# List the Routes created by the operator
oc get routes -n openshift-devspaces

# Expected output:
# NAME            HOST/PORT                          PATH   SERVICES       PORT    TERMINATION
# devspaces       devspaces.apps-crc.testing                che-gateway    https   reencrypt
```

Notice that the operator automatically created Routes with TLS re-encrypt termination, integrated with OpenShift's OAuth server, and set up all the internal services. On vanilla K8s, you would configure all of this manually.

### Step 5: Understand the Devfile Specification

Before creating a workspace, examine the devfile that will configure it. A devfile defines everything about a development environment as code.

**Examine the Node.js devfile:**

The file at `manifests/devfile-nodejs.yaml` demonstrates a complete devfile. The key sections are:

**Projects** --- Git repositories to clone:

```yaml
projects:
  - name: nodejs-sample
    git:
      remotes:
        origin: https://github.com/sclorg/nodejs-ex.git
      checkoutFrom:
        revision: master
```

**Components** --- containers and volumes that make up the workspace:

```yaml
components:
  - name: tools
    container:
      image: registry.redhat.io/devspaces/udi-rhel8:latest
      memoryLimit: 2Gi
      cpuLimit: "1"
      endpoints:
        - name: nodejs
          targetPort: 8080
          exposure: public
          protocol: https
```

The `udi-rhel8` (Universal Developer Image) includes Node.js, Java, Python, Go, .NET, and common CLI tools. For a leaner workspace you could use a language-specific image.

**Commands** --- tasks available in the IDE:

```yaml
commands:
  - id: run
    exec:
      component: tools
      workingDir: ${PROJECT_SOURCE}
      commandLine: npm start
      group:
        kind: run
        isDefault: true
```

Commands appear in the IDE's task runner. The `group` field categorizes them (build, run, test, debug), and `isDefault: true` makes the command the primary action for its group.

### Step 6: Create a Workspace from a Devfile URL

The simplest way to create a workspace is to give Dev Spaces a Git repository URL that contains a `devfile.yaml`:

**Method 1: Via the Dashboard**

1. Open the Dev Spaces dashboard (URL from Step 3).
2. Click **Create Workspace**.
3. Enter a Git repository URL. For this tutorial, use:
   ```
   https://github.com/devfile-samples/devfile-sample-code-with-quarkus.git
   ```
4. Dev Spaces detects the `devfile.yaml` in the repository and displays the workspace configuration.
5. Click **Create & Open**.

**Method 2: Via a factory URL (direct link)**

Dev Spaces supports "factory URLs" --- direct links that create and open a workspace in one step. This is powerful for team onboarding and README links:

```
https://devspaces.apps-crc.testing/#https://github.com/devfile-samples/devfile-sample-code-with-quarkus.git
```

The format is: `<Dev Spaces URL>/#<Git Repo URL>`

Paste this into your browser. Dev Spaces will:
1. Clone the repository.
2. Read the `devfile.yaml`.
3. Create a DevWorkspace CR in your namespace.
4. Start the workspace containers.
5. Open VS Code in your browser once the workspace is ready.

**Observe what happens in the cluster:**

```bash
# A new namespace was created for your workspaces
oc get namespaces | grep devspaces

# Expected output:
# developer-devspaces       Active   30s
# openshift-devspaces       Active   10m

# A DevWorkspace CR was created
oc get devworkspace -n developer-devspaces

# Expected output:
# NAME                                    PHASE     INFO
# devfile-sample-code-with-quarkus-xxxx   Running   https://devspaces.apps-crc.testing/...

# The workspace is a pod with multiple containers
oc get pods -n developer-devspaces

# Expected output:
# NAME                                          READY   STATUS    RESTARTS   AGE
# workspacexxxxxxxxxxxxxxxx.xxxx-xxxxx          2/2     Running   0          60s

# Inspect the workspace pod
oc describe pod -n developer-devspaces -l controller.devfile.io/devworkspace_name

# You will see containers for the dev tools and the che-code editor
```

### Step 7: Create a Workspace from a Custom Devfile

Now create a workspace using the Node.js devfile from this lesson. In a real project you would commit this file as `devfile.yaml` at the repository root. For this exercise, we will use the Dev Spaces dashboard to supply the devfile content.

**Method 1: Add a devfile to your own repository**

If you have a Git repository you want to work on:

1. Copy the content of `manifests/devfile-nodejs.yaml` to a file named `devfile.yaml` in the root of your Git repository.
2. Update the `projects` section to point to your repository.
3. Commit and push.
4. Open the factory URL: `https://devspaces.apps-crc.testing/#<your-repo-url>`

**Method 2: Use the multi-container Quarkus devfile**

The Quarkus devfile at `manifests/devfile-quarkus.yaml` demonstrates a more advanced scenario: a workspace with a development tools container AND a PostgreSQL database sidecar.

```yaml
components:
  - name: tools
    container:
      image: registry.redhat.io/devspaces/udi-rhel8:latest
      # ...
  - name: postgresql
    container:
      image: registry.redhat.io/rhel9/postgresql-15:latest
      endpoints:
        - name: postgresql
          targetPort: 5432
          exposure: internal
```

When this workspace starts, the developer gets a VS Code editor with Java/Maven tools AND a running PostgreSQL database accessible at `localhost:5432` --- no need to port-forward or run Docker locally.

### Step 8: Explore the Running Workspace

Once inside a running workspace (VS Code in the browser):

1. **Terminal**: Open a terminal (Ctrl+\` or Terminal > New Terminal). You are inside the tools container, with `oc`, `kubectl`, `git`, `npm`, `mvn`, and other tools pre-installed.

2. **Run commands**: The devfile commands appear in the IDE's task runner. Click **Terminal > Run Task** to see the build, run, test, and debug commands defined in the devfile.

3. **Access endpoints**: If the devfile defines a public endpoint (e.g., port 8080), Dev Spaces creates a Route for it. Find the URL in the **Endpoints** panel or by running:

   ```bash
   # From inside the workspace terminal
   echo $DEVWORKSPACE_ROUTING_HOST
   ```

4. **Live preview**: Start the application with the `run` command. Open the endpoint URL to see your application running --- served from inside the cluster.

5. **Git integration**: The workspace has Git configured with your OpenShift identity. You can commit, push, and pull directly.

**From outside the workspace, observe the cluster resources:**

```bash
# List all DevWorkspaces across all namespaces
oc get devworkspace -A

# Expected output:
# NAMESPACE               NAME                                    PHASE     INFO
# developer-devspaces     devfile-sample-code-with-quarkus-xxxx   Running   ...

# Check PVCs (persistent storage for workspace data)
oc get pvc -n developer-devspaces

# Expected output:
# NAME                  STATUS   VOLUME          CAPACITY   ACCESS MODES   STORAGECLASS
# claim-developer-...   Bound    pv-...          10Gi       RWO            ...

# Check Routes (workspace endpoints)
oc get routes -n developer-devspaces

# Expected output:
# NAME                          HOST/PORT                                               SERVICES      PORT
# workspacexxxx-...             workspacexxxx-....apps-crc.testing                      ...           ...
```

### Step 9: Apply a DevWorkspaceTemplate for Team Standardization

For teams that want consistent tooling across projects, you can create **DevWorkspaceTemplates** --- reusable component sets that devfiles can reference.

```bash
oc apply -f manifests/devworkspace-template.yaml

# Expected output:
# devworkspacetemplate.workspace.devfile.io/team-standard-tools created
```

Individual devfiles can then reference this template instead of duplicating container definitions:

```yaml
# In a project's devfile.yaml
components:
  - name: team-tools
    plugin:
      kubernetes:
        name: team-standard-tools
        namespace: openshift-devspaces
```

This enables a "golden path" pattern: the platform team defines standard tooling, and project teams extend it with project-specific additions.

### Step 10: Manage Workspace Lifecycle

**Stop a workspace** (preserves data, releases compute resources):

```bash
# From the CLI
oc patch devworkspace <workspace-name> -n developer-devspaces \
  --type merge -p '{"spec":{"started":false}}'

# Expected output:
# devworkspace.workspace.devfile.io/<workspace-name> patched

# Verify it stopped
oc get devworkspace -n developer-devspaces

# Expected output:
# NAME                                    PHASE     INFO
# devfile-sample-code-with-quarkus-xxxx   Stopped   ...
```

**Restart a stopped workspace:**

```bash
oc patch devworkspace <workspace-name> -n developer-devspaces \
  --type merge -p '{"spec":{"started":true}}'
```

**Delete a workspace** (removes the pod, but PVC data persists with `per-user` strategy):

```bash
oc delete devworkspace <workspace-name> -n developer-devspaces
```

**From the Dashboard:**

The Dev Spaces dashboard provides a UI for all these operations: start, stop, delete, and view workspace details. Navigate to **Workspaces** in the left sidebar.

## Verification

Run through this checklist to confirm everything is working:

```bash
# 1. Operator is installed and running
oc get csv -n openshift-operators | grep devspaces

# Expected: devspacesoperator.v3.x.x ... Succeeded

# 2. DevWorkspace Operator is installed (dependency)
oc get csv -n openshift-operators | grep devworkspace

# Expected: devworkspace-operator.v0.x.x ... Succeeded

# 3. CheCluster is active
oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.chePhase}'

# Expected: Active

# 4. All Dev Spaces pods are running
oc get pods -n openshift-devspaces -o wide

# Expected: all pods Running, no CrashLoopBackOff

# 5. Dashboard is accessible
DEV_SPACES_URL=$(oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.cheURL}')
echo "Dashboard URL: ${DEV_SPACES_URL}"
curl -sk "${DEV_SPACES_URL}" -o /dev/null -w "HTTP Status: %{http_code}\n"

# Expected: HTTP Status: 200

# 6. At least one workspace was created (if you completed Steps 6-7)
oc get devworkspace -A

# Expected: at least one DevWorkspace in Running or Stopped phase

# 7. Devfile Registry is accessible
REGISTRY_URL=$(oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.devfileRegistryURL}')
curl -sk "${REGISTRY_URL}/devfiles/index.json" | head -c 200

# Expected: JSON array of available devfile samples

# 8. Web Console integration
# Navigate to: Developer perspective > +Add > Developer Sandbox (or Samples)
# Dev Spaces workspaces should appear under the developer's topology view
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Cloud IDE platform | Install Eclipse Che via Helm manually | Dev Spaces operator: one-click install from OperatorHub |
| Authentication | Configure OAuth proxy or Dex manually | Automatic integration with OpenShift OAuth |
| TLS certificates | Install cert-manager, configure Ingress | Automatic TLS via OpenShift Routes (re-encrypt) |
| User namespaces | Create manually, set up RBAC | Auto-provisioned per user with correct RBAC |
| Workspace isolation | Configure PodSecurityPolicies / PSA manually | SCCs enforce workspace pod isolation automatically |
| Ingress routing | Configure Ingress controller + certs for workspace endpoints | Routes created automatically by DevWorkspace Operator |
| Updates | Track upstream Che releases, apply Helm upgrades | Operator manages upgrades automatically |
| Image registry | Pull from public registries | Red Hat certified UDI images, tested per release |
| Dashboard | Che Dashboard (separate install) | Integrated dashboard + OpenShift console integration |
| IDE options | VS Code (Theia), configure manually | VS Code (che-code), JetBrains Gateway, pre-configured |
| Devfile registry | Deploy separately or use devfile.io | Built-in registry with Red Hat curated samples |
| Resource governance | Configure ResourceQuotas manually | CheCluster CR controls workspace limits centrally |

## Key Takeaways

- **Dev Spaces turns developer environments into a managed service**: instead of each developer maintaining their own local setup, the platform team provisions standardized, cloud-based workspaces. This eliminates "works on my machine" problems and reduces onboarding time from days to minutes.

- **Devfiles are workspace-as-code**: just as Dockerfiles define container images and Kubernetes manifests define deployments, devfiles define development environments. Commit a `devfile.yaml` to your repository and every developer gets the same IDE, tools, databases, and commands --- versioned and reviewable alongside the application code.

- **The CheCluster CR is the single control plane**: platform administrators configure workspace defaults, resource limits, idle timeouts, and authentication through one Custom Resource. The operator handles all the deployment complexity (gateway, dashboard, registries, DevWorkspace Operator).

- **Multi-container workspaces bridge the inner-loop gap**: devfiles can include database sidecars, message brokers, and other dependencies as workspace containers. Developers test against real services without port-forwarding or Docker Compose --- the entire development stack runs in the cluster.

- **Factory URLs enable frictionless onboarding**: a single URL (`<devspaces-url>/#<git-repo-url>`) creates a fully configured workspace from a repository's devfile. Put this in your project's README and new contributors can start coding immediately.

## Troubleshooting

### Workspace stuck in "Starting" phase

```bash
# Check the DevWorkspace status
oc get devworkspace -n <user>-devspaces -o yaml

# Check events in the user's namespace
oc get events -n <user>-devspaces --sort-by='.lastTimestamp'

# Check the DevWorkspace Operator logs
oc logs deployment/devworkspace-controller-manager -n devworkspace-controller -c manager --tail=50
```

Common causes:
- **Insufficient resources**: Dev Spaces workspaces need 2-4 GB RAM per workspace. On CRC, use the minimal CheCluster config and limit to 1-2 workspaces.
- **Image pull errors**: The UDI image (`registry.redhat.io/devspaces/udi-rhel8`) requires Red Hat registry authentication. CRC includes pull secrets, but verify: `oc get secret pull-secret -n openshift-config`.
- **PVC binding**: If the StorageClass cannot provision a PVC, the workspace pod will be stuck in Pending. Check: `oc get pvc -n <user>-devspaces`.

### "403 Forbidden" when accessing the dashboard

The Dev Spaces dashboard uses OpenShift OAuth. Ensure:

```bash
# The user has permission to create DevWorkspaces
oc auth can-i create devworkspace -n <user>-devspaces --as=<username>

# The OAuth integration is healthy
oc get pods -n openshift-devspaces | grep gateway
oc logs deployment/che-gateway -n openshift-devspaces --tail=20
```

If using CRC, try logging in as `developer` (not `kubeadmin`). The `kubeadmin` user sometimes has OAuth issues with Dev Spaces.

### Workspace runs but endpoints are not accessible

```bash
# Check that Routes were created for workspace endpoints
oc get routes -n <user>-devspaces

# If no routes, check the DevWorkspace routing status
oc get devworkspace <name> -n <user>-devspaces -o jsonpath='{.status.mainUrl}'

# Check the che-gateway logs for routing errors
oc logs deployment/che-gateway -n openshift-devspaces --tail=30
```

On CRC, ensure that `*.apps-crc.testing` resolves correctly. Run `nslookup devspaces.apps-crc.testing` to verify DNS.

### CRC runs out of resources with Dev Spaces

Dev Spaces is resource-intensive. Monitor node capacity:

```bash
# Check node resource usage
oc adm top nodes

# Check what is consuming resources
oc adm top pods -A --sort-by=memory | head -20

# If tight on resources, stop idle workspaces
oc get devworkspace -A -o jsonpath='{range .items[?(@.status.phase=="Running")]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}'

# Increase CRC resources if needed
crc stop
crc config set cpus 8
crc config set memory 20480
crc start
```

### Devfile validation errors

If a workspace fails to start due to devfile issues:

```bash
# Validate the devfile schema
# The devfile registry provides a validation endpoint
curl -sk "$(oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.devfileRegistryURL}')/devfiles/" | python3 -m json.tool

# Check the DevWorkspace events for specific errors
oc describe devworkspace <name> -n <user>-devspaces
```

Common devfile mistakes:
- Using `schemaVersion: 2.0.0` instead of `2.2.2` (older versions lack features)
- Referencing images that require root access (violates OpenShift SCCs)
- Setting `memoryLimit` lower than what the application needs (OOMKilled)
- Missing `mountSources: true` on the main container (source code not available)

## Cleanup

```bash
# Delete all workspaces across all user namespaces
oc get devworkspace -A --no-headers | while read -r NS NAME REST; do
  oc delete devworkspace "${NAME}" -n "${NS}"
done

# Delete the DevWorkspaceTemplate
oc delete devworkspacetemplate -l tutorial-level=2,tutorial-module=M6 -n openshift-devspaces

# Delete the CheCluster instance
oc delete checluster devspaces -n openshift-devspaces --wait=true --timeout=120s

# Wait for pods to terminate, then delete the namespace
oc delete namespace openshift-devspaces

# Clean up user workspace namespaces
oc get namespaces -o name | grep '\-devspaces$' | xargs oc delete

# Or use the teardown script:
./scripts/teardown.sh
```

> **Note:** The Dev Spaces operator remains installed cluster-wide. Uninstall it from the Web Console (Operators > Installed Operators > Dev Spaces > Uninstall) only if you no longer need it. This will also remove the DevWorkspace Operator dependency.

## Next Steps

In **L2-M6.2 --- odo --- Developer CLI**, you will learn about `odo`, OpenShift's developer-focused CLI that complements Dev Spaces. While Dev Spaces provides a full cloud IDE, `odo` optimizes the inner development loop from any local IDE --- enabling live sync of code changes to a running container in the cluster with `odo dev`. Both tools use the same **devfile** specification, so the workspace definitions you created here work with `odo` as well.
