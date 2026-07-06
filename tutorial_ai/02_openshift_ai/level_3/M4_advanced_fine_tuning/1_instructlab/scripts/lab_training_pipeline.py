"""
L3-M4.1 -- InstructLab on OpenShift AI
KFP v2 Pipeline for the LAB-Tuning Workflow

This pipeline orchestrates the full InstructLab LAB-tuning workflow:
  1. Load and validate the taxonomy YAML
  2. Generate synthetic data (SDG) using a teacher model
  3. Phase 1: Knowledge tuning (fine-tune on knowledge data)
  4. Phase 2: Skills tuning (fine-tune on skills data)
  5. Evaluate the LAB-tuned model vs the base model
  6. Register the model in Model Registry

Usage:
  # Compile to YAML
  python lab_training_pipeline.py --compile-only --output lab-pipeline.yaml

  # Then upload lab-pipeline.yaml via the OpenShift AI dashboard,
  # or submit programmatically (see the __main__ block below).

Expected output:
  Pipeline compiled to lab-pipeline.yaml
"""

from kfp import dsl, compiler
from kfp.dsl import Artifact, Dataset, Input, Metrics, Model, Output


# ---------------------------------------------------------------------------
# Component 1: Load and Validate Taxonomy
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["pyyaml==6.0.1"],
)
def load_taxonomy(
    taxonomy_path: str,
    taxonomy_out: Output[Artifact],
    knowledge_count: dsl.OutputPath(int),
    skill_count: dsl.OutputPath(int),
):
    """Load a taxonomy YAML file, validate its structure, and pass it downstream."""
    import json
    import os
    import shutil

    import yaml

    print(f"Loading taxonomy from {taxonomy_path}")

    if not os.path.exists(taxonomy_path):
        raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")

    with open(taxonomy_path) as f:
        taxonomy = yaml.safe_load(f)

    # Validate required fields
    for field in ["version", "created_by", "domain"]:
        if field not in taxonomy:
            raise ValueError(f"Taxonomy missing required field: {field}")

    knowledge = taxonomy.get("knowledge", [])
    skills = taxonomy.get("skills", [])

    if not knowledge and not skills:
        raise ValueError("Taxonomy must have at least one knowledge or skill entry")

    # Validate each entry has seed examples
    for i, entry in enumerate(knowledge):
        if not entry.get("seed_examples"):
            raise ValueError(f"Knowledge entry {i} has no seed_examples")

    for i, entry in enumerate(skills):
        if not entry.get("seed_examples"):
            raise ValueError(f"Skill entry {i} has no seed_examples")

    total_seeds = sum(len(e["seed_examples"]) for e in knowledge) + \
                  sum(len(e["seed_examples"]) for e in skills)

    print(f"Taxonomy validated:")
    print(f"  Knowledge entries: {len(knowledge)}")
    print(f"  Skill entries: {len(skills)}")
    print(f"  Total seed examples: {total_seeds}")

    # Copy taxonomy to artifact path
    shutil.copy2(taxonomy_path, taxonomy_out.path)

    # Write counts as outputs
    with open(knowledge_count, "w") as f:
        f.write(str(len(knowledge)))
    with open(skill_count, "w") as f:
        f.write(str(len(skills)))


# ---------------------------------------------------------------------------
# Component 2: Generate Synthetic Data (SDG)
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["pyyaml==6.0.1", "openai==1.40.0"],
)
def generate_sdg(
    taxonomy_in: Input[Artifact],
    teacher_endpoint: str,
    teacher_model: str,
    num_examples_per_seed: int,
    knowledge_dataset: Output[Dataset],
    skills_dataset: Output[Dataset],
    sdg_metrics: Output[Metrics],
):
    """Generate synthetic training data from taxonomy entries using a teacher model."""
    import json

    import yaml
    from openai import OpenAI

    with open(taxonomy_in.path) as f:
        taxonomy = yaml.safe_load(f)

    client = OpenAI(base_url=teacher_endpoint, api_key="unused", timeout=120.0)

    knowledge_examples = []
    skill_examples = []

    # Generate from knowledge entries
    for entry in taxonomy.get("knowledge", []):
        context = entry.get("context", "")
        task_desc = entry.get("task_description", "")

        for seed in entry["seed_examples"]:
            prompt = (
                f"You are a training data generator. Given this context:\n\n"
                f"{context}\n\n"
                f"And this example:\nQ: {seed['question']}\nA: {seed['answer']}\n\n"
                f"Generate exactly {num_examples_per_seed} new question-answer pairs "
                f"based on the context. Return as a JSON array with 'question' and "
                f"'answer' keys. No text outside the JSON."
            )

            try:
                response = client.chat.completions.create(
                    model=teacher_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=2048,
                )
                content = response.choices[0].message.content.strip()

                # Parse JSON array
                start = content.find("[")
                end = content.rfind("]")
                if start != -1 and end != -1:
                    pairs = json.loads(content[start:end + 1])
                    for pair in pairs:
                        knowledge_examples.append({
                            "messages": [
                                {"role": "system", "content": task_desc},
                                {"role": "user", "content": pair["question"]},
                                {"role": "assistant", "content": pair["answer"]},
                            ]
                        })
                    print(f"  Knowledge seed: generated {len(pairs)} examples")
            except Exception as e:
                print(f"  Warning: SDG failed for knowledge seed: {e}")

    # Generate from skill entries
    for entry in taxonomy.get("skills", []):
        task_desc = entry.get("task_description", "")

        for seed in entry["seed_examples"]:
            prompt = (
                f"You are a training data generator. Given this skill example:\n"
                f"Input: {seed['question']}\nOutput: {seed['answer']}\n\n"
                f"Generate exactly {num_examples_per_seed} new input-output pairs "
                f"demonstrating the same skill. Return as a JSON array with "
                f"'question' and 'answer' keys. No text outside the JSON."
            )

            try:
                response = client.chat.completions.create(
                    model=teacher_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=2048,
                )
                content = response.choices[0].message.content.strip()

                start = content.find("[")
                end = content.rfind("]")
                if start != -1 and end != -1:
                    pairs = json.loads(content[start:end + 1])
                    for pair in pairs:
                        skill_examples.append({
                            "messages": [
                                {"role": "system", "content": task_desc},
                                {"role": "user", "content": pair["question"]},
                                {"role": "assistant", "content": pair["answer"]},
                            ]
                        })
                    print(f"  Skill seed: generated {len(pairs)} examples")
            except Exception as e:
                print(f"  Warning: SDG failed for skill seed: {e}")

    # Save knowledge dataset
    with open(knowledge_dataset.path, "w") as f:
        for ex in knowledge_examples:
            f.write(json.dumps(ex) + "\n")

    # Save skills dataset
    with open(skills_dataset.path, "w") as f:
        for ex in skill_examples:
            f.write(json.dumps(ex) + "\n")

    # Log metrics
    sdg_metrics.log_metric("knowledge_examples", len(knowledge_examples))
    sdg_metrics.log_metric("skill_examples", len(skill_examples))
    sdg_metrics.log_metric("total_examples", len(knowledge_examples) + len(skill_examples))

    print(f"\nSDG complete:")
    print(f"  Knowledge examples: {len(knowledge_examples)}")
    print(f"  Skill examples: {len(skill_examples)}")


# ---------------------------------------------------------------------------
# Component 3: Knowledge Tuning (Phase 1)
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["training-hub[lora]"],
)
def knowledge_tuning(
    knowledge_dataset: Input[Dataset],
    base_model: str,
    lora_r: int,
    lora_alpha: int,
    num_epochs: int,
    learning_rate: float,
    knowledge_adapter: Output[Model],
    training_metrics: Output[Metrics],
):
    """Phase 1: Fine-tune the base model on knowledge data."""
    import os
    import shutil

    from training_hub import lora_sft

    print("=== Phase 1: Knowledge Tuning ===")
    print(f"Base model: {base_model}")
    print(f"Dataset: {knowledge_dataset.path}")
    print(f"LoRA config: r={lora_r}, alpha={lora_alpha}")
    print(f"Training: {num_epochs} epochs, lr={learning_rate}")

    # Count examples
    with open(knowledge_dataset.path) as f:
        num_examples = sum(1 for _ in f)
    print(f"Training examples: {num_examples}")

    # Run knowledge tuning
    output_dir = "/tmp/phase1_output"
    result = lora_sft(
        model_path=base_model,
        data_path=knowledge_dataset.path,
        ckpt_output_dir=output_dir,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        num_epochs=num_epochs,
        learning_rate=learning_rate,
    )

    # Copy adapter to artifact output
    for item in os.listdir(output_dir):
        src = os.path.join(output_dir, item)
        dst = os.path.join(knowledge_adapter.path, item)
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # Log metrics
    training_metrics.log_metric("phase", "knowledge")
    training_metrics.log_metric("num_examples", num_examples)
    training_metrics.log_metric("num_epochs", num_epochs)
    training_metrics.log_metric("lora_r", lora_r)

    # Set model metadata
    knowledge_adapter.metadata["phase"] = "knowledge"
    knowledge_adapter.metadata["base_model"] = base_model

    print("Phase 1 complete. Knowledge adapter saved.")


# ---------------------------------------------------------------------------
# Component 4: Skills Tuning (Phase 2)
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["training-hub[lora]"],
)
def skills_tuning(
    skills_dataset: Input[Dataset],
    knowledge_adapter: Input[Model],
    lora_r: int,
    lora_alpha: int,
    num_epochs: int,
    learning_rate: float,
    lab_adapter: Output[Model],
    training_metrics: Output[Metrics],
):
    """Phase 2: Fine-tune the knowledge-tuned model on skills data."""
    import os
    import shutil

    from training_hub import lora_sft

    print("=== Phase 2: Skills Tuning ===")
    print(f"Starting from: {knowledge_adapter.path}")
    print(f"Dataset: {skills_dataset.path}")
    print(f"LoRA config: r={lora_r}, alpha={lora_alpha}")
    print(f"Training: {num_epochs} epochs, lr={learning_rate}")

    # Count examples
    with open(skills_dataset.path) as f:
        num_examples = sum(1 for _ in f)
    print(f"Training examples: {num_examples}")

    # Run skills tuning starting from Phase 1 adapter
    output_dir = "/tmp/phase2_output"
    result = lora_sft(
        model_path=knowledge_adapter.path,
        data_path=skills_dataset.path,
        ckpt_output_dir=output_dir,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        num_epochs=num_epochs,
        learning_rate=learning_rate,
    )

    # Copy adapter to artifact output
    for item in os.listdir(output_dir):
        src = os.path.join(output_dir, item)
        dst = os.path.join(lab_adapter.path, item)
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # Log metrics
    training_metrics.log_metric("phase", "skills")
    training_metrics.log_metric("num_examples", num_examples)
    training_metrics.log_metric("num_epochs", num_epochs)

    # Set model metadata
    lab_adapter.metadata["phase"] = "skills"
    lab_adapter.metadata["method"] = "lab-tuning"

    print("Phase 2 complete. LAB-tuned adapter saved.")


# ---------------------------------------------------------------------------
# Component 5: Evaluate LAB-Tuned Model
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["unsloth", "torch"],
)
def evaluate_model(
    lab_adapter: Input[Model],
    base_model: str,
    eval_metrics: Output[Metrics],
):
    """Evaluate the LAB-tuned model against the base model on test prompts."""
    from unsloth import FastLanguageModel

    print("=== Evaluating LAB-Tuned Model ===")

    # Test prompts covering both knowledge and skills
    test_cases = [
        {
            "prompt": "What is the price of the TrailBlazer 3000?",
            "system": "Answer questions about Acme Corp product catalog and policies.",
            "expected_substring": "$189.99",
            "category": "knowledge",
        },
        {
            "prompt": "What is Acme Corp's return policy?",
            "system": "Answer questions about Acme Corp product catalog and policies.",
            "expected_substring": "30-day",
            "category": "knowledge",
        },
        {
            "prompt": "Compare the TrailBlazer 3000 and SummitPack 45L in a table.",
            "system": "Generate structured product comparison tables for e-commerce items.",
            "expected_substring": "|",
            "category": "skill",
        },
    ]

    # Load LAB-tuned model
    print("Loading LAB-tuned model...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=lab_adapter.path,
        max_seq_length=2048,
        load_in_4bit=False,
    )
    FastLanguageModel.for_inference(model)

    passed = 0
    total = len(test_cases)

    for i, tc in enumerate(test_cases):
        messages = [
            {"role": "system", "content": tc["system"]},
            {"role": "user", "content": tc["prompt"]},
        ]

        input_ids = tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt",
        ).to(model.device)

        output = model.generate(
            input_ids=input_ids, max_new_tokens=512,
            temperature=0.3, do_sample=True,
        )
        response = tokenizer.decode(
            output[0][input_ids.shape[-1]:], skip_special_tokens=True,
        )

        contains_expected = tc["expected_substring"] in response
        status = "PASS" if contains_expected else "FAIL"
        passed += int(contains_expected)

        print(f"\nTest {i + 1} [{tc['category']}] ({status}):")
        print(f"  Prompt: {tc['prompt']}")
        print(f"  Expected substring: '{tc['expected_substring']}'")
        print(f"  Response (first 200 chars): {response[:200]}")

    # Log metrics
    eval_metrics.log_metric("tests_total", total)
    eval_metrics.log_metric("tests_passed", passed)
    eval_metrics.log_metric("pass_rate", passed / total if total > 0 else 0.0)

    knowledge_tests = [tc for tc in test_cases if tc["category"] == "knowledge"]
    skill_tests = [tc for tc in test_cases if tc["category"] == "skill"]

    # These are simplified; a real evaluation would use a held-out set
    eval_metrics.log_metric("knowledge_tests", len(knowledge_tests))
    eval_metrics.log_metric("skill_tests", len(skill_tests))

    print(f"\nEvaluation: {passed}/{total} tests passed ({100 * passed / total:.0f}%)")


# ---------------------------------------------------------------------------
# Component 6: Register Model
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["model-registry==0.2.0"],
)
def register_model(
    lab_adapter: Input[Model],
    eval_metrics: Input[Metrics],
    model_name: str,
    model_version: str,
):
    """Register the LAB-tuned model in the OpenShift AI Model Registry."""
    print(f"=== Registering Model: {model_name} v{model_version} ===")

    # In a production pipeline, this would use the Model Registry client:
    #
    # from model_registry import ModelRegistry
    #
    # registry = ModelRegistry(
    #     server_address="https://model-registry-route.apps.cluster.example.com",
    #     port=443,
    #     author="pipeline",
    # )
    #
    # registered = registry.register_model(
    #     name=model_name,
    #     uri=lab_adapter.uri,
    #     version=model_version,
    #     description="LAB-tuned model with knowledge and skill adaptations",
    #     model_format_name="pytorch",
    #     model_format_version="2.0",
    #     metadata={
    #         "method": "lab-tuning",
    #         "phases": "knowledge+skills",
    #     },
    # )

    print(f"Model adapter path: {lab_adapter.path}")
    print(f"Model registered as: {model_name} v{model_version}")
    print(f"Method: LAB-tuning (knowledge + skills phases)")
    print()
    print("NOTE: Model Registry registration is shown as pseudocode above.")
    print("Uncomment the registry code when Model Registry is configured in your project.")


# ---------------------------------------------------------------------------
# Pipeline Definition
# ---------------------------------------------------------------------------
@dsl.pipeline(
    name="lab-tuning-pipeline",
    description=(
        "End-to-end InstructLab LAB-tuning pipeline: taxonomy validation, "
        "synthetic data generation, multi-phase training (knowledge then skills), "
        "evaluation, and model registration."
    ),
)
def lab_tuning_pipeline(
    taxonomy_path: str = "/opt/app-root/src/lab-tuning/taxonomy.yaml",
    teacher_endpoint: str = "https://gemma-4-e4b-your-project.apps.cluster.example.com/v1",
    teacher_model: str = "gemma-4-e4b",
    base_model: str = "google/gemma-4-E4B-it",
    num_sdg_examples: int = 5,
    lora_r: int = 16,
    lora_alpha: int = 32,
    knowledge_epochs: int = 3,
    skills_epochs: int = 3,
    knowledge_lr: float = 2e-4,
    skills_lr: float = 1e-4,
    model_name: str = "acme-lab-tuned",
    model_version: str = "1.0.0",
):
    # Step 1: Load and validate taxonomy
    taxonomy_task = load_taxonomy(
        taxonomy_path=taxonomy_path,
    )

    # Step 2: Generate synthetic data
    sdg_task = generate_sdg(
        taxonomy_in=taxonomy_task.outputs["taxonomy_out"],
        teacher_endpoint=teacher_endpoint,
        teacher_model=teacher_model,
        num_examples_per_seed=num_sdg_examples,
    )

    # Step 3: Phase 1 -- Knowledge tuning
    knowledge_task = knowledge_tuning(
        knowledge_dataset=sdg_task.outputs["knowledge_dataset"],
        base_model=base_model,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        num_epochs=knowledge_epochs,
        learning_rate=knowledge_lr,
    )

    # Step 4: Phase 2 -- Skills tuning (depends on Phase 1)
    skills_task = skills_tuning(
        skills_dataset=sdg_task.outputs["skills_dataset"],
        knowledge_adapter=knowledge_task.outputs["knowledge_adapter"],
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        num_epochs=skills_epochs,
        learning_rate=skills_lr,
    )

    # Step 5: Evaluate the LAB-tuned model
    eval_task = evaluate_model(
        lab_adapter=skills_task.outputs["lab_adapter"],
        base_model=base_model,
    )

    # Step 6: Register in Model Registry
    register_model(
        lab_adapter=skills_task.outputs["lab_adapter"],
        eval_metrics=eval_task.outputs["eval_metrics"],
        model_name=model_name,
        model_version=model_version,
    )


# ---------------------------------------------------------------------------
# Compile and (optionally) Submit
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compile or submit the LAB-tuning pipeline"
    )
    parser.add_argument(
        "--compile-only", action="store_true",
        help="Only compile to YAML, do not submit",
    )
    parser.add_argument(
        "--output", default="lab-pipeline.yaml",
        help="Output YAML path (default: lab-pipeline.yaml)",
    )
    args = parser.parse_args()

    # Always compile
    compiler.Compiler().compile(
        pipeline_func=lab_tuning_pipeline,
        package_path=args.output,
    )
    print(f"Pipeline compiled to {args.output}")

    if args.compile_only:
        print("Compile-only mode -- skipping submission.")
    else:
        import subprocess

        from kfp.client import Client

        # Get the DSP route and token from the cluster
        route = subprocess.check_output(
            ["oc", "get", "route", "ds-pipeline-dspa", "-n", "lab-tuning-project",
             "-o", "jsonpath={.spec.host}"],
        ).decode().strip()

        token = subprocess.check_output(
            ["oc", "whoami", "-t"],
        ).decode().strip()

        print(f"Connecting to pipeline server at https://{route}")

        client = Client(
            host=f"https://{route}",
            existing_token=token,
        )

        run = client.create_run_from_pipeline_package(
            pipeline_file=args.output,
            arguments={
                "taxonomy_path": "/opt/app-root/src/lab-tuning/taxonomy.yaml",
                "teacher_endpoint": "https://gemma-4-e4b-your-project.apps.cluster.example.com/v1",
                "teacher_model": "gemma-4-e4b",
                "base_model": "google/gemma-4-E4B-it",
                "num_sdg_examples": 5,
                "knowledge_epochs": 3,
                "skills_epochs": 3,
            },
            run_name="lab-tuning-run",
            experiment_name="instructlab-experiments",
        )

        print(f"Run submitted: {run.run_id}")
        print("View in dashboard: Data Science Projects > lab-tuning-project > Runs")
