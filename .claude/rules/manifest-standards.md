# YAML Manifest Standards

## General Rules

- Use `apiVersion`, `kind`, `metadata`, `spec` ordering (standard K8s convention).
- Always include `metadata.labels` with at least `app: <name>`.
- Use `metadata.namespace` only when the lesson explicitly discusses cross-namespace scenarios — otherwise let the current project context handle it.
- Keep manifests minimal: only include fields relevant to the lesson concept.
- Use 2-space indentation (YAML standard).

## OpenShift-Specific Resources

### Routes

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: my-app
  labels:
    app: my-app
spec:
  to:
    kind: Service
    name: my-app
  port:
    targetPort: 8080
  tls:
    termination: edge
```

### BuildConfigs

```yaml
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: my-app
  labels:
    app: my-app
spec:
  source:
    type: Git
    git:
      uri: https://github.com/example/repo.git
  strategy:
    type: Source
    sourceStrategy:
      from:
        kind: ImageStreamTag
        namespace: openshift
        name: python:3.11-ubi9
  output:
    to:
      kind: ImageStreamTag
      name: my-app:latest
```

### ImageStreams

```yaml
apiVersion: image.openshift.io/v1
kind: ImageStream
metadata:
  name: my-app
  labels:
    app: my-app
```

### DeploymentConfigs (legacy — note this in lessons)

```yaml
apiVersion: apps.openshift.io/v1
kind: DeploymentConfig
metadata:
  name: my-app
spec:
  replicas: 1
  selector:
    app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
        - name: my-app
          image: my-app:latest
```

Prefer standard Kubernetes `Deployment` over `DeploymentConfig` in new lessons. Only use DC when teaching the DC-specific lesson (L1-M3.4).

## Comparison Manifests

When showing K8s vs OpenShift, put both in the `manifests/` directory with clear naming:

```
manifests/
  k8s-ingress.yaml
  openshift-route.yaml
```

Add a comment at the top of comparison files:

```yaml
# Kubernetes Ingress — the standard K8s approach
# Compare with openshift-route.yaml for the OpenShift equivalent
apiVersion: networking.k8s.io/v1
kind: Ingress
...
```

## Security Defaults

- Never set `runAsUser: 0` (root) without explaining why and the SCC implications.
- When a container needs elevated privileges, document which SCC is required and how to grant it.
- Default to `restricted` SCC-compatible manifests.

## Resource Limits

- Level 1: omit resource limits to keep manifests simple.
- Level 2: include resource requests/limits in production-style lessons.
- Level 3: always include resource requests and limits.

## Labels and Annotations

Use consistent labeling:

```yaml
metadata:
  labels:
    app: my-app
    tutorial-level: "1"
    tutorial-module: "M3"
```

The `tutorial-level` and `tutorial-module` labels make cleanup easier: `oc delete all -l tutorial-level=1,tutorial-module=M3`.
