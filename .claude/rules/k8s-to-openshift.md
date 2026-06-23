# Kubernetes → OpenShift Framing

## Core Principle

The reader knows Kubernetes. Every explanation should start from that foundation:
1. What they already know (the K8s way)
2. What OpenShift adds, changes, or restricts
3. Why — the design rationale

Never explain basic K8s concepts in detail. A sentence like "You already know Deployments manage ReplicaSets which manage Pods" is enough context.

## Key Differences to Emphasize

### Security Model (the #1 surprise for K8s users)
- Pods cannot run as root by default (SCC `restricted` is enforced).
- Many Docker Hub images fail on OpenShift because they expect root.
- This is intentional and a security feature, not a bug.
- Always explain how to handle this: fix the image, or grant `anyuid` SCC (and explain the tradeoff).

### Routes vs Ingress
- OpenShift had Routes before Kubernetes had Ingress.
- Routes offer built-in TLS termination modes (edge, passthrough, re-encrypt).
- Ingress is also supported on OpenShift — Routes are the native, more feature-rich option.
- The HAProxy-based router is pre-installed — no need to install an ingress controller.

### Projects vs Namespaces
- Projects are namespaces with extra metadata and default RBAC.
- Users can self-provision projects (configurable).
- `oc new-project` adds display name, description, and default role bindings.

### Builds and Images
- OpenShift has a built-in container build system — no external CI needed for basic builds.
- S2I (Source-to-Image) builds apps from source code without a Dockerfile.
- ImageStreams abstract image references and enable triggers.
- This is the biggest conceptual leap from K8s — dedicate extra explanation here.

### Operators as First-Class Citizens
- OLM (Operator Lifecycle Manager) is pre-installed.
- OperatorHub is integrated into the Web Console.
- In K8s you install operators manually; in OpenShift it's a catalog experience.

### Web Console
- Far more capable than K8s Dashboard.
- Two perspectives: Administrator (cluster ops) and Developer (app deployment).
- Topology view, built-in terminal, log viewer, metrics.

## Writing Pattern

For every OpenShift-specific concept, follow this structure:

```markdown
### In Kubernetes
<1-2 sentences: how it works in K8s>

### In OpenShift
<What's different and what's added>

### Why?
<The design rationale — security, developer experience, enterprise requirements>
```

## Common Gotchas to Call Out

These trip up every K8s user migrating to OpenShift. Flag them prominently:

1. **"My pod won't start"** → Probably an SCC issue. Image tries to run as root.
2. **"I can't pull from Docker Hub"** → Image may need `anyuid` SCC, or use Red Hat's UBI images.
3. **"Where's my Ingress controller?"** → Use Routes instead (or configure Ingress — both work).
4. **"DeploymentConfig vs Deployment?"** → Use Deployment. DC is legacy.
5. **"Why does `oc new-app` create so many resources?"** → It auto-creates Service, DeploymentConfig/Deployment, ImageStream, BuildConfig. Explain what each is.
6. **"How do I get cluster-admin?"** → `oc login` as `kubeadmin` in CRC. In production, use proper RBAC.
7. **"My Helm chart doesn't work"** → Likely SCC/root issues. Check the chart's `securityContext`.

## Tone

- Respectful of the reader's existing knowledge — never condescending about K8s.
- Honest about OpenShift's opinions: "OpenShift is opinionated about security — here's why."
- Practical: "Here's the K8s way, here's the OpenShift way, here's which to use when."
- Acknowledge when K8s and OpenShift converge: "Deployments work identically on both."
