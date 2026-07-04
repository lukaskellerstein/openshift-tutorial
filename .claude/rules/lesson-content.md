# Lesson Content — README.md Format

Every lesson's README.md follows this structure. The title format differs by track:

- **Platform track:** `# L<NN> — <Lesson Title>` (e.g., `# L01 — Projects`)
- **AI tracks:** `# L<level>-M<module>.<lesson> — <Lesson Title>` (e.g., `# L1-2.2 — Model Serving with KServe`)

## Template

```markdown
# <Title per track convention above>

**Level:** <Foundations | Practitioner | Expert>
**Duration:** <estimated time>

## Overview
<2-3 sentences: what the user will learn and why it matters.
Always anchor to the Kubernetes concept they already know.>

## Prerequisites
- Completed: <list prior lessons>
- OpenShift cluster running (CRC or Developer Sandbox)
- <any additional requirements (operators installed, etc.)>

## K8s Context
<Brief reminder of how this works in vanilla Kubernetes.
This is the bridge — the reader should think "ah yes, I know that,
now show me how OpenShift does it differently.">

## Concepts
<Explain the OpenShift-specific concepts. What does OpenShift add or change?
Why does it do it this way? What problem does it solve?>

## Step-by-Step

### Step 1: <Action>
<Explain what we're doing and why>

```bash
# Commands to run
oc ...
```

```yaml
# Manifest snippet (from manifests/ directory)
```

### Step 2: <Action>
...

## Verification
<How to verify the lesson worked — commands to run, URLs to check,
expected output in the terminal or Web Console.>

## K8s vs OpenShift Comparison
<Side-by-side table or bullet list showing the key differences
demonstrated in this lesson.>

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| ... | ... | ... |

## Key Takeaways
- <3-5 bullet points summarizing what was learned>

## Cleanup
```bash
# Commands to tear down resources created in this lesson
oc delete ...
```

## Next Steps
<Point to the next lesson and preview what it covers.>
```

## Writing Guidelines by Level

### Level 1 — Foundations
- Always start from the K8s concept: "In Kubernetes, you do X. In OpenShift, you do Y instead."
- Show the simplest working example — one manifest, one command.
- Include a K8s vs OpenShift comparison table in every lesson.
- Keep it under 30 minutes of hands-on time.

### Level 2 — Practitioner
- Build realistic scenarios (deploy a multi-tier app, set up a CI/CD pipeline).
- Explain tradeoffs: when to use Route vs Ingress, when to use DeploymentConfig vs Deployment.
- Cross-reference Level 1 concepts: "In L1-M4.2 you learned about Routes. Now we'll use them in a CI/CD pipeline."
- Include troubleshooting tips for common mistakes.

### Level 3 — Expert
- Production-quality configurations with proper resource limits, RBAC, network policies.
- Include architecture diagrams where appropriate.
- Discuss failure modes: what happens when this breaks? How do you recover?
- Capstone READMEs should include a full architecture overview.

## General Guidelines

- **Platform track:** Write for someone who knows Kubernetes well but is new to OpenShift. Always explain WHY OpenShift does something differently. Include a K8s vs OpenShift comparison table in every lesson.
- **AI tracks:** Write for someone who knows OpenShift (from the Platform track) and is learning OpenShift AI. The "K8s Context" section can be replaced with an "OpenShift Context" or "Prerequisites" section as appropriate. Comparison tables can contrast vanilla ML tooling with OpenShift AI equivalents.
- Show full `oc` commands — don't assume the reader knows OpenShift CLI flags.
- Include both CLI and Web Console instructions when relevant.
- Always include a Cleanup section — CRC and Demo Platform have limited resources.
- Every lesson should have a Verification section so users know they succeeded.
