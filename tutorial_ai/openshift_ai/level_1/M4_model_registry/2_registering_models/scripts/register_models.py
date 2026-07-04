#!/usr/bin/env python3
"""
Register models in the OpenShift AI Model Registry.

This script demonstrates the full Python SDK workflow:
1. Connect to the registry
2. Register the base Gemma4-e4b model (v1-base)
3. Register the fine-tuned version (v2-finetuned) with metadata
4. List all models and versions
5. Query a specific version and its artifact

Prerequisites:
  pip install model-registry

Usage:
  # From outside the cluster (with port-forward running):
  #   oc port-forward svc/model-registry-tutorial-registry 8080:8080 -n rhoai-model-registries &
  python3 register_models.py

  # From inside a workbench (no port-forward needed):
  python3 register_models.py --in-cluster

  # Custom server address:
  python3 register_models.py --server http://my-registry-host --port 8080
"""

import argparse
import sys

from model_registry import ModelRegistry


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# In-cluster service address (when running from a workbench)
IN_CLUSTER_ADDRESS = (
    "http://model-registry-tutorial-registry"
    ".rhoai-model-registries.svc.cluster.local"
)

# Local address (when port-forwarding)
LOCAL_ADDRESS = "http://localhost"

DEFAULT_PORT = 8080
DEFAULT_AUTHOR = "tutorial-user"


def connect(server_address: str, port: int, author: str) -> ModelRegistry:
    """Connect to the Model Registry."""
    print(f"Connecting to registry at {server_address}:{port} ...")
    registry = ModelRegistry(
        server_address=server_address,
        port=port,
        author=author,
        is_secure=False,
    )
    print("Connected.\n")
    return registry


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_base_model(registry: ModelRegistry) -> None:
    """Register the base Gemma4-e4b model (v1-base)."""
    print("=" * 60)
    print("Registering base model: gemma4-e4b v1-base")
    print("=" * 60)

    rm = registry.register_model(
        "gemma4-e4b",
        # Replace with your actual model storage URI:
        "hf://google/gemma-4-E4B-it",
        model_format_name="vLLM",
        model_format_version="1",
        version="v1-base",
        description=(
            "Original base model from Hugging Face (google/gemma-4-E4B-it). "
            "No fine-tuning applied. Served via vLLM with FP16 precision."
        ),
        metadata={
            "source": "huggingface",
            "hf_model_id": "google/gemma-4-E4B-it",
            "parameter_count": 4000000000,
            "quantization": "half",
            "max_model_len": 8192,
            "gpu_memory_utilization": 0.95,
            "is_fine_tuned": False,
        },
    )

    print(f"  Registered model: {rm.name} (ID: {rm.id})")
    print(f"  Description: {rm.description}")
    print()


def register_finetuned_model(registry: ModelRegistry) -> None:
    """Register the fine-tuned Gemma4-e4b model (v2-finetuned)."""
    print("=" * 60)
    print("Registering fine-tuned model: gemma4-e4b v2-finetuned")
    print("=" * 60)

    rm = registry.register_model(
        "gemma4-e4b",
        # Replace with your actual fine-tuned model storage URI:
        "s3://models/gemma4-e4b/finetuned-lora-merged/",
        model_format_name="vLLM",
        model_format_version="1",
        version="v2-finetuned",
        description=(
            "LoRA fine-tuned on custom-instructions-v1 dataset. "
            "Adapter merged with base model for serving."
        ),
        metadata={
            "base_model": "google/gemma-4-E4B-it",
            "fine_tuning_method": "LoRA",
            "lora_rank": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "target_modules": "q_proj,v_proj,k_proj,o_proj",
            "training_epochs": 3,
            "training_dataset": "custom-instructions-v1",
            "quantization": "half",
            "is_merged": True,
            "is_fine_tuned": True,
        },
    )

    print(f"  Registered model: {rm.name} (ID: {rm.id})")
    print()


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

def list_all_models(registry: ModelRegistry) -> None:
    """List all registered models and their versions."""
    print("=" * 60)
    print("All registered models")
    print("=" * 60)

    for model in registry.get_registered_models():
        print(f"\nModel: {model.name}")
        print(f"  ID: {model.id}")
        print(f"  Description: {model.description}")
        print(f"  State: {model.state}")

        # List versions for this model
        print(f"  Versions:")
        for version in registry.get_model_versions(model.name):
            print(f"    - {version.name} (ID: {version.id})")
            print(f"      Author: {version.author}")
            print(f"      Description: {version.description}")

            # Get the artifact for this version
            try:
                artifact = registry.get_model_artifact(model.name, version.name)
                print(f"      Artifact URI: {artifact.uri}")
                print(f"      Model format: {artifact.model_format_name}")
            except Exception:
                print(f"      Artifact: (none)")

    print()


def query_specific_version(registry: ModelRegistry) -> None:
    """Query a specific version and display its metadata."""
    print("=" * 60)
    print("Querying specific version: gemma4-e4b v2-finetuned")
    print("=" * 60)

    version = registry.get_model_version("gemma4-e4b", "v2-finetuned")
    artifact = registry.get_model_artifact("gemma4-e4b", "v2-finetuned")

    print(f"\nVersion name: {version.name}")
    print(f"Version ID: {version.id}")
    print(f"Author: {version.author}")
    print(f"Description: {version.description}")
    print(f"State: {version.state}")
    print(f"\nArtifact URI: {artifact.uri}")
    print(f"Model format: {artifact.model_format_name}")
    print(f"Model format version: {artifact.model_format_version}")

    # Display custom properties if available
    if hasattr(version, "custom_properties") and version.custom_properties:
        print(f"\nCustom properties:")
        for key, value in version.custom_properties.items():
            print(f"  {key}: {value}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Register models in the OpenShift AI Model Registry"
    )
    parser.add_argument(
        "--in-cluster",
        action="store_true",
        help="Use in-cluster service address (for workbenches)",
    )
    parser.add_argument(
        "--server",
        type=str,
        default=None,
        help="Custom registry server address",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Registry port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--author",
        type=str,
        default=DEFAULT_AUTHOR,
        help=f"Author name for registered models (default: {DEFAULT_AUTHOR})",
    )
    parser.add_argument(
        "--skip-register",
        action="store_true",
        help="Skip registration, only list existing models",
    )

    args = parser.parse_args()

    # Determine server address
    if args.server:
        server_address = args.server
    elif args.in_cluster:
        server_address = IN_CLUSTER_ADDRESS
    else:
        server_address = LOCAL_ADDRESS

    # Connect
    try:
        registry = connect(server_address, args.port, args.author)
    except Exception as e:
        print(f"ERROR: Could not connect to registry at {server_address}:{args.port}")
        print(f"  {e}")
        print()
        print("If running locally, make sure the port-forward is active:")
        print("  oc port-forward svc/model-registry-tutorial-registry 8080:8080 \\")
        print("    -n rhoai-model-registries &")
        sys.exit(1)

    # Register models
    if not args.skip_register:
        register_base_model(registry)
        register_finetuned_model(registry)

    # Query and display
    list_all_models(registry)
    query_specific_version(registry)

    print("Done. Check the OpenShift AI dashboard (AI Hub > Registry) to see")
    print("the registered models in the web interface.")


if __name__ == "__main__":
    main()
