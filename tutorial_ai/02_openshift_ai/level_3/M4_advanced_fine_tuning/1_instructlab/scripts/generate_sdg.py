"""
L3-M4.1 -- InstructLab on OpenShift AI
Synthetic Data Generation (SDG) from an InstructLab taxonomy.

This script reads a taxonomy YAML file, connects to a teacher model served
via a vLLM endpoint on OpenShift AI, and generates synthetic question-answer
pairs for each taxonomy entry. The output is a JSONL file ready for
LAB-tuning (multi-phase LoRA training).

Components:
  1. Load and validate the taxonomy YAML
  2. Connect to the teacher model endpoint
  3. Generate knowledge examples from context + seed examples
  4. Generate skill examples from seed input-output pairs
  5. Filter and deduplicate generated examples
  6. Save to JSONL format

Usage:
  # Set environment variables
  export TEACHER_ENDPOINT="https://gemma-4-e4b-your-project.apps.cluster.example.com/v1"
  export TEACHER_MODEL="gemma-4-e4b"

  # Run SDG
  python generate_sdg.py \
    --taxonomy /opt/app-root/src/lab-tuning/taxonomy.yaml \
    --output /opt/app-root/src/lab-tuning/sdg_output.jsonl \
    --num-examples 5

Expected output:
  Processing 2 knowledge entries...
    [acme_corp_products] seed 1/5: generated 5 examples
    [acme_corp_products] seed 2/5: generated 5 examples
    ...
  Processing 2 skill entries...
    [product_comparison] seed 1/3: generated 5 examples
    ...
  SDG complete:
    Total examples: 55
    Knowledge examples: 25
    Skill examples: 30
  Output saved to /opt/app-root/src/lab-tuning/sdg_output.jsonl
"""

import argparse
import json
import logging
import os
import sys
from typing import Any

import yaml
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Taxonomy Loading and Validation
# ---------------------------------------------------------------------------

def load_taxonomy(path: str) -> dict[str, Any]:
    """Load and validate a taxonomy YAML file."""
    logger.info(f"Loading taxonomy from {path}")

    if not os.path.exists(path):
        logger.error(f"Taxonomy file not found: {path}")
        sys.exit(1)

    with open(path) as f:
        taxonomy = yaml.safe_load(f)

    # Validate required fields
    required_fields = ["version", "created_by", "domain"]
    for field in required_fields:
        if field not in taxonomy:
            logger.error(f"Taxonomy missing required field: {field}")
            sys.exit(1)

    knowledge = taxonomy.get("knowledge", [])
    skills = taxonomy.get("skills", [])

    if not knowledge and not skills:
        logger.error("Taxonomy must contain at least one knowledge or skill entry")
        sys.exit(1)

    # Validate entries
    for i, entry in enumerate(knowledge):
        if "seed_examples" not in entry or not entry["seed_examples"]:
            logger.error(f"Knowledge entry {i} has no seed_examples")
            sys.exit(1)
        if "context" not in entry or not entry["context"].strip():
            logger.warning(f"Knowledge entry {i} has no context -- SDG quality may be low")

    for i, entry in enumerate(skills):
        if "seed_examples" not in entry or not entry["seed_examples"]:
            logger.error(f"Skill entry {i} has no seed_examples")
            sys.exit(1)

    logger.info(
        f"Taxonomy loaded: {len(knowledge)} knowledge entries, "
        f"{len(skills)} skill entries"
    )
    return taxonomy


# ---------------------------------------------------------------------------
# Teacher Model Connection
# ---------------------------------------------------------------------------

def create_teacher_client(endpoint: str) -> OpenAI:
    """Create an OpenAI-compatible client for the teacher model."""
    logger.info(f"Connecting to teacher model at {endpoint}")

    client = OpenAI(
        base_url=endpoint,
        api_key="unused",  # vLLM does not require a real API key
        timeout=120.0,     # SDG prompts can be slow for large contexts
    )

    # Verify connectivity
    try:
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        logger.info(f"Teacher model available: {model_ids}")
    except Exception as e:
        logger.error(f"Failed to connect to teacher model: {e}")
        logger.error("Ensure the model serving endpoint is accessible from this workbench")
        sys.exit(1)

    return client


# ---------------------------------------------------------------------------
# Knowledge SDG
# ---------------------------------------------------------------------------

KNOWLEDGE_PROMPT_TEMPLATE = """You are a training data generator. Your task is to create \
new question-answer pairs based on the provided context and example.

## Context (source material)
{context}

## Example question-answer pair (use this as a style template)
Question: {question}
Answer: {answer}

## Instructions
Generate exactly {num_examples} new, diverse question-answer pairs based on the context above.
Each pair must:
1. Ask about a DIFFERENT fact or aspect from the context than the example
2. Provide a detailed, factual answer citing specific data from the context
3. Follow the same answer style and detail level as the example

Return your response as a JSON array. Each element must have "question" and "answer" keys.
Do not include any text outside the JSON array.

Output:"""


def generate_knowledge_examples(
    client: OpenAI,
    model: str,
    entry: dict[str, Any],
    num_examples: int,
    temperature: float,
) -> list[dict]:
    """Generate synthetic examples from a knowledge taxonomy entry."""
    context = entry.get("context", "")
    task_desc = entry.get("task_description", "")
    topic = entry.get("topic", "unknown")
    results = []

    for i, seed in enumerate(entry["seed_examples"]):
        logger.info(f"  [{topic}] seed {i + 1}/{len(entry['seed_examples'])}: generating...")

        prompt = KNOWLEDGE_PROMPT_TEMPLATE.format(
            context=context,
            question=seed["question"],
            answer=seed["answer"],
            num_examples=num_examples,
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=2048,
            )

            content = response.choices[0].message.content.strip()

            # Try to extract JSON array from the response
            pairs = _parse_json_array(content)

            for pair in pairs:
                if "question" in pair and "answer" in pair:
                    results.append({
                        "messages": [
                            {"role": "system", "content": task_desc},
                            {"role": "user", "content": pair["question"]},
                            {"role": "assistant", "content": pair["answer"]},
                        ],
                        "source": "sdg-knowledge",
                        "taxonomy_topic": topic,
                    })

            logger.info(f"  [{topic}] seed {i + 1}/{len(entry['seed_examples'])}: generated {len(pairs)} examples")

        except Exception as e:
            logger.warning(f"  [{topic}] seed {i + 1}: generation failed: {e}")

    return results


# ---------------------------------------------------------------------------
# Skill SDG
# ---------------------------------------------------------------------------

SKILL_PROMPT_TEMPLATE = """You are a training data generator. Your task is to create \
new input-output pairs that demonstrate the same skill pattern.

## Skill description
{task_description}

## Example input-output pair (use this as a pattern template)
Input: {question}
Output: {answer}

## Instructions
Generate exactly {num_examples} new input-output pairs that demonstrate the same skill.
Each pair must:
1. Use a DIFFERENT scenario or set of data than the example
2. Follow the SAME output format and structure
3. Be realistic and internally consistent

Return your response as a JSON array. Each element must have "question" and "answer" keys.
Do not include any text outside the JSON array.

Output:"""


def generate_skill_examples(
    client: OpenAI,
    model: str,
    entry: dict[str, Any],
    num_examples: int,
    temperature: float,
) -> list[dict]:
    """Generate synthetic examples from a skill taxonomy entry."""
    task_desc = entry.get("task_description", "")
    topic = entry.get("topic", "unknown")
    results = []

    for i, seed in enumerate(entry["seed_examples"]):
        logger.info(f"  [{topic}] seed {i + 1}/{len(entry['seed_examples'])}: generating...")

        prompt = SKILL_PROMPT_TEMPLATE.format(
            task_description=task_desc,
            question=seed["question"],
            answer=seed["answer"],
            num_examples=num_examples,
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=2048,
            )

            content = response.choices[0].message.content.strip()
            pairs = _parse_json_array(content)

            for pair in pairs:
                if "question" in pair and "answer" in pair:
                    results.append({
                        "messages": [
                            {"role": "system", "content": task_desc},
                            {"role": "user", "content": pair["question"]},
                            {"role": "assistant", "content": pair["answer"]},
                        ],
                        "source": "sdg-skill",
                        "taxonomy_topic": topic,
                    })

            logger.info(f"  [{topic}] seed {i + 1}/{len(entry['seed_examples'])}: generated {len(pairs)} examples")

        except Exception as e:
            logger.warning(f"  [{topic}] seed {i + 1}: generation failed: {e}")

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_array(content: str) -> list[dict]:
    """Extract a JSON array from model output, handling common formatting issues."""
    # Try direct parse first
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON array within the text (model may add explanation around it)
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(content[start:end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON array from teacher output")
    return []


def deduplicate(examples: list[dict]) -> list[dict]:
    """Remove duplicate examples based on the user message content."""
    seen = set()
    unique = []

    for example in examples:
        user_msg = example["messages"][1]["content"].strip().lower()
        if user_msg not in seen:
            seen.add(user_msg)
            unique.append(example)
        else:
            logger.debug(f"Removed duplicate: {user_msg[:60]}...")

    removed = len(examples) - len(unique)
    if removed > 0:
        logger.info(f"Deduplication removed {removed} examples")

    return unique


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic training data from an InstructLab taxonomy"
    )
    parser.add_argument(
        "--taxonomy", required=True,
        help="Path to the taxonomy YAML file",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to save the generated JSONL file",
    )
    parser.add_argument(
        "--num-examples", type=int, default=5,
        help="Number of synthetic examples to generate per seed example (default: 5)",
    )
    parser.add_argument(
        "--teacher-endpoint", default=None,
        help="Teacher model endpoint URL (default: TEACHER_ENDPOINT env var)",
    )
    parser.add_argument(
        "--teacher-model", default=None,
        help="Teacher model name (default: TEACHER_MODEL env var)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.8,
        help="Sampling temperature for the teacher model (default: 0.8)",
    )
    args = parser.parse_args()

    # Resolve teacher endpoint and model
    endpoint = args.teacher_endpoint or os.environ.get("TEACHER_ENDPOINT")
    model = args.teacher_model or os.environ.get("TEACHER_MODEL")

    if not endpoint:
        logger.error(
            "Teacher endpoint not specified. Set TEACHER_ENDPOINT env var or "
            "use --teacher-endpoint"
        )
        sys.exit(1)
    if not model:
        logger.error(
            "Teacher model not specified. Set TEACHER_MODEL env var or "
            "use --teacher-model"
        )
        sys.exit(1)

    # Load taxonomy
    taxonomy = load_taxonomy(args.taxonomy)
    client = create_teacher_client(endpoint)

    all_examples = []

    # Generate knowledge examples
    knowledge_entries = taxonomy.get("knowledge", [])
    if knowledge_entries:
        logger.info(f"Processing {len(knowledge_entries)} knowledge entries...")
        for entry in knowledge_entries:
            examples = generate_knowledge_examples(
                client, model, entry, args.num_examples, args.temperature,
            )
            all_examples.extend(examples)

    # Generate skill examples
    skill_entries = taxonomy.get("skills", [])
    if skill_entries:
        logger.info(f"Processing {len(skill_entries)} skill entries...")
        for entry in skill_entries:
            examples = generate_skill_examples(
                client, model, entry, args.num_examples, args.temperature,
            )
            all_examples.extend(examples)

    # Deduplicate
    all_examples = deduplicate(all_examples)

    # Save output
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w") as f:
        for example in all_examples:
            f.write(json.dumps(example) + "\n")

    # Report
    knowledge_count = sum(1 for e in all_examples if e["source"] == "sdg-knowledge")
    skill_count = sum(1 for e in all_examples if e["source"] == "sdg-skill")

    logger.info("SDG complete:")
    logger.info(f"  Total examples: {len(all_examples)}")
    logger.info(f"  Knowledge examples: {knowledge_count}")
    logger.info(f"  Skill examples: {skill_count}")
    logger.info(f"Output saved to {args.output}")


if __name__ == "__main__":
    main()
