# L1-M5.3 — ConfigMaps & Secrets

**Level:** Foundations
**Duration:** 20 min

## Overview

ConfigMaps and Secrets work the same way in OpenShift as they do in Kubernetes — but OpenShift adds CLI shortcuts that make creating and injecting configuration faster. In this lesson you will create ConfigMaps and Secrets using `oc` convenience commands, inject them into pods as environment variables and volume mounts, link Secrets to ServiceAccounts, and use `oc set env` to patch running workloads with configuration data on the fly.

## Prerequisites

- Completed: L1-M3.1 (oc new-app & Source-to-Image)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`

## K8s Context

You already know ConfigMaps and Secrets in Kubernetes. ConfigMaps hold non-sensitive key-value configuration data. Secrets hold sensitive data (passwords, tokens, keys) and are base64-encoded at rest. Both can be consumed by pods in two ways:

1. **Environment variables** — individual keys injected via `valueFrom.configMapKeyRef` or `valueFrom.secretKeyRef`.
2. **Volume mounts** — the entire ConfigMap or Secret projected as files inside the container filesystem.

In Kubernetes, you create them with `kubectl create configmap` and `kubectl create secret`, and you inject them by editing Deployment YAML. There is no shortcut to patch a running Deployment with new environment variables — you edit the manifest and reapply.

## Concepts

### `oc create configmap` and `oc create secret`

These commands work identically to their `kubectl` counterparts. OpenShift does not change the API resources — ConfigMaps and Secrets are standard Kubernetes objects. The `oc` CLI simply provides the same creation shortcuts:

```bash
oc create configmap <name> --from-literal=key=value
oc create configmap <name> --from-file=<path>
oc create secret generic <name> --from-literal=key=value
```

### `oc set env` — The OpenShift Shortcut

This is where OpenShift adds value. `oc set env` injects environment variables into a Deployment or other workload — without editing YAML. It can inject individual values, entire ConfigMaps, or entire Secrets in a single command:

```bash
# Inject a single literal value
oc set env deployment/my-app MY_VAR=my-value

# Inject all keys from a ConfigMap as env vars
oc set env deployment/my-app --from=configmap/my-config

# Inject all keys from a Secret as env vars
oc set env deployment/my-app --from=secret/my-secret
```

There is no `kubectl set env` equivalent. In Kubernetes, you would edit the Deployment YAML, add each `env` entry manually, and reapply.

### `oc set volume` for ConfigMaps and Secrets

You saw `oc set volume` in the previous lesson for PVCs. It also works with ConfigMaps and Secrets:

```bash
oc set volume deployment/my-app --add \
  --type=configmap \
  --configmap-name=my-config \
  --mount-path=/etc/config
```

### Linking Secrets to ServiceAccounts

OpenShift extends the ServiceAccount model with the ability to link Secrets for specific purposes. The most common use case is linking image pull secrets so that all pods running under a ServiceAccount can pull from a private registry:

```bash
oc secrets link <serviceaccount> <secret-name> --for=pull
```

This is an OpenShift-specific command. In Kubernetes, you add `imagePullSecrets` to each Pod spec or patch the ServiceAccount YAML manually.

## Step-by-Step

### Step 1: Create a Project

```bash
oc new-project config-lesson
```

### Step 2: Create a ConfigMap from the CLI

Create a ConfigMap using `oc create configmap` with literal values:

```bash
oc create configmap app-config \
  --from-literal=APP_ENV=production \
  --from-literal=APP_LOG_LEVEL=info \
  --from-literal=APP_MAX_CONNECTIONS=100
```

Verify:

```bash
oc get configmap app-config -o yaml
```

Expected output (data section):

```yaml
data:
  APP_ENV: production
  APP_LOG_LEVEL: info
  APP_MAX_CONNECTIONS: "100"
```

### Step 3: Add a File to the ConfigMap

You can also create ConfigMaps from files. Let's delete the previous one and recreate it from the manifest, which includes both literal keys and a multi-line properties file:

```bash
oc delete configmap app-config
oc apply -f manifests/configmap.yaml
```

```yaml
# manifests/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  labels:
    app: config-demo
    tutorial-level: "1"
    tutorial-module: "M5"
data:
  APP_ENV: "production"
  APP_LOG_LEVEL: "info"
  APP_MAX_CONNECTIONS: "100"
  app.properties: |
    server.port=8080
    server.context-path=/api
    feature.cache.enabled=true
    feature.debug.enabled=false
```

### Step 4: Create a Secret

Create a Secret using the CLI shortcut:

```bash
oc create secret generic app-credentials \
  --from-literal=db-user=appuser \
  --from-literal=db-password='s3cur3P@ss'
```

Verify:

```bash
oc get secret app-credentials -o yaml
```

The values are base64-encoded in the output. Decode them to confirm:

```bash
oc get secret app-credentials -o jsonpath='{.data.db-user}' | base64 -d
```

Expected output:

```
appuser
```

> **Note:** You can also apply the Secret from the manifest file (`oc apply -f manifests/secret.yaml`) instead of using the CLI. The CLI approach is convenient because you do not need to base64-encode values yourself — `oc create secret` handles that automatically.

### Step 5: Deploy a Pod That Consumes Both

Apply the pod manifest that injects the Secret as environment variables and mounts the ConfigMap as a volume:

```bash
oc apply -f manifests/pod-with-config.yaml
```

```yaml
# manifests/pod-with-config.yaml (abbreviated)
spec:
  containers:
    - name: app
      env:
        - name: DB_USER
          valueFrom:
            secretKeyRef:
              name: app-credentials
              key: db-user
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: app-credentials
              key: db-password
        - name: APP_ENV
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: APP_ENV
      volumeMounts:
        - name: config-volume
          mountPath: /etc/config
          readOnly: true
  volumes:
    - name: config-volume
      configMap:
        name: app-config
```

Wait for the pod to be ready:

```bash
oc wait pod/config-demo --for=condition=Ready --timeout=120s
```

Check the pod logs to see the injected values:

```bash
oc logs config-demo
```

Expected output:

```
=== Environment Variables from Secret ===
DB_USER=appuser
DB_PASSWORD=s3cur3P@ss

=== Environment Variables from ConfigMap ===
APP_ENV=production
APP_LOG_LEVEL=info

=== ConfigMap mounted as volume ===
server.port=8080
server.context-path=/api
feature.cache.enabled=true
feature.debug.enabled=false

Config demo running.
```

### Step 6: Verify the Volume Mount

List the files mounted from the ConfigMap:

```bash
oc exec config-demo -- ls /etc/config
```

Expected output:

```
APP_ENV
APP_LOG_LEVEL
APP_MAX_CONNECTIONS
app.properties
```

Each key in the ConfigMap becomes a file. Read the properties file:

```bash
oc exec config-demo -- cat /etc/config/app.properties
```

### Step 7: Use `oc set env` to Inject Config into a Deployment

Now let's see the OpenShift shortcut in action. Create a simple Deployment:

```bash
oc create deployment env-demo --image=registry.access.redhat.com/ubi9/ubi-minimal:latest -- sleep infinity
oc rollout status deployment/env-demo --timeout=120s
```

Inject all keys from the ConfigMap as environment variables in one command:

```bash
oc set env deployment/env-demo --from=configmap/app-config
```

Expected output:

```
deployment.apps/env-demo updated
```

This triggers a rollout. Wait for it:

```bash
oc rollout status deployment/env-demo --timeout=120s
```

Verify the environment variables are set:

```bash
oc set env deployment/env-demo --list
```

Expected output:

```
# deployments/env-demo, container app
# configmap/app-config
APP_ENV=production
APP_LOG_LEVEL=info
APP_MAX_CONNECTIONS=100
app.properties=server.port=8080
...
```

Now inject the Secret:

```bash
oc set env deployment/env-demo --from=secret/app-credentials
```

List all environment variables again:

```bash
oc set env deployment/env-demo --list
```

Expected output now includes both the ConfigMap and Secret values:

```
# deployments/env-demo, container app
# configmap/app-config
APP_ENV=production
APP_LOG_LEVEL=info
APP_MAX_CONNECTIONS=100
...
# secret/app-credentials
db-user=appuser
db-password=s3cur3P@ss
```

### Step 8: Link a Secret to a ServiceAccount

Create an image pull secret (simulating a private registry credential):

```bash
oc create secret docker-registry my-registry-creds \
  --docker-server=registry.example.com \
  --docker-username=myuser \
  --docker-password=mypassword
```

Link it to the default ServiceAccount so all pods in this project can pull from that registry:

```bash
oc secrets link default my-registry-creds --for=pull
```

Verify:

```bash
oc get serviceaccount default -o jsonpath='{.imagePullSecrets[*].name}'
```

Expected output includes:

```
my-registry-creds
```

Any pod using the `default` ServiceAccount in this project will now automatically use `my-registry-creds` when pulling images from `registry.example.com`.

> **K8s equivalent:** In Kubernetes, you would either add `imagePullSecrets` to every Pod spec, or manually patch the ServiceAccount with `kubectl patch serviceaccount default -p '{"imagePullSecrets": [{"name": "my-registry-creds"}]}'`. The `oc secrets link` command is a cleaner, purpose-built shortcut.

## Verification

Run these commands to verify the lesson worked:

```bash
# 1. ConfigMap exists with all keys
oc get configmap app-config -o jsonpath='{.data.APP_ENV}'
# Expected: production

# 2. Secret exists and is decodable
oc get secret app-credentials -o jsonpath='{.data.db-user}' | base64 -d
# Expected: appuser

# 3. Pod has Secret values in its environment
oc exec config-demo -- sh -c 'echo $DB_USER'
# Expected: appuser

# 4. Pod has ConfigMap mounted as files
oc exec config-demo -- cat /etc/config/app.properties
# Expected: Shows the properties file content

# 5. oc set env injected ConfigMap into the Deployment
oc set env deployment/env-demo --list | grep APP_ENV
# Expected: APP_ENV=production

# 6. Secret is linked to the default ServiceAccount
oc get serviceaccount default -o jsonpath='{.imagePullSecrets[*].name}' | grep my-registry-creds
# Expected: my-registry-creds
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Creating ConfigMaps | `kubectl create configmap` | `oc create configmap` (identical) |
| Creating Secrets | `kubectl create secret` | `oc create secret` (identical) |
| Injecting env vars into a Deployment | Edit YAML, add `env` entries, reapply | `oc set env deployment/name --from=configmap/name` |
| Listing env vars on a workload | `kubectl describe` and parse output | `oc set env deployment/name --list` |
| Mounting as volumes | Edit YAML, add `volumes` and `volumeMounts` | `oc set volume --add --type=configmap` or edit YAML |
| Linking pull secrets to ServiceAccounts | Patch ServiceAccount YAML manually | `oc secrets link sa-name secret --for=pull` |
| ConfigMap/Secret API resources | Standard K8s API | Identical — no OpenShift-specific CRDs |

## Key Takeaways

- **ConfigMaps and Secrets are standard Kubernetes resources** — OpenShift does not change their API or behavior. If you know how they work in K8s, they work the same way here.
- **`oc set env` is the key OpenShift shortcut** — it injects environment variables from ConfigMaps, Secrets, or literal values into workloads without editing YAML. There is no `kubectl` equivalent.
- **`oc set env --list` shows all env vars** on a workload in a clean, readable format — much easier than parsing `kubectl describe` output.
- **`oc secrets link` connects Secrets to ServiceAccounts** — this is the OpenShift way to configure image pull credentials project-wide, instead of adding `imagePullSecrets` to every Pod spec.
- **Volume mounts work identically to Kubernetes** — each key in a ConfigMap or Secret becomes a file in the mounted directory.

## Cleanup

```bash
# Delete the config-demo Pod
oc delete pod config-demo

# Delete the env-demo Deployment
oc delete deployment env-demo

# Delete ConfigMap, Secrets
oc delete configmap app-config
oc delete secret app-credentials
oc delete secret my-registry-creds

# Delete the project
oc delete project config-lesson
```

## Next Steps

In **L1-M6.1 — Built-in Monitoring Stack**, you will explore OpenShift's pre-installed Prometheus and Grafana monitoring. In Kubernetes you install and configure monitoring yourself — OpenShift ships it out of the box with separate cluster monitoring and user workload monitoring stacks.
