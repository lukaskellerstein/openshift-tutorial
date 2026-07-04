# Tutorial Structure Rules

This repo has two layout conventions: one for the Platform track and one for the AI tracks.

## Platform Track (`tutorial/`)

Uses a flat numbering scheme — 10 self-contained lessons:

```
tutorial/
  shared_app/                      # ShopInsights application source
  L01_projects/
  L02_builds_and_images/
  ...
  L10_serverless/
```

Lesson directories use `L<NN>_snake_case_name/`.

## AI Tracks (`tutorial_ai/openshift_ai/` and `tutorial_ai/redhat_ai/`)

Use a three-level architecture with modules:

- **`level_1/`** — Foundations: short lessons (~20-30 min)
- **`level_2/`** — Practitioner: real-world workflows, longer lessons (~45-90 min)
- **`level_3/`** — Expert: production operations, advanced topics

```
tutorial_ai/openshift_ai/
  syllabus.md
  manifests/
  level_1/
    M1_platform_setup/
      1_architecture_overview/
      2_installing_operators/
    M2_model_serving/
      ...
  level_2/
    ...
  level_3/
    ...
```

Module directories use `M<N>_snake_case_name/`. Lesson directories use `<N>_snake_case_name/`.

Consult each track's `syllabus.md` for the full module/lesson breakdown.

## Lesson Directory Convention

Every lesson (in either track) lives in its own directory and contains:

1. **`README.md`** — lesson guide (see `lesson-content.md` rule for format). This is the primary deliverable.
2. **`manifests/`** — YAML files for all OpenShift/K8s resources used in the lesson.
3. **`scripts/`** — shell scripts for setup, teardown, and demo steps (optional, use when commands are complex or multi-step).
4. **`app/`** — application source code if the lesson deploys a custom app (optional).
5. **`.gitignore`** — ignore temp files and credentials.

Not every lesson needs all directories — only create what the lesson requires.

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
- **Platform track:** assumes CRC or Developer Sandbox. Always show the K8s equivalent first, then the OpenShift way — the reader knows K8s.
- **AI tracks:** assume the Red Hat Demo Platform (GPU cluster with admin access). The reader knows OpenShift from the Platform track.
- Keep manifests minimal and focused — don't add fields that aren't relevant to the lesson.
- Level 1 lessons should cover one concept in ~20-30 minutes.
- Level 2 lessons can build multi-step workflows over ~45-90 minutes.
- Level 3 lessons should address production concerns and integrate multiple concepts.
- Use `oc` for OpenShift-specific operations, `kubectl` when demonstrating K8s compatibility.
