# L1-M3.5 -- Templates & Kustomize

**Level:** Foundations
**Duration:** 30 min

## Overview

In Kubernetes, you parameterize your YAML with tools like Helm or Kustomize -- both external to the core platform. OpenShift has its own built-in templating system called **Templates** that predates both. This lesson teaches you how to create and process OpenShift Templates with parameters, then compares that approach with Helm and Kustomize -- both of which are also fully supported on OpenShift -- so you know which tool to reach for and when.

## Prerequisites

- Completed: L1-M3.1 (oc new-app & Source-to-Image)
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI installed and on your PATH

## K8s Context

In vanilla Kubernetes, you have two main approaches to managing variations in your YAML manifests:

1. **Helm** -- a package manager that uses Go templates inside YAML charts, producing versioned releases with install/upgrade/rollback semantics.
2. **Kustomize** -- a template-free overlay system built into `kubectl` (`kubectl apply -k`) that patches base manifests without modifying them.

Neither is built into the Kubernetes API server itself -- they are client-side tools. Kubernetes has no native server-side concept of "a template with parameters."

## Concepts

### OpenShift Templates

OpenShift Templates are a **server-side** concept -- they are actual API resources of kind `Template` stored in the cluster. A Template bundles multiple resource definitions (Deployments, Services, Routes, etc.) together with **parameters** that are substituted at processing time.

Key characteristics:
- Templates are OpenShift-specific (`template.openshift.io/v1` API group).
- Parameters have names, descriptions, default values, and can be marked as required.
- You process a template with `oc process`, which resolves all parameters and outputs standard Kubernetes YAML that you then apply.
- The cluster ships with dozens of pre-installed templates in the `openshift` namespace (languages, databases, frameworks).
- Templates can be shared by uploading them to a project -- other users in that project can then instantiate them.

Parameter substitution uses two syntaxes:
- `${PARAM_NAME}` -- string substitution (the value is injected as a string).
- `${{PARAM_NAME}}` -- numeric/boolean substitution (the value is injected without quotes, preserving the YAML type).

### Helm on OpenShift

Helm works on OpenShift exactly as it does on Kubernetes. OpenShift adds value in two ways:
- The **Web Console** has a built-in Helm chart catalog under the Developer perspective (Developer > +Add > Helm Chart).
- Red Hat provides **certified Helm charts** that are tested for OpenShift compatibility (SCC-aware, UBI-based images).

You install Helm charts the same way: `helm install`, `helm upgrade`, `helm rollback`.

### Kustomize on OpenShift

Kustomize also works identically on OpenShift. Both `oc` and `kubectl` embed Kustomize and support the `-k` flag:
- `oc apply -k overlays/dev/` -- apply Kustomize overlay using `oc`.
- `kubectl apply -k overlays/dev/` -- same operation, works on OpenShift too.

Kustomize is popular for GitOps workflows because overlays are plain YAML patches without a template language -- what you see is what gets applied.

### When to use which

| Scenario | Best tool |
|----------|-----------|
| Quick prototyping on OpenShift, sharing app blueprints within a team | OpenShift Templates |
| Packaging software for distribution (community or vendor charts) | Helm |
| Environment-specific overlays in a GitOps pipeline (dev/staging/prod) | Kustomize |
| Mixed K8s and OpenShift clusters | Helm or Kustomize (portable) |
| Pre-installed cluster catalog items | OpenShift Templates (already there) |

## Step-by-Step

### Step 1: Create a project for this lesson

```bash
oc new-project template-demo --display-name="Template Demo" --description="L1-M3.5: Templates and Kustomize"
```

**Expected output:**
```
Now using project "template-demo" on server "https://api.crc.testing:6443".
```

### Step 2: Explore pre-installed templates

OpenShift ships with templates in the `openshift` namespace for common workloads -- databases, web frameworks, and more. Browse what is available.

```bash
# List all templates in the openshift namespace
oc get templates -n openshift

# See details of a specific template (e.g., a database)
oc describe template mysql-ephemeral -n openshift
```

**Expected output (abbreviated):**
```
$ oc get templates -n openshift
NAME                    DESCRIPTION                                                   PARAMETERS    OBJECTS
cakephp-mysql-example   An example CakePHP application with a MySQL database...       18 (4 blank)  8
dancer-mysql-example    An example Dancer application with a MySQL database...         17 (5 blank)  8
django-psql-example     An example Django application with a PostgreSQL database...    19 (5 blank)  8
httpd-example           An example Apache HTTP Server application...                   9 (3 blank)   5
mysql-ephemeral         MySQL database service, without persistent storage...          8 (3 blank)   3
mysql-persistent        MySQL database service, with persistent storage...             9 (3 blank)   4
...
```

Notice the PARAMETERS and OBJECTS columns. Each template declares how many parameters it accepts and how many Kubernetes/OpenShift resources it will create.

### Step 3: Examine the template manifest

Look at the template file included with this lesson. It defines a parameterized web application with a Deployment, Service, and Route.

```yaml
# manifests/openshift-template.yaml (key sections)
apiVersion: template.openshift.io/v1
kind: Template
metadata:
  name: web-app-template
parameters:
  - name: APP_NAME
    description: "Name of the application"
    value: "template-app"
    required: true
  - name: APP_IMAGE
    description: "Container image to deploy"
    value: "openshift/hello-openshift:latest"
    required: true
  - name: REPLICAS
    description: "Number of pod replicas"
    value: "1"
    required: true
  - name: APP_PORT
    description: "Port the container listens on"
    value: "8080"
    required: true
objects:
  - apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: "${APP_NAME}"
    spec:
      replicas: ${{REPLICAS}}
      ...
  - apiVersion: v1
    kind: Service
    ...
  - apiVersion: route.openshift.io/v1
    kind: Route
    ...
```

Key details:
- `parameters` defines the inputs -- each has a name, description, default value, and whether it is required.
- `objects` contains the resource definitions, referencing parameters with `${APP_NAME}` (string) or `${{REPLICAS}}` (numeric).
- The `${{REPLICAS}}` syntax ensures the value is injected as an integer (`replicas: 1`), not a string (`replicas: "1"`).

### Step 4: Process the template with default parameters

Use `oc process` to resolve all parameters and see the resulting YAML. This does not create any resources -- it only outputs the processed manifests.

```bash
# Process the template using default parameter values
oc process -f manifests/openshift-template.yaml
```

**Expected output (abbreviated):**
```json
{
    "kind": "List",
    "apiVersion": "v1",
    "items": [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "template-app",
                "labels": {
                    "app": "template-app"
                }
            },
            "spec": {
                "replicas": 1,
                ...
            }
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "template-app"
            },
            ...
        },
        {
            "apiVersion": "route.openshift.io/v1",
            "kind": "Route",
            "metadata": {
                "name": "template-app"
            },
            ...
        }
    ]
}
```

Notice that `${APP_NAME}` was replaced with `template-app` (the default) everywhere it appeared.

### Step 5: Process with custom parameters and deploy

Now override the defaults to deploy a custom instance. Pipe the processed output directly to `oc apply`.

```bash
# Process the template with custom parameters and apply the result
oc process -f manifests/openshift-template.yaml \
  -p APP_NAME=hello-template \
  -p REPLICAS=2 \
  | oc apply -f -
```

**Expected output:**
```
deployment.apps/hello-template created
service/hello-template created
route.route.openshift.io/hello-template created
```

You can also supply parameters from a file using `--param-file`:

```bash
# Create a parameter file
cat <<'EOF' > /tmp/params.env
APP_NAME=hello-params
REPLICAS=1
APP_IMAGE=openshift/hello-openshift:latest
APP_PORT=8080
EOF

# Process using the parameter file
oc process -f manifests/openshift-template.yaml --param-file=/tmp/params.env | oc apply -f -
```

**Expected output:**
```
deployment.apps/hello-params created
service/hello-params created
route.route.openshift.io/hello-params created
```

### Step 6: Verify the template-based deployments

```bash
# Check the deployments
oc get deployments

# Check the routes
oc get routes

# Test the application via its route
curl -s http://hello-template-template-demo.apps-crc.testing
```

**Expected output:**
```
$ oc get deployments
NAME             READY   UP-TO-DATE   AVAILABLE   AGE
hello-template   2/2     2            2           30s
hello-params     1/1     1            1           15s

$ oc get routes
NAME             HOST/PORT                                          PATH   SERVICES         PORT   TERMINATION   WILDCARD
hello-template   hello-template-template-demo.apps-crc.testing             hello-template   8080                 None
hello-params     hello-params-template-demo.apps-crc.testing               hello-params     8080                 None

$ curl -s http://hello-template-template-demo.apps-crc.testing
Hello OpenShift!
```

### Step 7: Upload a template to the cluster

You can store templates in the cluster itself so other team members can use them from the Web Console or CLI.

```bash
# Upload the template to the current project
oc apply -f manifests/openshift-template.yaml

# Verify it is stored
oc get templates

# Another user in this project can now instantiate it:
# oc process web-app-template -p APP_NAME=team-app | oc apply -f -
```

**Expected output:**
```
$ oc apply -f manifests/openshift-template.yaml
template.template.openshift.io/web-app-template created

$ oc get templates
NAME               DESCRIPTION                                                        PARAMETERS   OBJECTS
web-app-template   A simple web application template for the OpenShift tutorial.       4 (all set)  3
```

Once uploaded, the template also appears in the Web Console under Developer > +Add > From Template.

### Step 8: Use oc new-app with a template

You can also instantiate templates directly using `oc new-app`, which you learned in L1-M3.1.

```bash
# Deploy from the uploaded template using oc new-app
oc new-app --template=web-app-template -p APP_NAME=newapp-demo -p REPLICAS=1

# Check the results
oc get deployments
oc get routes
```

**Expected output:**
```
$ oc new-app --template=web-app-template -p APP_NAME=newapp-demo -p REPLICAS=1
--> Deploying template "template-demo/web-app-template" to project template-demo

     Tutorial Web App
     ---------
     A simple web application template for the OpenShift tutorial.

     * With parameters:
        * Name of the application=newapp-demo
        * Container image to deploy=openshift/hello-openshift:latest
        * Number of pod replicas=1
        * Port the container listens on=8080

--> Creating resources ...
    deployment.apps "newapp-demo" created
    service "newapp-demo" created
    route.route.openshift.io "newapp-demo" created
--> Success
```

### Step 9: Deploy with Kustomize overlays

Now compare the same workflow using Kustomize. The `manifests/kustomize/` directory contains a base layer and two overlays (dev and prod).

```bash
# Preview what the dev overlay produces (dry-run)
oc apply -k manifests/kustomize/overlays/dev/ --dry-run=client -o yaml | head -40

# Apply the dev overlay
oc apply -k manifests/kustomize/overlays/dev/
```

**Expected output:**
```
$ oc apply -k manifests/kustomize/overlays/dev/
deployment.apps/dev-kustomize-app created
service/dev-kustomize-app created
route.route.openshift.io/dev-kustomize-app created
```

Notice that Kustomize added the `dev-` prefix to every resource name and applied the `environment: dev` label -- all without modifying the base YAML files. The base files remain untouched and can be shared across overlays.

```bash
# Apply the prod overlay in the same project (for demonstration)
oc apply -k manifests/kustomize/overlays/prod/

# Compare the deployments
oc get deployments
```

**Expected output:**
```
$ oc apply -k manifests/kustomize/overlays/prod/
deployment.apps/prod-kustomize-app created
service/prod-kustomize-app created
route.route.openshift.io/prod-kustomize-app created

$ oc get deployments
NAME                 READY   UP-TO-DATE   AVAILABLE   AGE
hello-template       2/2     2            2           5m
hello-params         1/1     1            1           4m
newapp-demo          1/1     1            1           2m
dev-kustomize-app    1/1     1            1           30s
prod-kustomize-app   3/3     3            3           10s
```

The dev overlay has 1 replica and the prod overlay has 3 -- both derived from the same base manifest.

### Step 10: Inspect the Kustomize directory structure

Understanding the layout helps you see why Kustomize works well for GitOps:

```bash
# Show the directory tree
find manifests/kustomize -type f | sort
```

**Expected output:**
```
manifests/kustomize/base/deployment.yaml
manifests/kustomize/base/kustomization.yaml
manifests/kustomize/base/route.yaml
manifests/kustomize/base/service.yaml
manifests/kustomize/overlays/dev/kustomization.yaml
manifests/kustomize/overlays/prod/kustomization.yaml
```

The `base/` directory holds the canonical resource definitions. Each overlay directory contains only a `kustomization.yaml` that references the base and applies patches. In a real project, you would commit each overlay to Git, and a GitOps tool like ArgoCD would apply the appropriate overlay to each cluster.

## Verification

Run these commands to confirm everything is working:

```bash
# 1. Verify template-based deployments are running
oc get deployments -l tutorial-module=M3
# Expected: hello-template (2 replicas), hello-params (1 replica), newapp-demo (1 replica)

# 2. Verify Kustomize-based deployments are running
oc get deployments dev-kustomize-app prod-kustomize-app
# Expected: dev-kustomize-app (1 replica), prod-kustomize-app (3 replicas)

# 3. Verify routes exist for all deployments
oc get routes
# Expected: routes for hello-template, hello-params, newapp-demo, dev-kustomize-app, prod-kustomize-app

# 4. Verify the uploaded template exists in the project
oc get templates
# Expected: web-app-template

# 5. Test connectivity through a route
curl -s http://hello-template-template-demo.apps-crc.testing
# Expected: Hello OpenShift!
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Built-in templating | None -- use Helm or Kustomize (client-side) | OpenShift Templates (server-side API resource) |
| Template storage | Helm charts in external repos | Templates stored in the cluster (`oc get templates`) |
| Parameter substitution | Helm: Go templates; Kustomize: patch overlays | `${PARAM}` (string) and `${{PARAM}}` (typed) |
| Catalog experience | Helm Hub / Artifact Hub | Web Console "From Template" + OperatorHub |
| Processing | `helm template` / `kubectl kustomize` | `oc process -f template.yaml -p KEY=value` |
| Instantiation | `helm install` / `kubectl apply -k` | `oc new-app --template=name -p KEY=value` |
| Helm support | Native | Fully supported + Web Console catalog |
| Kustomize support | `kubectl apply -k` | `oc apply -k` (identical) |
| Pre-installed blueprints | None | Dozens of templates in `openshift` namespace |

## Key Takeaways

- **OpenShift Templates are a built-in, server-side templating mechanism** -- they bundle multiple resources with parameters and are processed by `oc process`. They predate Helm and Kustomize and are unique to OpenShift.
- **Use `${PARAM}` for strings and `${{PARAM}}` for numbers/booleans** -- this distinction prevents YAML type errors (e.g., `replicas: "1"` vs `replicas: 1`).
- **Helm works on OpenShift exactly as on Kubernetes** -- the Web Console adds a chart catalog for discovery, and Red Hat provides certified charts that are SCC-compatible.
- **Kustomize works on OpenShift via `oc apply -k`** -- both `oc` and `kubectl` embed Kustomize, and the overlay pattern is especially popular for GitOps workflows with ArgoCD.
- **Choose your tool by use case** -- Templates for quick OpenShift-native prototyping, Helm for distributable packages, Kustomize for environment-specific overlays in GitOps pipelines.

## Cleanup

```bash
# Delete all resources created by this lesson
oc delete all -l tutorial-level=1,tutorial-module=M3 -n template-demo

# Delete the uploaded template
oc delete template web-app-template -n template-demo

# Delete Kustomize-deployed resources
oc delete -k manifests/kustomize/overlays/dev/
oc delete -k manifests/kustomize/overlays/prod/

# Delete the project entirely
oc delete project template-demo

# Clean up the temporary parameter file
rm -f /tmp/params.env
```

## Next Steps

In **L1-M4.1 -- Services & Pod Networking**, you will explore how OpenShift handles pod-to-pod communication using the OVN-Kubernetes SDN, Multus for multiple network interfaces, and NetworkPolicy. You already know Kubernetes Services -- you will see what OpenShift layers on top.
