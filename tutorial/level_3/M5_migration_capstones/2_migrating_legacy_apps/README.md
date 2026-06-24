# L3-M5.2 — Migrating Legacy Apps to OpenShift

**Level:** Expert
**Duration:** 45 min

## Overview

Most enterprises still run a significant portion of their workloads on virtual machines -- Java EE application servers, .NET Framework services, monolithic PHP apps, and custom C/C++ daemons. Moving these to OpenShift is not a simple `docker build`. This lesson teaches you a systematic approach to containerizing VM-based applications, leveraging OpenShift's Source-to-Image (S2I) builds for legacy codebases, and choosing the right migration strategy (lift-and-shift, replatform, or refactor) based on application characteristics. You will also learn how to use the Konveyor/Tackle toolkit for portfolio-level application assessment and migration wave planning.

In Kubernetes, you containerize applications manually and deploy them. OpenShift adds an entire migration ecosystem -- built-in build strategies, image streams, and integration with assessment tools -- that reduces the gap between "legacy VM app" and "production container workload."

## Prerequisites

- Completed: L3-M5.1 (Migrating from Kubernetes to OpenShift)
- OpenShift cluster running (CRC or Developer Sandbox)
- Familiarity with S2I concepts from L1-M3.1 and BuildConfigs from L1-M3.2
- `oc` CLI installed and authenticated
- Basic understanding of Java (Maven/Gradle), .NET, or Python build systems

## K8s Context

In vanilla Kubernetes, containerizing a legacy application follows a well-known pattern:

1. Write a Dockerfile (or use a multi-stage build)
2. Build the image with `docker build` or `kaniko`
3. Push to a container registry
4. Write Deployment, Service, and Ingress manifests
5. Deploy with `kubectl apply`

This process is entirely manual. You choose base images, write build instructions, set up a CI pipeline, and manage image lifecycle yourself. There is no built-in assessment tooling, no opinionated build framework, and no portfolio-level migration planning.

For legacy apps that cannot be easily containerized (e.g., they depend on specific OS-level services, use systemd, or require persistent local state), Kubernetes offers no built-in answer -- you either refactor the app or keep it on VMs.

## Concepts

### Migration Strategies: The Three Rs

Not every legacy application should be migrated the same way. The industry uses several models (Gartner's "6 Rs," AWS's "7 Rs"), but for containerization onto OpenShift, three strategies matter most:

```
+-------------------------------------------------------------------+
|                  Migration Strategy Spectrum                       |
|                                                                    |
|  Lift-and-Shift       Replatform            Refactor               |
|  (Rehost)             (Repackage)           (Re-architect)         |
|                                                                    |
|  Lowest effort        Medium effort         Highest effort         |
|  Lowest benefit        Medium benefit        Highest benefit       |
|                                                                    |
|  Container wraps       Adapt to platform     Redesign as           |
|  the existing app      conventions           cloud-native          |
|  as-is                                       microservices         |
|                                                                    |
|  Examples:             Examples:             Examples:             |
|  - WAR in Tomcat       - S2I build from      - Break monolith     |
|    container             source               into services       |
|  - Binary in UBI       - Switch to UBI       - Add health checks  |
|    image                 base images          - Externalize config |
|  - VM disk to          - Use ConfigMaps      - Use message queues |
|    container image       for config                                |
+-------------------------------------------------------------------+
```

**Lift-and-Shift (Rehost):** Take the application binary, wrap it in a container image with the same OS-level dependencies, and run it. Minimal code changes. Useful for quick wins but you inherit all the app's operational baggage (e.g., logs to local files, hardcoded ports, root-user expectations).

**Replatform (Repackage):** Adapt the application to take advantage of platform features without major architectural changes. For example, use S2I to build a Java WAR from source, switch to UBI base images, externalize configuration into ConfigMaps/Secrets, and add health check endpoints. This is the sweet spot for most legacy migrations.

**Refactor (Re-architect):** Break the monolith into microservices, adopt 12-factor principles, add event-driven communication. Highest effort but highest long-term benefit. Usually done incrementally using the Strangler Fig pattern.

### OpenShift S2I for Legacy Code

Source-to-Image (S2I) is OpenShift's built-in mechanism for converting application source code into a runnable container image -- without writing a Dockerfile. You learned the basics in L1-M3.1; now we apply it to legacy codebases.

S2I works particularly well for legacy migrations because:

1. **Builder images handle the complexity.** Red Hat provides certified builder images for Java (OpenJDK, JBoss EAP, JBoss Web Server), .NET, Python, Node.js, PHP, Ruby, and Go. These images know how to compile and package each language.
2. **No Dockerfile expertise required.** Legacy teams often lack container expertise. S2I abstracts the build process.
3. **Consistent, repeatable builds.** The same S2I builder produces identical image layouts, making operations predictable.
4. **Security by default.** S2I builder images run as non-root and are SCC-compatible.

For languages not covered by built-in builders (e.g., C/C++, Rust, COBOL), you can create custom S2I builder images or fall back to Dockerfile-based builds.

### Konveyor / Tackle for Application Assessment

Before migrating a portfolio of applications, you need to assess each one: What language and framework does it use? What external dependencies does it have? How complex is the migration? Which apps should go first?

[Konveyor](https://www.konveyor.io/) (formerly Tackle) is an open-source toolkit for application modernization, integrated into OpenShift via the Migration Toolkit for Applications (MTA). It provides:

- **Application Inventory:** Catalog all applications with metadata (language, framework, runtime, dependencies).
- **Assessment:** Questionnaire-based evaluation of migration difficulty, risk, and business priority.
- **Analysis:** Static code analysis to identify migration issues (e.g., hardcoded file paths, use of proprietary APIs, threading models incompatible with containers).
- **Migration Waves:** Group applications into waves based on dependency order, risk, and team capacity.

```
+---------------------------------------------------------------+
|           Konveyor / MTA Assessment Pipeline                   |
|                                                                |
|  +----------+    +-----------+    +----------+    +----------+ |
|  | Discover |    |  Assess   |    | Analyze  |    | Migrate  | |
|  |          |--->|           |--->|          |--->|          | |
|  | Inventory|    | Questio-  |    | Static   |    | Wave     | |
|  | apps &   |    | naire for |    | code     |    | planning | |
|  | deps     |    | readiness |    | scanning |    | & exec   | |
|  +----------+    +-----------+    +----------+    +----------+ |
|                                                                |
|  Outputs:        Outputs:         Outputs:        Outputs:     |
|  - App catalog   - Risk score     - Issue list    - Migration  |
|  - Dependency    - Effort est.    - Dependency    - waves      |
|    graph         - Confidence       analysis      - Timeline   |
+---------------------------------------------------------------+
```

### Architecture: End-to-End Legacy Migration Flow

```
+------------------------------------------------------------------+
|                                                                    |
|  ASSESSMENT PHASE                  MIGRATION PHASE                 |
|  (Konveyor/MTA)                    (OpenShift Build + Deploy)      |
|                                                                    |
|  +----------+                      +-------------------+           |
|  |  Legacy  |                      |  Source Code Repo  |          |
|  |  VM App  |--- assess -------->  |  (Git)             |          |
|  |  (JBoss, |                      +--------+----------+           |
|  |   .NET,  |                               |                     |
|  |   PHP)   |                               | S2I / Dockerfile    |
|  +----------+                               v                     |
|       |                            +-------------------+           |
|       | extract source             |  BuildConfig      |          |
|       | & config                   |  (OpenShift)      |          |
|       |                            +--------+----------+           |
|       v                                     |                     |
|  +----------+                               v                     |
|  | Analysis |                      +-------------------+           |
|  | Report   |                      |  ImageStream      |          |
|  | (issues, |                      |  (built image)    |          |
|  |  effort) |                      +--------+----------+           |
|  +----------+                               |                     |
|                                             v                     |
|                                    +-------------------+           |
|                                    |  Deployment       |          |
|                                    |  + Service        |          |
|                                    |  + Route          |          |
|                                    |  + ConfigMap      |          |
|                                    |  + PVC            |          |
|                                    +-------------------+           |
|                                                                    |
+------------------------------------------------------------------+
```

### Failure Modes in Legacy Migrations

Legacy app containerization is fraught with failure modes. Understanding them upfront saves significant debugging time:

| Failure Mode | Symptom | Root Cause | Recovery |
|---|---|---|---|
| SCC violation | `CrashLoopBackOff`, "Permission denied" in logs | App or base image expects to run as root | Use UBI base image, fix file permissions, or grant `anyuid` SCC (last resort) |
| Port binding failure | Container exits immediately | App tries to bind to port < 1024 | Reconfigure app to use port 8080+ or grant `NET_BIND_SERVICE` capability |
| Filesystem write failure | "Read-only file system" errors | App writes to paths owned by root | Use `emptyDir` volumes or fix ownership in build step |
| Missing OS packages | Runtime errors, missing shared libraries | Legacy app depends on packages not in UBI | Add packages in Dockerfile `RUN` step or use custom S2I builder |
| Hardcoded config paths | App fails to find configuration | Config at `/etc/myapp/` or `C:\config\` | Mount ConfigMap at expected path or refactor to use environment variables |
| Session affinity loss | Users lose session state | App stores sessions in memory or on local disk | Add session affinity to Route, or externalize sessions to Redis |
| Database connectivity | Connection refused, timeout | App uses `localhost` or VM hostname for DB | Update connection strings via environment variables or ConfigMap |
| Timezone mismatch | Incorrect timestamps, scheduler failures | Container uses UTC, app expects local timezone | Set `TZ` environment variable in Deployment |

## Step-by-Step

### Step 1: Set Up the Migration Project

Create a dedicated project for this migration exercise. We will migrate a simulated legacy Java application.

```bash
oc new-project legacy-migration \
  --display-name="Legacy App Migration" \
  --description="L3-M5.2: Migrating legacy applications to OpenShift"
```

### Step 2: Deploy a Lift-and-Shift Example (Binary Deployment)

The simplest migration: take a pre-built application binary and wrap it in a container. This example deploys a Java WAR file using the JBoss Web Server (Tomcat) builder image.

First, examine the BuildConfig for a binary build:

```yaml
# manifests/binary-build-config.yaml
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: legacy-java-app
  labels:
    app: legacy-java-app
    tutorial-level: "3"
    tutorial-module: "M5"
    migration-strategy: lift-and-shift
spec:
  source:
    type: Binary
  strategy:
    type: Source
    sourceStrategy:
      from:
        kind: ImageStreamTag
        namespace: openshift
        name: jboss-webserver56-openjdk11-tomcat9-openshift-ubi8:latest
  output:
    to:
      kind: ImageStreamTag
      name: legacy-java-app:latest
```

Apply the ImageStream and BuildConfig:

```bash
oc apply -f manifests/imagestream-legacy-java.yaml
oc apply -f manifests/binary-build-config.yaml
```

For a real migration, you would trigger a binary build by uploading a WAR file:

```bash
# Example: upload a WAR file from your local machine
# oc start-build legacy-java-app --from-file=target/myapp.war --follow

# For this tutorial, we use a Git-based S2I build instead (Step 3)
```

Binary builds are useful when:
- You have compiled artifacts but not source code (vendor-provided software)
- The build system is complex and cannot easily run inside a container
- You want a quick lift-and-shift with minimal changes

### Step 3: Deploy a Replatform Example (S2I from Source)

The replatform strategy uses S2I to build directly from source code. This is the recommended approach for most legacy Java, .NET, Python, and PHP applications.

Apply the S2I BuildConfig that builds from a Git repository:

```bash
oc apply -f manifests/s2i-build-config.yaml
oc apply -f manifests/imagestream-s2i-app.yaml
```

Start the S2I build:

```bash
oc start-build s2i-legacy-app --follow
```

Watch the build process. S2I will:
1. Clone the source repository
2. Detect the language and framework (via builder image)
3. Run the build (e.g., `mvn package` for Java)
4. Assemble the output into a runnable image
5. Push the image to the internal registry as an ImageStream tag

### Step 4: Deploy the Application with Production Configuration

Once the image is built, deploy it with production-quality configuration including health checks, resource limits, externalized configuration, and persistent storage.

Apply the ConfigMap for externalized configuration:

```bash
oc apply -f manifests/legacy-app-config.yaml
```

Apply the Deployment, Service, and Route:

```bash
oc apply -f manifests/deployment.yaml
oc apply -f manifests/service.yaml
oc apply -f manifests/route.yaml
```

If the application needs persistent storage (e.g., for file uploads or logs that must survive restarts):

```bash
oc apply -f manifests/pvc.yaml
```

### Step 5: Handle Common Legacy App Issues

Legacy applications often hit SCC restrictions. Here is a systematic approach to diagnosing and resolving them.

**Check if pods are failing:**

```bash
oc get pods -l app=legacy-app
oc describe pod -l app=legacy-app | grep -A 5 "State\|Error\|Warning"
```

**Diagnose SCC issues:**

```bash
# Check which SCC the pod is using
oc get pod -l app=legacy-app -o jsonpath='{.items[0].metadata.annotations.openshift\.io/scc}'

# Test if the image can run under the restricted SCC
oc debug deployment/legacy-app --as-root=false
```

**If the app requires root (common with legacy apps), evaluate options:**

1. **Best:** Fix the image to run as non-root (update file permissions in the Dockerfile)
2. **Acceptable:** Create a dedicated ServiceAccount with `anyuid` SCC
3. **Last resort:** Run the app in OpenShift Virtualization as a VM (L3-M4.1)

```bash
# Option 2: Grant anyuid SCC to a dedicated ServiceAccount (if truly needed)
oc create serviceaccount legacy-app-sa -n legacy-migration
oc adm policy add-scc-to-user anyuid -z legacy-app-sa -n legacy-migration

# Then update the Deployment to use this ServiceAccount:
# spec.template.spec.serviceAccountName: legacy-app-sa
```

### Step 6: Externalize Configuration

Legacy apps commonly hardcode configuration in files baked into the deployment. Containerized apps should externalize this using ConfigMaps and Secrets.

The ConfigMap mounts configuration at the path the legacy app expects:

```bash
# View the ConfigMap
oc get configmap legacy-app-config -o yaml

# Verify the mount inside the running pod
oc rsh deployment/legacy-app ls -la /opt/app-root/config/
```

For sensitive configuration (database passwords, API keys), use Secrets:

```bash
oc create secret generic legacy-app-secrets \
  --from-literal=db-password='changeme123' \
  --from-literal=api-key='my-legacy-api-key'

# Reference in the Deployment via envFrom or volumeMount
```

### Step 7: Set Up Migration Assessment with Konveyor/MTA

For portfolio-level migration planning, install the Migration Toolkit for Applications (MTA) operator.

**Install MTA from OperatorHub:**

```bash
# Log in as cluster admin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Apply the MTA operator subscription
oc apply -f manifests/mta-operator-subscription.yaml
```

Wait for the operator to install, then create a Tackle instance:

```bash
# Wait for the operator to be ready
oc wait --for=condition=Available deployment/mta-operator \
  -n openshift-mta --timeout=300s

# Create the Tackle CR to deploy the MTA application
oc apply -f manifests/mta-tackle-cr.yaml
```

**Access the MTA Web Console:**

```bash
# Get the MTA route
oc get route -n openshift-mta
```

In the MTA web console, you can:

1. **Create an Application Inventory** -- register each legacy app with metadata
2. **Run Assessments** -- answer questionnaires about each app's cloud readiness
3. **Run Analysis** -- point MTA at source code or binaries to detect migration issues
4. **Plan Migration Waves** -- group apps by dependency, risk, and team capacity

### Step 8: Plan Migration Waves

Migration waves prioritize applications for containerization in a logical order. Apply the wave planning script:

```bash
bash scripts/migration-wave-plan.sh
```

The output illustrates a migration wave plan. In a real scenario, Konveyor/MTA generates this based on assessment data. The key principles are:

1. **Wave 1 (Quick wins):** Stateless apps, already 12-factor compliant, low risk
2. **Wave 2 (Standard migrations):** Apps needing minor changes (config externalization, port changes)
3. **Wave 3 (Complex migrations):** Stateful apps, apps needing SCC changes, database-dependent
4. **Wave 4 (Refactor candidates):** Monoliths that should be broken into services, apps needing architecture changes

```
+----------------------------------------------------------+
|                Migration Wave Timeline                     |
|                                                            |
|  Wave 1       Wave 2        Wave 3         Wave 4          |
|  (Weeks 1-2)  (Weeks 3-6)   (Weeks 7-12)  (Weeks 13+)    |
|                                                            |
|  [Stateless]  [Config      [Stateful     [Monolith        |
|  [12-factor ]  external.]   apps with     decomposition]  |
|  [REST APIs]  [Port fixes]  databases]   [Re-architecture]|
|  [Web UIs  ]  [UBI rebase] [SCC needs]   [Event-driven]  |
|                                                            |
|  Risk: Low    Risk: Medium  Risk: High    Risk: Very High  |
|  Effort: Low  Effort: Med   Effort: High  Effort: V.High  |
+----------------------------------------------------------+
```

### Step 9: Monitor the Migrated Application

Verify the migrated application is running correctly with production-grade monitoring:

```bash
# Check pod status and resource consumption
oc get pods -l app=legacy-app -o wide
oc adm top pods -l app=legacy-app

# Check events for any warnings
oc get events --sort-by=.metadata.creationTimestamp | tail -20

# View application logs
oc logs deployment/legacy-app --tail=50

# Check the route is accessible
ROUTE_URL=$(oc get route legacy-app -o jsonpath='{.spec.host}')
curl -sk "https://${ROUTE_URL}" | head -20
```

## Verification

Run the following commands to verify the lesson resources are deployed correctly:

```bash
# 1. Verify the project exists
oc project legacy-migration

# 2. Check that the BuildConfig exists
oc get buildconfig -l tutorial-module=M5
# Expected: s2i-legacy-app and/or legacy-java-app BuildConfigs listed

# 3. Check the ImageStream
oc get imagestream -l tutorial-module=M5
# Expected: ImageStreams with tags populated after successful builds

# 4. Verify the Deployment is running
oc get deployment legacy-app -o wide
# Expected: READY shows desired replica count (e.g., 2/2)

# 5. Check the pods are healthy
oc get pods -l app=legacy-app
# Expected: All pods in Running state, no restarts

# 6. Verify the Route is accessible
oc get route legacy-app
# Expected: Route with a host/port URL
curl -sk "https://$(oc get route legacy-app -o jsonpath='{.spec.host}')" -o /dev/null -w "%{http_code}"
# Expected: 200

# 7. Verify ConfigMap is mounted
oc rsh deployment/legacy-app cat /opt/app-root/config/application.properties
# Expected: Configuration file contents displayed

# 8. Check resource limits are applied
oc get deployment legacy-app -o jsonpath='{.spec.template.spec.containers[0].resources}'
# Expected: JSON showing requests and limits for cpu and memory
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Containerizing legacy apps | Write Dockerfiles manually; no built-in tooling | S2I builds from source without Dockerfiles; certified builder images for Java, .NET, Python, PHP |
| Build system | External (Docker, Kaniko, CI pipeline) | Built-in BuildConfigs with Source, Docker, Binary, and Pipeline strategies |
| Image management | Push to external registry; reference by digest or tag | ImageStreams abstract image references; automatic triggers on new images |
| Binary deployments | No built-in support; write Dockerfile with `COPY` | `oc start-build --from-file` uploads artifacts directly into S2I builder |
| Migration assessment | No built-in tooling; use third-party tools | Konveyor/MTA operator for portfolio assessment, code analysis, wave planning |
| Security during migration | Pods run as root by default; PSA is opt-in | Restricted SCC enforced by default; forces security-first containerization |
| Legacy VM workloads | Not supported natively | OpenShift Virtualization (KubeVirt) runs VMs alongside containers |
| Configuration management | ConfigMaps/Secrets (manual setup) | Same, plus `oc set env`, `oc set volume` shortcuts for quick migration |
| Base images | Any Docker Hub image | Red Hat UBI (Universal Base Image) -- free, supported, SCC-compatible |
| Runtime support | Install your own language runtimes | Pre-configured builder images in the `openshift` namespace |

## Key Takeaways

- **Choose the right migration strategy** for each application: lift-and-shift for quick wins with minimal changes, replatform (with S2I) for the best balance of effort and benefit, and refactor only when the application truly needs architectural change.
- **S2I eliminates Dockerfile complexity** for legacy codebases. Red Hat provides certified builder images for Java, .NET, Python, PHP, Ruby, Node.js, and Go that handle compilation, packaging, and security automatically.
- **Konveyor/MTA provides portfolio-level visibility** for large-scale migrations. Its assessment questionnaires, static code analysis, and wave planning tools turn a chaotic migration into a structured, prioritized program.
- **Security is the number one migration blocker.** Most legacy apps expect root privileges, bind to privileged ports, or write to root-owned paths. Address SCC issues early -- preferring image fixes over SCC grants.
- **Migration waves prevent organizational chaos.** Migrating everything at once is a recipe for failure. Prioritize by risk, effort, and business value, and tackle stateless quick wins first to build confidence.

## Cleanup

```bash
# Delete all resources created in this lesson
oc delete project legacy-migration

# If you installed the MTA operator (Step 7), remove it:
# oc delete subscription mta-operator -n openshift-mta
# oc delete csv -n openshift-mta -l operators.coreos.com/mta-operator.openshift-mta
# oc delete namespace openshift-mta

# Verify cleanup
oc get project legacy-migration
# Expected: "not found" error confirms deletion
```

## Next Steps

In **L3-M5.3 -- Capstone: Production-Ready Microservices**, you will bring together everything from all three levels to deploy a complete multi-service application with CI/CD pipelines, GitOps, service mesh, monitoring, autoscaling, network policies, and proper RBAC. That capstone will use migration techniques from this lesson as part of its architecture.
