"""
Merge a LoRA adapter with the base model and upload to S3.

This script performs four operations:
  1. Downloads the LoRA adapter files from S3
  2. Loads the base model and applies the LoRA adapter using PEFT
  3. Merges the adapter weights into the base model and saves the result
  4. Uploads the merged model to S3 for serving via KServe/vLLM

Requirements:
  pip install torch transformers peft accelerate safetensors boto3

Environment variables:
  S3_ENDPOINT       - S3-compatible endpoint URL (e.g., https://minio.example.com)
  S3_BUCKET         - S3 bucket name (e.g., models)
  AWS_ACCESS_KEY_ID - S3 access key
  AWS_SECRET_ACCESS_KEY - S3 secret key
  S3_ADAPTER_PATH   - S3 prefix where the LoRA adapter is stored
                      (e.g., gemma-4-e4b-lora-adapter)
  S3_MERGED_PATH    - S3 prefix where the merged model will be uploaded
                      (e.g., gemma-4-e4b-finetuned)
  BASE_MODEL        - Hugging Face model ID for the base model
                      (e.g., google/gemma-4-E4B-it)
  LOCAL_MERGE_DIR   - Local directory to save the merged model before uploading
                      (default: ./merged_model)
  HF_TOKEN          - (Optional) Hugging Face token for gated models

To get S3 credentials from your OpenShift data connection:
  oc get secret <data-connection-name> -n <project> \
    -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
  oc get secret <data-connection-name> -n <project> \
    -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d
  oc get secret <data-connection-name> -n <project> \
    -o jsonpath='{.data.AWS_S3_ENDPOINT}' | base64 -d
"""

import os
import sys
from pathlib import Path


def get_env(name: str, default: str | None = None) -> str:
    """Get a required environment variable or exit with an error."""
    value = os.environ.get(name, default)
    if value is None:
        print(f"Error: environment variable {name} is required but not set.")
        sys.exit(1)
    return value


def create_s3_client():
    """Create a boto3 S3 client using environment variables."""
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=get_env("S3_ENDPOINT"),
        aws_access_key_id=get_env("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=get_env("AWS_SECRET_ACCESS_KEY"),
        # Disable SSL verification for self-signed certs (common in dev).
        # For production, set verify=True and configure proper CA certs.
        verify=False,
    )


def download_adapter_from_s3(
    s3_client, bucket: str, adapter_prefix: str, local_dir: Path
) -> None:
    """Download all files under the adapter prefix from S3."""
    print("\n[1/4] Downloading LoRA adapter from S3...")
    local_dir.mkdir(parents=True, exist_ok=True)

    # List all objects under the adapter prefix
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=adapter_prefix)

    file_count = 0
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Get the relative path within the adapter directory
            relative_path = key[len(adapter_prefix) :].lstrip("/")
            if not relative_path:
                continue

            local_path = local_dir / relative_path
            local_path.parent.mkdir(parents=True, exist_ok=True)

            print(f"  Downloaded: {relative_path}")
            s3_client.download_file(bucket, key, str(local_path))
            file_count += 1

    if file_count == 0:
        print(f"  Error: no files found at s3://{bucket}/{adapter_prefix}/")
        sys.exit(1)

    print(f"  Adapter saved to: {local_dir}")


def load_and_merge_model(base_model_id: str, adapter_dir: Path, merge_dir: Path) -> None:
    """Load the base model, apply the LoRA adapter, merge, and save."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    hf_token = os.environ.get("HF_TOKEN")

    # --- Load base model ---
    print("\n[2/4] Loading base model and LoRA adapter...")
    print(f"  Loading base model: {base_model_id}")

    tokenizer = AutoTokenizer.from_pretrained(
        base_model_id,
        token=hf_token,
    )

    model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="auto",
        token=hf_token,
    )

    # --- Load LoRA adapter ---
    print(f"  Loading LoRA adapter from: {adapter_dir}")
    model = PeftModel.from_pretrained(model, str(adapter_dir))
    print("  Adapter loaded successfully")

    # --- Merge ---
    print("\n[3/4] Merging adapter into base model...")
    print("  Merging weights...")
    model = model.merge_and_unload()

    # --- Save ---
    print(f"  Saving merged model to: {merge_dir}")
    merge_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(merge_dir, safe_serialization=True)
    tokenizer.save_pretrained(merge_dir)

    # Report saved files
    total_size = 0
    file_count = 0
    for f in merge_dir.iterdir():
        if f.is_file():
            total_size += f.stat().st_size
            file_count += 1

    total_gb = total_size / (1024**3)
    print(f"  Merged model saved ({file_count} files, {total_gb:.1f} GB total)")


def upload_model_to_s3(
    s3_client, bucket: str, merged_prefix: str, merge_dir: Path
) -> None:
    """Upload all files in the merged model directory to S3."""
    print("\n[4/4] Uploading merged model to S3...")

    for file_path in sorted(merge_dir.iterdir()):
        if not file_path.is_file():
            continue
        # Skip hidden files and temporary files
        if file_path.name.startswith("."):
            continue

        s3_key = f"{merged_prefix}/{file_path.name}"
        print(f"  Uploading: {file_path.name}")
        s3_client.upload_file(str(file_path), bucket, s3_key)

    print(f"  Upload complete: s3://{bucket}/{merged_prefix}/")


def main() -> None:
    # --- Configuration from environment ---
    bucket = get_env("S3_BUCKET", "models")
    adapter_prefix = get_env("S3_ADAPTER_PATH", "gemma-4-e4b-lora-adapter")
    merged_prefix = get_env("S3_MERGED_PATH", "gemma-4-e4b-finetuned")
    base_model_id = get_env("BASE_MODEL", "google/gemma-4-E4B-it")
    merge_dir = Path(get_env("LOCAL_MERGE_DIR", "./merged_model"))
    adapter_download_dir = Path("./adapter_download")

    print("=" * 60)
    print("LoRA Adapter Merge and Upload")
    print("=" * 60)
    print(f"  Base model:    {base_model_id}")
    print(f"  Adapter path:  s3://{bucket}/{adapter_prefix}/")
    print(f"  Merged path:   s3://{bucket}/{merged_prefix}/")
    print(f"  Local dir:     {merge_dir}")

    # Step 1: Download adapter from S3
    s3_client = create_s3_client()
    download_adapter_from_s3(s3_client, bucket, adapter_prefix, adapter_download_dir)

    # Step 2+3: Load base model, apply adapter, merge, save
    load_and_merge_model(base_model_id, adapter_download_dir, merge_dir)

    # Step 4: Upload merged model to S3
    upload_model_to_s3(s3_client, bucket, merged_prefix, merge_dir)

    print("\nDone. Merged model is ready for serving.")
    print(f"  Use storageUri: s3://{bucket}/{merged_prefix}/")


if __name__ == "__main__":
    main()
