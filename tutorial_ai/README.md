# OpenShift AI Tutorial

A project-based OpenShift AI tutorial for developers who already know Kubernetes and OpenShift. Covers both **OpenShift AI** (the platform) and the broader **Red Hat AI** ecosystem.

## Environment

The ideal environment for this tutorial is the **Red Hat Demo Platform** — a pre-configured OpenShift cluster with GPUs and full admin access:

**[OpenShift AI v3 Demo Environment](https://catalog.demo.redhat.com/catalog/babylon-catalog-prod?item=babylon-catalog-prod/published.openshift-ai-v3.prod&utm_source=webapp&utm_medium=share-link)**

Why not the alternatives?

| Environment | Problem |
|-------------|---------|
| [Developer Sandbox](https://sandbox.redhat.com/) | No cluster-admin access — you cannot install operators, enable/disable DataScienceCluster components, or configure the platform. Only useful for exploring the dashboard. |
| [OpenShift Local (CRC)](https://console.redhat.com/openshift/create/local) | No GPU, limited resources (~9 GB RAM default). You can install the OpenShift AI operator and explore the DataScienceCluster CR, but model serving, fine-tuning, and evaluation workloads will fail. |

## Structure

```
tutorial_ai/
├── openshift_ai/                        # OpenShift AI tutorial (3 levels, 66 lessons, ~56-67h)
│   ├── syllabus.md
│   └── manifests/                       # Working manifests (used in lessons)
│       ├── gemma4-e4b-servingruntime.yaml    # → L1-2.2
│       └── gemma4-e4b-inferenceservice.yaml  # → L1-2.2
├── redhat_ai/                           # Red Hat AI Ecosystem tutorial (2 levels, 15 lessons, ~11-15h)
│   └── syllabus.md
├── openshift_ai_docs.md                 # Reference links to official 3.5 docs
├── other_docs.md                        # Paths to sub-tutorial repos and source code
└── README.md                            # This file
```

### Sub-Tutorials (separate repos)

Each OpenShift AI sub-component has its own tutorial with dedicated syllabus:

| Sub-Tutorial | Repo | Lessons | Focus |
|-------------|------|---------|-------|
| [MLflow](https://github.com/lukaskellerstein/mlflow-tutorial) | `mlflow-tutorial` | 21 | Experiment tracking, model registry, tracing |
| [OGX](https://github.com/lukaskellerstein/ogx-tutorial) | `ogx-tutorial` | 21 | OpenAI-compatible APIs, Responses API, RAG |
| [AutoRAG](https://github.com/lukaskellerstein/autorag-tutorial) | `autorag-tutorial` | 13 | RAG pipeline optimization (AutoML for RAG) |
| [EvalHub](https://github.com/lukaskellerstein/evalhub-tutorial) | `evalhub-tutorial` | 14 | Evaluation orchestration, CI/CD quality gates |
| [NeMo Guardrails](https://github.com/lukaskellerstein/nemo-guardrails-tutorial) | `nemo-guardrails-tutorial` | 17 | Safety rails with Colang 2.0, guardrails orchestrator |

## Prerequisites

- Completed the [main OpenShift tutorial](../tutorial/) or equivalent
- Familiar with Python, LLMs, and basic ML concepts
- Existing experience with [MLflow](https://github.com/lukaskellerstein/mlflow-tutorial), [LangChain/LangGraph](https://github.com/lukaskellerstein/ai-agents-course), and [MCP](https://github.com/lukaskellerstein/ai-agents-course)

## Architecture Overview

```mermaid
block-beta
  columns 1

  block:openshift["OpenShift Container Platform\n(Kubernetes + RBAC + Routes + SCCs + OLM + Web Console)"]
    columns 1

    block:rhoai_operator["Red Hat OpenShift AI Operator (meta-operator)\nInstalled from OperatorHub"]
      columns 2
      dsci["DSCInitialization CR\n(cluster-wide config:\nnamespace, mesh, certs)"]
      dsc["DataScienceCluster CR\n(toggles components:\nManaged / Removed)"]
    end

    block:dsc_components["DataScienceCluster Components (each can be Managed or Removed)"]
      columns 4
      dashboard["dashboard\n(Web UI)"]
      workbenches["workbenches\n(Jupyter)"]
      pipelines["datasciencepipelines\n(Kubeflow Pipelines)"]
      kserve["kserve\n(single-model serving)"]
      modelmesh["modelmeshserving\n(multi-model serving)"]
      registry["modelregistry\n(governance)"]
      codeflare["codeflare\n(distributed compute)"]
      ray["ray\n(distributed compute)"]
      kueue["kueue\n(job queueing)"]
      training["trainingoperator\n(model training)"]
      feast["feastoperator\n(feature store)"]
      llamastack["llamastackoperator\n(Llama Stack / OGX)"]
    end

    block:trustyai_block["trustyai — TrustyAI Service Operator"]
      columns 3
      trustyai_svc["TrustyAI Service\n(explainability,\nfairness, drift)"]
      guardrails["FMS-Guardrails\n(LLM guardrails)"]

      block:evalhub_block["EvalHub — eval-hub.github.io/home\nSeparate repo: github.com/eval-hub/eval-hub (Go, Apache 2.0)\nDeployed by TrustyAI Operator via EvalHub CR"]
        columns 5
        lmeval["lm-eval-harness\n(167 benchmarks)"]
        garak["Garak\n(red-teaming)"]
        guidellm["GuideLLM\n(throughput)"]
        lighteval["LightEval\n(lightweight)"]
        contrib["Contrib adapters\n(RAGAS, MTEB,\nIBM CLEAR)"]
      end
    end

    block:prereqs["Prerequisite Operators (installed separately from OperatorHub)"]
      columns 5
      serverless["OpenShift\nServerless\n(Knative)"]
      mesh["OpenShift\nService Mesh\n(Istio)"]
      authorino["Authorino\nOperator\n(auth)"]
      gpu["NVIDIA GPU\nOperator"]
      nfd["Node Feature\nDiscovery\nOperator"]
    end

    block:namespaces["Namespaces created by the operator"]
      columns 4
      ns1["redhat-ods-operator"]
      ns2["redhat-ods-applications"]
      ns3["redhat-ods-monitoring"]
      ns4["rhods-notebooks"]
    end

  end

  rhoai_operator --> dsc_components
  dsc_components --> trustyai_block
  kserve --> serverless
  kserve --> mesh
  kserve --> authorino
  evalhub_block -- "results tracked in" --> mlflow["MLflow"]

  style openshift fill:#1a1a2e,color:#fff
  style rhoai_operator fill:#16213e,color:#fff
  style dsc_components fill:#0f3460,color:#fff
  style trustyai_block fill:#533483,color:#fff
  style evalhub_block fill:#e94560,color:#fff
  style prereqs fill:#1a1a2e,color:#fff,stroke:#555
  style namespaces fill:#1a1a2e,color:#fff,stroke:#555
  style mlflow fill:#0d7377,color:#fff
```

**Key takeaway:** OpenShift AI is an operator installed on OpenShift. That operator manages a `DataScienceCluster` CR whose `spec.components` section toggles ~13 sub-components on/off. One of those components is `trustyai`, which is itself an operator (TrustyAI Service Operator) that manages the TrustyAI Service, FMS-Guardrails, and **EvalHub** — a separate Go project with its own repo that the TrustyAI Operator deploys via an EvalHub custom resource.

## Working Manifests

The `openshift_ai/manifests/` directory contains tested, working manifests deployed on a real OpenShift AI cluster. These are referenced directly from lesson steps:

| Manifest | Used In | What It Does |
|----------|---------|-------------|
| `gemma4-e4b-servingruntime.yaml` | L1-2.2 | vLLM ServingRuntime for Gemma 4 E4B (NVIDIA GPU, `dtype=half`, `max-model-len=8192`) |
| `gemma4-e4b-inferenceservice.yaml` | L1-2.2 | InferenceService deploying Gemma 4 E4B (RawDeployment mode, 1x GPU, 24Gi memory) |

## Getting Started

1. Start with the [OpenShift AI syllabus](openshift_ai/syllabus.md) — it references sub-tutorials when you need them.
2. Optionally explore the [Red Hat AI Ecosystem syllabus](redhat_ai/syllabus.md) for Podman AI Lab, RHEL AI, and Granite models.
