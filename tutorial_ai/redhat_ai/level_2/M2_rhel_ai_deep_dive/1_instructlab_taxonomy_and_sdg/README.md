# L2-M2.1 — InstructLab Taxonomy and SDG

**Level:** Practitioner
**Duration:** 1 hour

## Overview

This lesson takes you deep into InstructLab's two most powerful mechanisms: the taxonomy system for encoding human knowledge and skills, and Synthetic Data Generation (SDG) for turning that taxonomy into high-quality training data. You will create both a knowledge and a skill contribution, generate synthetic training data, fine-tune a model, and evaluate the results.

## Prerequisites

- Completed Level 1 (L1-M1 through L1-M3) — you understand the Red Hat AI ecosystem, the Granite model family, and the InstructLab workflow at a high level
- RHEL AI instance with GPU access (or a machine with InstructLab installed and a compatible GPU)
- InstructLab CLI (`ilab`) installed and initialized (`ilab config init` completed)
- A base Granite model downloaded (`ilab model download`)
- Familiarity with YAML syntax

## Concepts

### Taxonomy Deep Dive

InstructLab's taxonomy is a hierarchical directory structure that encodes what you want a model to learn. Every contribution falls into one of two categories: **knowledge** or **skills**. Understanding the difference is critical for effective fine-tuning.

#### Knowledge Contributions

Knowledge contributions teach the model new facts — information it did not have in its base training data. This includes:

- **Domain documentation** — product manuals, internal wikis, API references
- **FAQs** — question-and-answer pairs about your organization or domain
- **Factual content** — dates, names, specifications, processes, policies

Knowledge contributions require a **document source**. You cannot teach the model facts from thin air — you must provide a reference document that contains the information. InstructLab uses this document as ground truth when generating synthetic training data.

A knowledge `qna.yaml` file contains:

- `created_by` — your identifier
- `domain` — the subject area
- `document_outline` — a summary of the source document
- `seed_examples` — 5+ question-and-answer pairs grounded in the document
- `document` — a reference to the source document (in the `knowledge` directory or a repo)

#### Skill Contributions

Skill contributions teach the model new capabilities — how to reason, format, analyze, or transform information. Unlike knowledge, skills do not require a source document because they teach behavior patterns, not facts.

Examples of skills:

- **Reasoning** — solving math problems, logical deduction, multi-step analysis
- **Formatting** — converting data between formats (JSON to YAML, CSV to Markdown tables)
- **Coding** — writing code in a specific style or framework
- **Analysis** — summarizing, comparing, extracting patterns from text

A skill `qna.yaml` file contains:

- `created_by` — your identifier
- `task_description` — what the skill does
- `seed_examples` — 5+ input-output pairs demonstrating the skill

Skills do not have a `document` field. The model learns the pattern from the examples alone.

#### Taxonomy File Format

Both knowledge and skill contributions use YAML files named `qna.yaml`. The taxonomy directory structure determines where the contribution sits in the model's knowledge hierarchy:

```
taxonomy/
  knowledge/
    technology/
      cloud/
        openshift/
          qna.yaml          # Knowledge about OpenShift
    company/
      acme_corp/
        policies/
          qna.yaml          # Knowledge about company policies
  skills/
    extraction/
      json_to_yaml/
        qna.yaml            # Skill: converting JSON to YAML
    analysis/
      sentiment/
        qna.yaml            # Skill: sentiment analysis
```

The directory path acts as a category tree. Place your contribution in the most specific category that makes sense.

#### Taxonomy Validation

Before generating data, you must validate your taxonomy. The `ilab taxonomy diff` command checks:

- YAML syntax correctness
- Required fields are present
- Minimum number of seed examples (5 for knowledge, 5 for skills)
- Document references resolve correctly (for knowledge)
- No duplicate entries

---

### Synthetic Data Generation (SDG)

SDG is the process that transforms your small set of seed examples (5+) into a large, diverse training dataset (hundreds or thousands of examples). This is the core innovation of the LAB (Large-scale Alignment for chatBots) methodology.

#### How SDG Works

1. **Input** — Your `qna.yaml` file with seed examples, plus the source document (for knowledge).
2. **Teacher model** — A larger model (the "teacher") reads your examples and generates new, diverse variations. The teacher rephrases questions, creates different angles on the same topic, and generates challenging edge cases.
3. **Output** — A synthetic dataset with many more examples than you provided, all grounded in your original seed data and source document.

The teacher model is critical. A better teacher produces higher-quality synthetic data, which produces a better fine-tuned model. InstructLab uses a pipeline of generation and filtering to ensure quality.

#### SDG Configuration

Key SDG parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--num-instructions` | 100 | Number of synthetic examples to generate |
| `--pipeline` | `simple` | SDG pipeline (`simple` for CPU/small GPU, `full` for large GPU) |
| `--batch-size` | Varies | Batch size for generation (affects speed and memory) |

The `simple` pipeline uses the student model itself as a teacher (lower quality but runs on modest hardware). The `full` pipeline uses a separate, larger teacher model for higher-quality data generation.

#### Reviewing Generated Data

SDG output is saved as JSON files. Always review a sample before training:

- Are the generated questions relevant and diverse?
- Are the answers factually correct (for knowledge)?
- Do the generated examples match the intended skill pattern?
- Are there any hallucinations or contradictions?

Poor seed examples produce poor synthetic data. If the generated data looks wrong, improve your seed examples and regenerate.

---

### Multi-Phase Training

InstructLab training proceeds in phases, each optimizing for a different objective:

#### Phase 1: Knowledge Tuning

Injects new factual information into the model. The model learns to answer questions about topics it was not originally trained on. This phase uses the synthetic data generated from your knowledge contributions.

#### Phase 2: Skills Tuning

Teaches the model new behavioral capabilities. The model learns to perform tasks (formatting, analysis, reasoning) demonstrated in your skill contributions. This phase uses the synthetic data generated from your skill contributions.

#### Phase 3: Alignment

Maintains the model's helpfulness, harmlessness, and honesty after the knowledge and skills phases. Without alignment, fine-tuned models can become less conversational or produce unsafe outputs. This phase ensures the new capabilities do not degrade the model's general quality.

All three phases run automatically during `ilab model train`. You do not need to manage them individually unless you are customizing the training pipeline.

---

### LAB-Tuning vs LoRA/QLoRA

If you have experience with LoRA (Low-Rank Adaptation) or QLoRA, you may wonder how InstructLab's approach differs.

| Aspect | InstructLab (LAB) | LoRA / QLoRA |
|--------|-------------------|--------------|
| **Training data** | Generated synthetically from taxonomy (5+ seed examples) | You provide the full training dataset (hundreds to thousands of examples) |
| **Data preparation effort** | Low — write a few seed examples and a source document | High — curate, clean, and format a large dataset |
| **Scope of change** | Broad knowledge injection and skill learning | Targeted adaptation of specific behaviors |
| **Method** | Full fine-tuning with multi-phase training (knowledge, skills, alignment) | Low-rank weight updates (freezes most parameters) |
| **VRAM requirements** | High (full fine-tuning) | Low (QLoRA can fine-tune 7B models on 16GB VRAM) |
| **Training time** | Longer (SDG + multi-phase training) | Shorter (direct training on existing data) |
| **Best for** | Teaching a model about a new domain from scratch | Adapting a model's style or behavior with existing data |
| **Risk of catastrophic forgetting** | Lower (alignment phase preserves general capabilities) | Higher (no built-in alignment preservation) |

**When to use InstructLab:** You need to teach the model about a topic it knows nothing about, and you have limited training data (a few documents and examples).

**When to use LoRA/QLoRA:** You have a large, curated dataset and want to fine-tune efficiently with limited GPU resources. LoRA is also better for quick iteration cycles.

Both approaches are valid. InstructLab's advantage is that it dramatically lowers the barrier to fine-tuning by handling data generation for you.

## Step-by-Step

### Step 1: Set Up the Taxonomy Directory

Start by examining the existing taxonomy structure and creating directories for your contributions.

```bash
# Navigate to your InstructLab working directory
cd ~/.local/share/instructlab

# View the existing taxonomy structure
ilab taxonomy diff
# This will show "No taxonomy changes detected" if you have not modified anything

# Create a knowledge contribution directory
mkdir -p taxonomy/knowledge/technology/cloud/openshift_networking

# Create a skill contribution directory
mkdir -p taxonomy/skills/extraction/yaml_to_json
```

### Step 2: Create a Knowledge Taxonomy File

Create a knowledge contribution that teaches the model about OpenShift networking concepts. First, create the source document.

Create a file at `taxonomy/knowledge/technology/cloud/openshift_networking/openshift_networking.md`:

```markdown
# OpenShift Networking

OpenShift uses a software-defined networking (SDN) model based on Open Virtual Network (OVN-Kubernetes)
as the default Container Network Interface (CNI) plugin. Every pod in an OpenShift cluster receives a
unique IP address, and pods can communicate with each other across nodes without NAT.

## Routes vs Ingress

OpenShift Routes predate Kubernetes Ingress and provide built-in TLS termination with three modes:
edge (TLS terminates at the router), passthrough (TLS goes directly to the pod), and re-encrypt
(TLS terminates at the router and a new TLS connection is established to the pod). The default
router is HAProxy-based and is pre-installed in every OpenShift cluster.

Kubernetes Ingress is also supported on OpenShift, but Routes offer more features including
wildcard routes, route-based rate limiting, and IP whitelisting without requiring annotations.

## Network Policies

OpenShift supports standard Kubernetes NetworkPolicy resources for controlling pod-to-pod traffic.
Additionally, OpenShift provides EgressFirewall resources (formerly EgressNetworkPolicy) to control
outbound traffic from pods to external IP addresses or DNS names.

## Service Mesh

OpenShift Service Mesh is based on Istio and provides mutual TLS, traffic management, and
observability for microservices. It is installed via an operator and uses sidecar proxies
(Envoy) to intercept and manage traffic between services.
```

Now create the `qna.yaml` file at `taxonomy/knowledge/technology/cloud/openshift_networking/qna.yaml`:

```yaml
created_by: tutorial-user
version: 3
domain: cloud_computing
document_outline: >
  An overview of OpenShift networking covering SDN architecture,
  Routes vs Ingress, Network Policies, and Service Mesh.
seed_examples:
  - context: >
      OpenShift uses a software-defined networking (SDN) model based on
      Open Virtual Network (OVN-Kubernetes) as the default Container
      Network Interface (CNI) plugin. Every pod in an OpenShift cluster
      receives a unique IP address, and pods can communicate with each
      other across nodes without NAT.
    questions_and_answers:
      - question: What is the default CNI plugin in OpenShift?
        answer: >
          The default CNI plugin in OpenShift is OVN-Kubernetes, which
          provides a software-defined networking model.
      - question: How do pods communicate in an OpenShift cluster?
        answer: >
          Every pod receives a unique IP address and pods can communicate
          with each other across nodes without NAT.
      - question: What networking model does OpenShift use?
        answer: >
          OpenShift uses a software-defined networking (SDN) model based
          on Open Virtual Network (OVN-Kubernetes).
  - context: >
      OpenShift Routes predate Kubernetes Ingress and provide built-in TLS
      termination with three modes: edge (TLS terminates at the router),
      passthrough (TLS goes directly to the pod), and re-encrypt (TLS
      terminates at the router and a new TLS connection is established
      to the pod). The default router is HAProxy-based and is pre-installed
      in every OpenShift cluster.
    questions_and_answers:
      - question: What are the three TLS termination modes for OpenShift Routes?
        answer: >
          The three TLS termination modes are edge (TLS terminates at the
          router), passthrough (TLS goes directly to the pod), and re-encrypt
          (TLS terminates at the router and a new TLS connection is established
          to the pod).
      - question: What is the default router implementation in OpenShift?
        answer: >
          The default router in OpenShift is HAProxy-based and comes
          pre-installed in every OpenShift cluster.
      - question: How do OpenShift Routes compare to Kubernetes Ingress historically?
        answer: >
          OpenShift Routes predate Kubernetes Ingress. They provide built-in
          TLS termination and more features than standard Ingress, including
          wildcard routes, route-based rate limiting, and IP whitelisting.
  - context: >
      OpenShift supports standard Kubernetes NetworkPolicy resources for
      controlling pod-to-pod traffic. Additionally, OpenShift provides
      EgressFirewall resources (formerly EgressNetworkPolicy) to control
      outbound traffic from pods to external IP addresses or DNS names.
    questions_and_answers:
      - question: Does OpenShift support Kubernetes NetworkPolicy?
        answer: >
          Yes, OpenShift supports standard Kubernetes NetworkPolicy resources
          for controlling pod-to-pod traffic.
      - question: How can you control outbound traffic from pods in OpenShift?
        answer: >
          OpenShift provides EgressFirewall resources (formerly
          EgressNetworkPolicy) to control outbound traffic from pods
          to external IP addresses or DNS names.
      - question: What is the difference between NetworkPolicy and EgressFirewall in OpenShift?
        answer: >
          NetworkPolicy controls pod-to-pod traffic within the cluster, while
          EgressFirewall controls outbound traffic from pods to external
          IP addresses or DNS names.
  - context: >
      OpenShift Service Mesh is based on Istio and provides mutual TLS,
      traffic management, and observability for microservices. It is
      installed via an operator and uses sidecar proxies (Envoy) to
      intercept and manage traffic between services.
    questions_and_answers:
      - question: What is OpenShift Service Mesh based on?
        answer: >
          OpenShift Service Mesh is based on Istio and provides mutual TLS,
          traffic management, and observability for microservices.
      - question: How is OpenShift Service Mesh installed?
        answer: >
          OpenShift Service Mesh is installed via an operator on the
          OpenShift cluster.
      - question: What proxy does OpenShift Service Mesh use?
        answer: >
          OpenShift Service Mesh uses Envoy sidecar proxies to intercept
          and manage traffic between services.
  - context: >
      Kubernetes Ingress is also supported on OpenShift, but Routes offer
      more features including wildcard routes, route-based rate limiting,
      and IP whitelisting without requiring annotations.
    questions_and_answers:
      - question: What additional features do OpenShift Routes provide over standard Ingress?
        answer: >
          OpenShift Routes provide wildcard routes, route-based rate limiting,
          and IP whitelisting without requiring annotations, which are not
          available in standard Kubernetes Ingress.
      - question: Can you use Kubernetes Ingress on OpenShift?
        answer: >
          Yes, Kubernetes Ingress is supported on OpenShift, but Routes are
          the native option with more features.
      - question: Why might you choose Routes over Ingress on OpenShift?
        answer: >
          Routes offer more features than Ingress on OpenShift, including
          built-in TLS termination modes, wildcard routes, route-based
          rate limiting, and IP whitelisting, all without requiring
          custom annotations.
document:
  repo: https://github.com/your-org/taxonomy-docs
  commit: main
  patterns:
    - openshift_networking.md
```

### Step 3: Create a Skill Taxonomy File

Create a skill contribution that teaches the model to convert YAML configurations to JSON format.

Create the `qna.yaml` file at `taxonomy/skills/extraction/yaml_to_json/qna.yaml`:

```yaml
created_by: tutorial-user
version: 3
task_description: >
  Convert YAML configuration files to equivalent JSON format,
  preserving all keys, values, nesting, and data types.
seed_examples:
  - question: |
      Convert this YAML to JSON:
      name: my-app
      replicas: 3
      labels:
        app: my-app
        version: v1
    answer: |
      {
        "name": "my-app",
        "replicas": 3,
        "labels": {
          "app": "my-app",
          "version": "v1"
        }
      }
  - question: |
      Convert this YAML to JSON:
      apiVersion: v1
      kind: Service
      metadata:
        name: web-service
      spec:
        ports:
          - port: 80
            targetPort: 8080
        selector:
          app: web
    answer: |
      {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
          "name": "web-service"
        },
        "spec": {
          "ports": [
            {
              "port": 80,
              "targetPort": 8080
            }
          ],
          "selector": {
            "app": "web"
          }
        }
      }
  - question: |
      Convert this YAML to JSON:
      database:
        host: localhost
        port: 5432
        credentials:
          username: admin
          password: secret
        options:
          ssl: true
          timeout: 30
    answer: |
      {
        "database": {
          "host": "localhost",
          "port": 5432,
          "credentials": {
            "username": "admin",
            "password": "secret"
          },
          "options": {
            "ssl": true,
            "timeout": 30
          }
        }
      }
  - question: |
      Convert this YAML to JSON:
      items:
        - name: widget-a
          price: 9.99
          in_stock: true
        - name: widget-b
          price: 14.50
          in_stock: false
    answer: |
      {
        "items": [
          {
            "name": "widget-a",
            "price": 9.99,
            "in_stock": true
          },
          {
            "name": "widget-b",
            "price": 14.50,
            "in_stock": false
          }
        ]
      }
  - question: |
      Convert this YAML to JSON:
      server:
        host: 0.0.0.0
        port: 8443
        tls:
          enabled: true
          cert_path: /etc/ssl/cert.pem
          key_path: /etc/ssl/key.pem
        logging:
          level: info
          format: json
    answer: |
      {
        "server": {
          "host": "0.0.0.0",
          "port": 8443,
          "tls": {
            "enabled": true,
            "cert_path": "/etc/ssl/cert.pem",
            "key_path": "/etc/ssl/key.pem"
          },
          "logging": {
            "level": "info",
            "format": "json"
          }
        }
      }
```

### Step 4: Validate the Taxonomy

Run the taxonomy validation to check for errors before generating data.

```bash
# Validate taxonomy changes
ilab taxonomy diff

# Expected output shows your new contributions:
# knowledge/technology/cloud/openshift_networking/qna.yaml
# skills/extraction/yaml_to_json/qna.yaml
# Taxonomy is valid!
```

If validation fails, common issues include:

- **Missing required fields** — Ensure `created_by`, `domain` (knowledge), or `task_description` (skills) are present.
- **Too few seed examples** — You need at least 5 seed examples. For knowledge, each seed example must have a `context` and at least 3 question-and-answer pairs.
- **YAML syntax errors** — Check indentation (2 spaces), proper use of `|` for multi-line strings, and correct quoting.
- **Missing document reference** — Knowledge contributions require a `document` field pointing to the source material.

### Step 5: Run Synthetic Data Generation

Generate synthetic training data from your taxonomy contributions.

```bash
# Run SDG with the simple pipeline (suitable for smaller GPUs)
ilab data generate \
  --pipeline simple \
  --num-instructions 100

# For larger GPUs with more memory, use the full pipeline:
# ilab data generate \
#   --pipeline full \
#   --num-instructions 250
```

SDG will take several minutes depending on your hardware. The output is saved to the `generated/` directory.

**What to expect:**

- The process generates new question-answer pairs based on your seed examples
- For knowledge contributions, the teacher model creates diverse questions about the source document
- For skill contributions, the teacher model creates new input-output pairs following the pattern you demonstrated
- Progress is displayed in the terminal

### Step 6: Review Generated Data

Before training, review the synthetic data to ensure quality.

```bash
# List generated data files
ls -la generated/

# View a sample of the generated data (the filename includes a timestamp)
# Replace the filename with the actual generated file
python3 -c "
import json
with open('generated/generated_train.jsonl', 'r') as f:
    for i, line in enumerate(f):
        if i >= 5:
            break
        data = json.loads(line)
        print(f'--- Example {i+1} ---')
        print(f'Q: {data.get(\"instruction\", data.get(\"question\", \"N/A\"))[:200]}')
        print(f'A: {data.get(\"output\", data.get(\"answer\", \"N/A\"))[:200]}')
        print()
"
```

**What to look for:**

- **Diversity** — Are the generated questions varied, or just rephrasings of the same question?
- **Accuracy** — For knowledge, are the answers factually correct according to your source document?
- **Relevance** — Do the generated examples stay within the topic of your contribution?
- **Quality** — Are there hallucinations, contradictions, or nonsensical outputs?

If the quality is poor, go back and improve your seed examples. Common fixes:

- Add more diverse seed examples covering different angles
- Make your questions more specific and varied
- For knowledge, ensure the source document is clear and well-structured
- Increase the `--num-instructions` parameter for more diversity

### Step 7: Train the Model

Run the fine-tuning process using the generated synthetic data.

```bash
# Train the model (this will take significant time depending on GPU)
ilab model train

# For more control over training parameters:
# ilab model train \
#   --num-epochs 4 \
#   --effective-batch-size 8
```

Training runs through all three phases automatically:

1. **Knowledge tuning** — The model learns the facts from your knowledge contributions
2. **Skills tuning** — The model learns the behaviors from your skill contributions
3. **Alignment** — The model is realigned to maintain general helpfulness

Training output is saved to the `models/` directory. The process can take 30 minutes to several hours depending on GPU hardware and dataset size.

### Step 8: Evaluate the Results

Test the fine-tuned model to verify it learned your contributions.

```bash
# Serve the fine-tuned model
ilab model serve --model-path models/<your-trained-model>

# In a new terminal, chat with the model
ilab model chat --model <your-trained-model>
```

Test your knowledge contribution:

```
>>> What is the default CNI plugin in OpenShift?
>>> What are the three TLS termination modes for OpenShift Routes?
>>> How does OpenShift Service Mesh work?
```

Test your skill contribution:

```
>>> Convert this YAML to JSON:
... server:
...   host: 10.0.0.1
...   port: 443
...   workers: 4
```

Compare the fine-tuned model's responses against the base model to see the improvement. If the results are not satisfactory:

- Review and improve your seed examples
- Generate more synthetic data (`--num-instructions 250` or higher)
- Add more seed examples to cover edge cases
- Retrain with adjusted parameters

## Verification

Your lesson is complete when:

1. **Taxonomy files exist and are valid:**
   ```bash
   ilab taxonomy diff
   # Shows your knowledge and skill contributions with no errors
   ```

2. **Synthetic data was generated:**
   ```bash
   ls generated/
   # Shows generated_train.jsonl (or similar) with training data
   ```

3. **Model was trained:**
   ```bash
   ls models/
   # Shows a new model directory with your fine-tuned model
   ```

4. **Knowledge questions are answered correctly:**
   - The model accurately describes OpenShift networking concepts from your taxonomy
   - Answers are grounded in the source document you provided

5. **Skill tasks are performed correctly:**
   - The model converts YAML to JSON with proper formatting
   - Nested structures, arrays, and data types are preserved

## Key Takeaways

- The **taxonomy** is a hierarchical directory structure with two contribution types: **knowledge** (new facts backed by a source document) and **skills** (new capabilities demonstrated by input-output examples). Each requires at least 5 seed examples.
- **Synthetic Data Generation (SDG)** transforms a handful of seed examples into a large, diverse training dataset using a teacher model. This is the core innovation of InstructLab -- it dramatically reduces the amount of human-authored training data needed.
- Training proceeds in **three phases** (knowledge tuning, skills tuning, alignment), all managed automatically by `ilab model train`. The alignment phase is critical for preventing degradation of the model's general capabilities.
- **InstructLab's LAB approach differs from LoRA/QLoRA** in a fundamental way: LAB generates its own training data from a small taxonomy, while LoRA requires a pre-existing large dataset. LAB is better for domain injection from scratch; LoRA is better for targeted adaptation with existing data and limited GPU resources.
- Always **review generated data quality** before training. Poor seed examples produce poor synthetic data, which produces a poor model. Iterate on your taxonomy based on SDG results.

## Next Steps

Continue to [L2-M2.2 — RHEL AI Production Deployment](../2_production_deployment/) to learn how to configure RHEL AI for production use with systemd services, TLS, multi-model serving, and monitoring.
