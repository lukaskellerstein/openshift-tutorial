# Tutorial Structure Rules

## Three-Level Architecture

- **`tutorial/level_1/`** — Foundations: every major K8s→OpenShift difference, short lessons (~20-30 min)
- **`tutorial/level_2/`** — Practitioner: real-world workflows, longer lessons (~45-90 min)
- **`tutorial/level_3/`** — Expert: production operations, multi-cluster, capstones

Always consult `tutorial_syllabus.md` for the full module/lesson breakdown.

## Lesson Directory Convention

Every lesson lives in `tutorial/<level>/<module>/<lesson>/` and contains:

1. **`README.md`** — lesson guide (see `lesson-content.md` rule for format). This is the primary deliverable.
2. **`manifests/`** — YAML files for all OpenShift/K8s resources used in the lesson.
3. **`scripts/`** — shell scripts for setup, teardown, and demo steps (optional, use when commands are complex or multi-step).
4. **`app/`** — application source code if the lesson deploys a custom app (optional).
5. **`.gitignore`** — ignore temp files and credentials.

Not every lesson needs all directories — only create what the lesson requires.

## Directory Naming

```
tutorial/
  level_1/
    M1_platform_setup/
      1_architecture_overview/
      2_installing_crc/
      3_oc_vs_kubectl/
      4_web_console_tour/
    M2_projects_users_rbac/
      ...
```

Module directories use `M<N>_snake_case_name/`. Lesson directories use `<N>_snake_case_name/`.

## Manifest Organization

Within a lesson's `manifests/` directory, name files descriptively:

```
manifests/
  deployment.yaml
  service.yaml
  route.yaml
  buildconfig.yaml
  imagestream.yaml
```

For lessons with multiple variants or comparisons:
```
manifests/
  k8s-ingress.yaml          # Kubernetes way (for comparison)
  openshift-route.yaml       # OpenShift way
  route-edge-tls.yaml
  route-passthrough-tls.yaml
```

## .gitignore Template

```
*.tmp
*.bak
kubeconfig
.kube/
```

## Principles

- Each lesson must be self-contained — a user should be able to follow the README, apply the manifests, and see results.
- All lessons assume CRC is running or a Developer Sandbox is available.
- Always show the K8s equivalent first, then the OpenShift way — the reader knows K8s.
- Keep manifests minimal and focused — don't add fields that aren't relevant to the lesson.
- Level 1 lessons should cover one concept in ~20-30 minutes.
- Level 2 lessons can build multi-step workflows over ~45-90 minutes.
- Level 3 lessons should address production concerns and integrate multiple concepts.
- Use `oc` for OpenShift-specific operations, `kubectl` when demonstrating K8s compatibility.
