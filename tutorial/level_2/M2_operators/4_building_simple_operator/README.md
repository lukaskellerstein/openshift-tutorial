# L2-M2.4 — Building a Simple Operator

**Level:** Practitioner
**Duration:** 1.5 hr

## Overview

In previous lessons you installed operators from OperatorHub and consumed their CRDs. Now you will build your own operator from scratch using the Operator SDK. You will scaffold a Go-based operator that manages a custom `WebApp` resource, implement the reconciliation loop, define a CRD, build the operator image, deploy it to your OpenShift cluster, and bundle it for OLM distribution. This lesson also includes an Ansible-based alternative for teams that prefer YAML-driven automation over Go.

If you have built custom controllers in Kubernetes using `controller-runtime` or `kubebuilder`, you already understand the core pattern. The Operator SDK builds on kubebuilder and adds OpenShift/OLM integration -- scaffolding, bundle generation, scorecard testing, and catalog publishing -- so you can go from idea to OperatorHub in a single workflow.

## Prerequisites

- Completed: L2-M2.3 (Using Operators: Database Example)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `kubeadmin` (cluster-admin required for CRD creation)
- Go 1.21+ installed (`go version`)
- Operator SDK v1.34+ installed (`operator-sdk version`)
- Podman installed (`podman version`) -- used for building operator images
- Access to a container registry you can push to (Quay.io free account, or the OpenShift internal registry)

> **Installing the Operator SDK:** Follow the official guide at https://sdk.operatorframework.io/docs/installation/. On macOS: `brew install operator-sdk`. On Linux, download the binary from the GitHub releases page.

## K8s Context

In vanilla Kubernetes, extending the platform means writing a custom controller:

1. Define a CRD (CustomResourceDefinition) to describe your new resource type.
2. Write a controller that watches for instances of that CRD and reconciles actual state to match desired state.
3. Package the controller as a container image, deploy it with a Deployment, and wire up RBAC (ServiceAccount, ClusterRole, ClusterRoleBinding).

Tools like kubebuilder and controller-runtime handle the boilerplate -- watch setup, event queuing, leader election. But you still need to manually manage versioning, upgrades, and distribution yourself.

In OpenShift, the Operator SDK adds:
- **OLM integration** -- package your operator as a bundle so it appears in OperatorHub.
- **Scorecard testing** -- validate your operator against best practices.
- **Multiple authoring options** -- Go, Ansible, or Helm-based operators.
- **Built-in Makefile targets** -- for building, pushing, bundling, and deploying.

## Concepts

### The Reconciliation Loop

Every operator follows the same pattern:

```
User creates/updates CR  -->  Controller sees the event  -->  Reconcile() runs
                                                                  |
                                     Compare desired state (CR spec) with actual state (cluster)
                                                                  |
                                     Create / Update / Delete child resources as needed
                                                                  |
                                     Update CR status with current state
                                                                  |
                                     Return: Requeue (retry later) or Done
```

The `Reconcile()` function is idempotent. Kubernetes calls it whenever something changes (or on a timer), and your job is to make actual state match desired state. You never watch for specific events -- you just respond to "the world changed, fix it."

### What We Are Building

A `WebApp` operator that manages simple web applications. When a user creates a `WebApp` custom resource:

```yaml
apiVersion: tutorial.openshift.io/v1alpha1
kind: WebApp
metadata:
  name: my-app
spec:
  image: quay.io/redhattraining/hello-world-nginx:latest
  replicas: 2
  port: 8080
  routeEnabled: true
```

The operator automatically creates:
- A **Deployment** with the specified image and replica count
- A **Service** exposing the specified port
- A **Route** (if `routeEnabled: true`) to expose the app externally

This is a realistic pattern -- many production operators manage exactly this kind of resource graph.

### Go vs Ansible Operators

| Aspect | Go | Ansible |
|--------|----|---------|
| Language | Go (strongly typed) | YAML + Jinja2 |
| Performance | High (compiled binary) | Lower (Ansible runtime overhead) |
| Complexity ceiling | Unlimited | Limited to what Ansible modules support |
| Learning curve | Steeper (Go, controller-runtime) | Gentler (if you know Ansible) |
| Best for | Complex state machines, high-performance reconciliation | Configuration management, day-2 ops, simple CR-to-resource mappings |

This lesson focuses on the Go-based approach with an Ansible alternative in the appendix.

### OLM Bundles

An OLM (Operator Lifecycle Manager) bundle packages everything needed to install your operator:

```
bundle/
  manifests/
    my-operator.clusterserviceversion.yaml   # The CSV -- describes the operator
    my-crd.yaml                               # The CRD
  metadata/
    annotations.yaml                          # Bundle metadata
  Dockerfile                                  # Bundle image Dockerfile
```

The CSV (ClusterServiceVersion) is the key file -- it tells OLM what the operator does, what permissions it needs, what CRDs it owns, and how to install it.

## Step-by-Step

### Step 1: Scaffold the Operator Project

Create a new directory and initialize the operator project with the Operator SDK.

```bash
mkdir -p ~/webapp-operator && cd ~/webapp-operator

operator-sdk init \
  --domain openshift.io \
  --repo github.com/example/webapp-operator \
  --project-name webapp-operator
```

**Expected output:**
```
Writing kustomize manifests for you to edit...
Writing scaffold for you to edit...
Get controller runtime:
$ go get sigs.k8s.io/controller-runtime@v0.17.2
...
Next: define a resource with:
$ operator-sdk create api
```

This creates the standard project layout:

```
webapp-operator/
  Dockerfile          # Operator image build
  Makefile             # Build, test, deploy targets
  PROJECT              # Operator SDK project metadata
  go.mod / go.sum      # Go module dependencies
  cmd/main.go          # Entry point
  config/              # Kustomize bases for RBAC, CRDs, deployment
  internal/controller/ # Where your reconciliation logic goes
```

### Step 2: Create the API and Controller

Scaffold the `WebApp` custom resource and controller:

```bash
cd ~/webapp-operator

operator-sdk create api \
  --group tutorial \
  --version v1alpha1 \
  --kind WebApp \
  --resource --controller
```

**Expected output:**
```
Writing kustomize manifests for you to edit...
Writing scaffold for you to edit...
api/v1alpha1/webapp_types.go
api/v1alpha1/groupversion_info.go
internal/controller/webapp_controller.go
internal/controller/suite_test.go
...
Update dependencies:
$ make generate
```

### Step 3: Define the WebApp Custom Resource

Edit `api/v1alpha1/webapp_types.go` to define the CRD spec and status. Replace the file contents with the following (the full source is in `app/api/v1alpha1/webapp_types.go`):

```go
package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// WebAppSpec defines the desired state of WebApp
type WebAppSpec struct {
	// Image is the container image for the web application
	// +kubebuilder:validation:Required
	Image string `json:"image"`

	// Replicas is the number of desired pod replicas
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=10
	// +kubebuilder:default=1
	Replicas int32 `json:"replicas,omitempty"`

	// Port is the container port the application listens on
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=65535
	// +kubebuilder:default=8080
	Port int32 `json:"port,omitempty"`

	// RouteEnabled controls whether an OpenShift Route is created
	// +kubebuilder:default=true
	RouteEnabled bool `json:"routeEnabled,omitempty"`

	// Resources defines CPU and memory requests/limits
	// +optional
	Resources *ResourceRequirements `json:"resources,omitempty"`
}

// ResourceRequirements defines compute resource requirements
type ResourceRequirements struct {
	// CPURequest is the CPU request (e.g., "100m")
	CPURequest string `json:"cpuRequest,omitempty"`
	// CPULimit is the CPU limit (e.g., "500m")
	CPULimit string `json:"cpuLimit,omitempty"`
	// MemoryRequest is the memory request (e.g., "64Mi")
	MemoryRequest string `json:"memoryRequest,omitempty"`
	// MemoryLimit is the memory limit (e.g., "128Mi")
	MemoryLimit string `json:"memoryLimit,omitempty"`
}

// WebAppStatus defines the observed state of WebApp
type WebAppStatus struct {
	// Conditions represent the latest available observations of the WebApp's state
	Conditions []metav1.Condition `json:"conditions,omitempty"`
	// AvailableReplicas is the number of ready replicas
	AvailableReplicas int32 `json:"availableReplicas,omitempty"`
	// RouteURL is the externally accessible URL (if route is enabled)
	RouteURL string `json:"routeURL,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Image",type=string,JSONPath=`.spec.image`
// +kubebuilder:printcolumn:name="Replicas",type=integer,JSONPath=`.spec.replicas`
// +kubebuilder:printcolumn:name="Available",type=integer,JSONPath=`.status.availableReplicas`
// +kubebuilder:printcolumn:name="URL",type=string,JSONPath=`.status.routeURL`
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"

// WebApp is the Schema for the webapps API
type WebApp struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   WebAppSpec   `json:"spec,omitempty"`
	Status WebAppStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// WebAppList contains a list of WebApp
type WebAppList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []WebApp `json:"items"`
}

func init() {
	SchemeBuilder.Register(&WebApp{}, &WebAppList{})
}
```

Key points:
- **`+kubebuilder` markers** generate CRD validation, defaults, and additional printer columns.
- **`+kubebuilder:subresource:status`** creates a `/status` subresource so status updates do not trigger reconciliation.
- **`+kubebuilder:printcolumn`** adds columns to `oc get webapp` output.

After editing, regenerate the deep copy methods and CRD manifests:

```bash
make generate
make manifests
```

**Expected output:**
```
/home/user/webapp-operator/bin/controller-gen object:headerFile="hack/boilerplate.go.txt" paths="./..."
/home/user/webapp-operator/bin/controller-gen rbac:roleName=manager-role crd webhook paths="./..." output:crd:artifacts:config=config/crd/bases
```

### Step 4: Implement the Reconciliation Loop

This is the core of the operator. Edit `internal/controller/webapp_controller.go` with the reconciliation logic. The full source is provided in `app/internal/controller/webapp_controller.go`.

Here is the key `Reconcile()` function (simplified for readability):

```go
func (r *WebAppReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    log := log.FromContext(ctx)

    // 1. Fetch the WebApp custom resource
    webapp := &tutorialv1alpha1.WebApp{}
    if err := r.Get(ctx, req.NamespacedName, webapp); err != nil {
        if apierrors.IsNotFound(err) {
            log.Info("WebApp resource not found — probably deleted")
            return ctrl.Result{}, nil
        }
        return ctrl.Result{}, err
    }

    // 2. Reconcile the Deployment
    deployment := &appsv1.Deployment{}
    err := r.Get(ctx, types.NamespacedName{Name: webapp.Name, Namespace: webapp.Namespace}, deployment)
    if err != nil && apierrors.IsNotFound(err) {
        // Create the Deployment
        dep := r.deploymentForWebApp(webapp)
        if err := controllerutil.SetControllerReference(webapp, dep, r.Scheme); err != nil {
            return ctrl.Result{}, err
        }
        log.Info("Creating Deployment", "name", dep.Name)
        if err := r.Create(ctx, dep); err != nil {
            return ctrl.Result{}, err
        }
    } else if err == nil {
        // Update if spec changed
        if *deployment.Spec.Replicas != webapp.Spec.Replicas ||
            deployment.Spec.Template.Spec.Containers[0].Image != webapp.Spec.Image {
            deployment.Spec.Replicas = &webapp.Spec.Replicas
            deployment.Spec.Template.Spec.Containers[0].Image = webapp.Spec.Image
            log.Info("Updating Deployment", "name", deployment.Name)
            if err := r.Update(ctx, deployment); err != nil {
                return ctrl.Result{}, err
            }
        }
    }

    // 3. Reconcile the Service
    // (similar pattern: get, create-if-missing, update-if-changed)

    // 4. Reconcile the Route (if routeEnabled)
    // (similar pattern, skip if routeEnabled is false, delete if it exists but should not)

    // 5. Update status
    webapp.Status.AvailableReplicas = deployment.Status.AvailableReplicas
    if route exists {
        webapp.Status.RouteURL = "https://" + route.Spec.Host
    }
    if err := r.Status().Update(ctx, webapp); err != nil {
        return ctrl.Result{}, err
    }

    return ctrl.Result{}, nil
}
```

The pattern in every reconciliation step is the same:
1. **Get** the child resource.
2. If it does not exist, **Create** it with `SetControllerReference` (so it gets garbage collected when the parent CR is deleted).
3. If it exists, **compare** desired vs actual state and **Update** if they differ.
4. **Update status** on the parent CR.

> **SetControllerReference** is critical. It sets an `ownerReference` on the child resource pointing back to the WebApp CR. When the WebApp is deleted, Kubernetes garbage collection automatically deletes the Deployment, Service, and Route. Without this, you would need to implement finalizers.

### Step 5: Add RBAC Markers

The controller needs permissions to manage Deployments, Services, and Routes. Add RBAC markers above the `Reconcile` function:

```go
// +kubebuilder:rbac:groups=tutorial.openshift.io,resources=webapps,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=tutorial.openshift.io,resources=webapps/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=tutorial.openshift.io,resources=webapps/finalizers,verbs=update
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=route.openshift.io,resources=routes,verbs=get;list;watch;create;update;patch;delete
```

Then regenerate the RBAC manifests:

```bash
make manifests
```

This updates `config/rbac/role.yaml` with the necessary ClusterRole permissions.

### Step 6: Build and Push the Operator Image

Set your image registry and build the operator:

```bash
# Set your registry (replace with your own)
export IMG=quay.io/<your-username>/webapp-operator:v0.0.1

# Build the operator image with Podman
make docker-build IMG=$IMG

# Push to the registry
make docker-push IMG=$IMG
```

> **Using Podman instead of Docker:** The Makefile uses `docker` by default. Override this:
> ```bash
> # Either set the CONTAINER_TOOL variable:
> make docker-build docker-push IMG=$IMG CONTAINER_TOOL=podman
>
> # Or add to your Makefile:
> # CONTAINER_TOOL ?= podman
> ```

> **Using CRC's internal registry:** If you do not have an external registry, you can push to CRC's internal registry:
> ```bash
> # Expose the internal registry
> oc patch configs.imageregistry.operator.openshift.io/cluster \
>   --type=merge -p '{"spec":{"defaultRoute":true}}'
>
> # Get the route
> REGISTRY=$(oc get route default-route -n openshift-image-registry -o jsonpath='{.spec.host}')
>
> # Log in with Podman
> podman login -u kubeadmin -p $(oc whoami -t) $REGISTRY --tls-verify=false
>
> # Use the internal registry as your IMG
> export IMG=$REGISTRY/webapp-operator/webapp-operator:v0.0.1
> ```

### Step 7: Deploy the Operator to OpenShift

Create a project and deploy:

```bash
# Create a project for the operator
oc new-project webapp-operator-system

# Deploy the operator (installs CRD, RBAC, Deployment)
make deploy IMG=$IMG
```

**Expected output:**
```
namespace/webapp-operator-system configured
customresourcedefinition.apiextensions.k8s.io/webapps.tutorial.openshift.io created
serviceaccount/webapp-operator-controller-manager created
role.rbac.authorization.k8s.io/webapp-operator-leader-election-role created
clusterrole.rbac.authorization.k8s.io/webapp-operator-manager-role created
...
deployment.apps/webapp-operator-controller-manager created
```

Verify the operator is running:

```bash
oc get pods -n webapp-operator-system
```

**Expected output:**
```
NAME                                                     READY   STATUS    RESTARTS   AGE
webapp-operator-controller-manager-6d4b7c8f9d-x2k4r     2/2     Running   0          30s
```

The pod has 2 containers: the operator itself and `kube-rbac-proxy` (a sidecar that protects the metrics endpoint).

### Step 8: Create a WebApp Custom Resource

Now switch to a user project and create a WebApp instance:

```bash
# Create a project for the application
oc new-project webapp-demo

# Apply the sample WebApp CR
oc apply -f manifests/webapp-sample.yaml
```

The sample CR (`manifests/webapp-sample.yaml`):

```yaml
apiVersion: tutorial.openshift.io/v1alpha1
kind: WebApp
metadata:
  name: hello-web
  labels:
    app: hello-web
    tutorial-level: "2"
    tutorial-module: "M2"
spec:
  image: quay.io/redhattraining/hello-world-nginx:latest
  replicas: 2
  port: 8080
  routeEnabled: true
  resources:
    cpuRequest: "100m"
    cpuLimit: "500m"
    memoryRequest: "64Mi"
    memoryLimit: "128Mi"
```

Watch the operator create the child resources:

```bash
# Check the WebApp status
oc get webapp hello-web

# Expected output:
# NAME        IMAGE                                                  REPLICAS   AVAILABLE   URL                                                AGE
# hello-web   quay.io/redhattraining/hello-world-nginx:latest        2          2           https://hello-web-webapp-demo.apps-crc.testing      15s

# See the resources the operator created
oc get deployment,service,route -l app=hello-web
```

**Expected output:**
```
NAME                        READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/hello-web   2/2     2             2           30s

NAME                TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
service/hello-web   ClusterIP   172.30.45.123   <none>        8080/TCP   30s

NAME                                HOST/PORT                                    PATH   SERVICES    PORT   TERMINATION   WILDCARD
route.route.openshift.io/hello-web  hello-web-webapp-demo.apps-crc.testing              hello-web   8080   edge          None
```

### Step 9: Test the Reconciliation Loop

The real power of an operator is continuous reconciliation. Test that it corrects drift:

```bash
# Delete the deployment manually -- the operator should recreate it
oc delete deployment hello-web
echo "Waiting for operator to reconcile..."
sleep 5
oc get deployment hello-web

# Expected output: the deployment is back
# NAME        READY   UP-TO-DATE   AVAILABLE   AGE
# hello-web   2/2     2             2           3s

# Scale via the CR (not by editing the deployment directly)
oc patch webapp hello-web --type=merge -p '{"spec":{"replicas":3}}'
sleep 3
oc get deployment hello-web

# Expected output: now 3 replicas
# NAME        READY   UP-TO-DATE   AVAILABLE   AGE
# hello-web   3/3     3             3           45s
```

> **Important:** Always modify the CR, not the child resources. If you scale the Deployment directly with `oc scale`, the operator will revert it on the next reconciliation.

### Step 10: Disable the Route via CR Update

```bash
# Turn off the route
oc patch webapp hello-web --type=merge -p '{"spec":{"routeEnabled":false}}'
sleep 3
oc get route hello-web 2>/dev/null || echo "Route deleted by operator"

# Expected output:
# Route deleted by operator

# Re-enable it
oc patch webapp hello-web --type=merge -p '{"spec":{"routeEnabled":true}}'
sleep 3
oc get route hello-web

# Expected output: route is recreated
```

### Step 11: Create an OLM Bundle

To distribute your operator via OperatorHub, create an OLM bundle:

```bash
cd ~/webapp-operator

# Generate the bundle (CSV, CRD, annotations)
make bundle IMG=$IMG \
  BUNDLE_CHANNELS=alpha \
  BUNDLE_DEFAULT_CHANNEL=alpha

# This creates:
# bundle/
#   manifests/
#     webapp-operator.clusterserviceversion.yaml
#     tutorial.openshift.io_webapps.yaml
#   metadata/
#     annotations.yaml
#   bundle.Dockerfile
```

The generated CSV (`bundle/manifests/webapp-operator.clusterserviceversion.yaml`) contains:
- Operator metadata (name, description, icon, maintainers)
- RBAC permissions (from your `+kubebuilder:rbac` markers)
- Install strategy (the Deployment spec for your operator)
- Owned CRDs (WebApp)

Edit the CSV to add a meaningful description, icon, and examples:

```bash
# Validate the bundle
operator-sdk bundle validate ./bundle
```

**Expected output:**
```
INFO[0000] All validation tests have completed successfully
```

Build and push the bundle image:

```bash
export BUNDLE_IMG=quay.io/<your-username>/webapp-operator-bundle:v0.0.1
make bundle-build bundle-push BUNDLE_IMG=$BUNDLE_IMG
```

### Step 12: Test the Bundle with OLM (Optional)

If OLM is installed on your cluster (it is on OpenShift by default):

```bash
# Run the bundle directly (without a catalog)
operator-sdk run bundle $BUNDLE_IMG -n webapp-operator-system

# This creates a temporary CatalogSource and installs the operator
# Verify:
oc get csv -n webapp-operator-system

# Expected output:
# NAME                         DISPLAY          VERSION   REPLACES   PHASE
# webapp-operator.v0.0.1       WebApp Operator  0.0.1                Succeeded
```

To clean up the OLM-installed operator:

```bash
operator-sdk cleanup webapp-operator -n webapp-operator-system
```

## Verification

Run through this checklist to confirm everything works:

```bash
# 1. CRD is installed
oc get crd webapps.tutorial.openshift.io
# Should show the CRD with CREATED AT timestamp

# 2. Operator pod is running
oc get pods -n webapp-operator-system
# Should show 1 pod with 2/2 READY

# 3. Check operator logs for reconciliation
oc logs -n webapp-operator-system deployment/webapp-operator-controller-manager -c manager | tail -20
# Should show "Creating Deployment", "Creating Service", "Creating Route" messages

# 4. WebApp CR has correct status
oc get webapp hello-web -n webapp-demo -o yaml | grep -A 10 "status:"
# Should show availableReplicas and routeURL

# 5. Route is accessible
curl -k https://hello-web-webapp-demo.apps-crc.testing
# Should return the hello-world-nginx page

# 6. Drift correction works
oc delete svc hello-web -n webapp-demo && sleep 5 && oc get svc hello-web -n webapp-demo
# Service should be recreated by the operator
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Scaffolding tool | kubebuilder | Operator SDK (wraps kubebuilder, adds OLM support) |
| Authoring options | Go only (kubebuilder) | Go, Ansible, or Helm (Operator SDK) |
| Distribution | Manually deploy YAML or use Helm | OLM bundles, OperatorHub catalog |
| Lifecycle management | Manual upgrades | OLM handles install, upgrade, and removal |
| Discovery | No built-in catalog | OperatorHub in Web Console |
| RBAC for operators | Write ClusterRole by hand | Generated from `+kubebuilder:rbac` markers |
| Ingress for managed apps | Write Ingress + install controller | Route API built-in, operator creates Routes natively |
| Testing | Manual or custom CI | `operator-sdk scorecard` validates best practices |
| Security | No default restrictions | Operator pod runs under `restricted` SCC; images must not require root |
| Metrics | Set up Prometheus yourself | Prometheus auto-discovers operator metrics via ServiceMonitor |

## Key Takeaways

- **The Operator SDK extends kubebuilder** with OLM integration, multiple language support (Go, Ansible, Helm), and scorecard testing -- it is the standard tool for building operators on OpenShift.
- **The reconciliation loop is idempotent** -- your `Reconcile()` function compares desired state (the CR spec) to actual state (cluster resources) and corrects drift. Never assume specific events; always read current state.
- **Owner references are essential** -- `SetControllerReference` ensures child resources (Deployments, Services, Routes) are garbage collected when the parent CR is deleted, avoiding resource leaks.
- **OLM bundles are the distribution mechanism** -- packaging your operator as a bundle with a CSV enables installation via OperatorHub, automatic upgrades, and dependency resolution.
- **OpenShift operators can manage Routes natively** -- unlike vanilla Kubernetes operators that must handle Ingress and controller dependencies, OpenShift operators can create Routes directly since the HAProxy router is always available.

## Troubleshooting

### Operator pod is CrashLoopBackOff

```bash
oc logs -n webapp-operator-system deployment/webapp-operator-controller-manager -c manager --previous
```

Common causes:
- **RBAC permissions missing:** Check that your `+kubebuilder:rbac` markers include all resources the operator manages. Run `make manifests` after adding markers.
- **CRD not installed:** The operator will crash if it tries to watch a CRD that does not exist. Run `make install` to install CRDs.
- **Image pull error:** Verify `IMG` points to an accessible registry. Check `oc get events -n webapp-operator-system`.

### WebApp CR created but no Deployment appears

```bash
# Check operator logs
oc logs -n webapp-operator-system deployment/webapp-operator-controller-manager -c manager | grep -i error

# Common cause: the operator's ClusterRole does not have permission to create
# Deployments in the user's namespace. Check:
oc get clusterrolebinding | grep webapp-operator
```

### Route not created

- Verify `routeEnabled: true` in the CR spec.
- Check that the RBAC markers include `route.openshift.io`.
- The operator needs a ClusterRole (not a namespaced Role) to create Routes in any namespace.

### "no matches for kind WebApp" error

The CRD is not installed. Run:
```bash
make install
# or
oc apply -f config/crd/bases/tutorial.openshift.io_webapps.yaml
```

### SCC issues with the managed application

If the application image requires root (for example, some nginx images), the Deployment will fail. Fix by either:
- Using a non-root image (e.g., `quay.io/redhattraining/hello-world-nginx` which is OpenShift-compatible).
- Granting `anyuid` SCC to the application's ServiceAccount (not the operator's SA):
  ```bash
  oc adm policy add-scc-to-user anyuid -z default -n webapp-demo
  ```
  As discussed in L1-M2.4 (Security Context Constraints), this loosens security and should be avoided in production.

## Cleanup

```bash
# Delete the WebApp CR (owner references will cascade-delete child resources)
oc delete webapp hello-web -n webapp-demo

# Undeploy the operator
cd ~/webapp-operator
make undeploy

# Delete the projects
oc delete project webapp-demo
oc delete project webapp-operator-system

# Remove CRDs (if make undeploy did not do it)
oc delete crd webapps.tutorial.openshift.io 2>/dev/null

# Clean up OLM bundle (if you tested with OLM)
operator-sdk cleanup webapp-operator -n webapp-operator-system 2>/dev/null

# Optionally remove the local project directory
rm -rf ~/webapp-operator
```

## Appendix: Ansible-Based Alternative

If your team prefers Ansible over Go, the Operator SDK supports Ansible-based operators. Here is the equivalent scaffolding:

```bash
mkdir -p ~/webapp-operator-ansible && cd ~/webapp-operator-ansible

operator-sdk init \
  --plugins=ansible \
  --domain openshift.io \
  --project-name webapp-operator

operator-sdk create api \
  --group tutorial \
  --version v1alpha1 \
  --kind WebApp \
  --generate-role
```

This creates a `roles/webapp/` directory. Edit `roles/webapp/tasks/main.yml`:

```yaml
---
- name: Create Deployment for WebApp
  kubernetes.core.k8s:
    state: present
    definition:
      apiVersion: apps/v1
      kind: Deployment
      metadata:
        name: "{{ ansible_operator_meta.name }}"
        namespace: "{{ ansible_operator_meta.namespace }}"
        labels:
          app: "{{ ansible_operator_meta.name }}"
      spec:
        replicas: "{{ replicas | default(1) }}"
        selector:
          matchLabels:
            app: "{{ ansible_operator_meta.name }}"
        template:
          metadata:
            labels:
              app: "{{ ansible_operator_meta.name }}"
          spec:
            containers:
              - name: webapp
                image: "{{ image }}"
                ports:
                  - containerPort: "{{ port | default(8080) }}"

- name: Create Service for WebApp
  kubernetes.core.k8s:
    state: present
    definition:
      apiVersion: v1
      kind: Service
      metadata:
        name: "{{ ansible_operator_meta.name }}"
        namespace: "{{ ansible_operator_meta.namespace }}"
      spec:
        selector:
          app: "{{ ansible_operator_meta.name }}"
        ports:
          - port: "{{ port | default(8080) }}"
            targetPort: "{{ port | default(8080) }}"

- name: Create Route for WebApp (if enabled)
  kubernetes.core.k8s:
    state: present
    definition:
      apiVersion: route.openshift.io/v1
      kind: Route
      metadata:
        name: "{{ ansible_operator_meta.name }}"
        namespace: "{{ ansible_operator_meta.namespace }}"
      spec:
        to:
          kind: Service
          name: "{{ ansible_operator_meta.name }}"
        port:
          targetPort: "{{ port | default(8080) }}"
        tls:
          termination: edge
  when: route_enabled | default(true) | bool
```

The Ansible operator reads CR spec fields as Ansible variables (snake_case: `routeEnabled` becomes `route_enabled`). The `kubernetes.core.k8s` module is idempotent -- it creates or updates resources to match the definition.

Build and deploy the same way as the Go operator:

```bash
make docker-build docker-push IMG=$IMG CONTAINER_TOOL=podman
make deploy IMG=$IMG
```

## Next Steps

In **L2-M3.1 — OpenShift Service Mesh (Istio)**, you will install the Service Mesh operator (itself an operator!) and learn how Istio integrates with OpenShift. You will configure sidecar injection, traffic management, and mTLS -- building on the operator concepts you learned in this module to understand how complex operators manage interconnected resources across the cluster.
