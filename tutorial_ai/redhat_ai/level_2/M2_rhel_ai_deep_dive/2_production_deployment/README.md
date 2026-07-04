# L2-M2.2 — RHEL AI Production Deployment

**Level:** Practitioner
**Duration:** 45 min

## Overview

This lesson covers how to move RHEL AI from a development tool into a production-grade inference service. You will configure vLLM as a persistent systemd service, secure the inference endpoint with TLS, set up multi-model serving, configure Prometheus monitoring, create backup procedures for your fine-tuned models and taxonomies, and understand how RHEL AI's image-based upgrade model keeps your platform current without risking your data.

## Prerequisites

- Completed L2-M2.1 (InstructLab Taxonomy and SDG) -- you have a fine-tuned model ready to serve
- RHEL AI instance running on a server with GPU access
- Basic familiarity with systemd, TLS certificates, and Prometheus
- Root or sudo access on the RHEL AI host
- `openssl` installed (for generating self-signed certificates)

## Concepts

### Production RHEL AI Architecture

In development, you run `ilab model serve` interactively and stop it when you are done. In production, the inference service must:

- **Start automatically** on boot and restart on failure (systemd)
- **Accept encrypted connections** so inference requests and responses are not sent in plaintext (TLS)
- **Manage resources** to prevent GPU memory exhaustion and ensure predictable performance
- **Emit metrics** so you can monitor throughput, latency, and errors (Prometheus)
- **Serve multiple models** when different applications need different models from the same server

RHEL AI uses vLLM as its inference engine. vLLM provides an OpenAI-compatible API server that supports all of these requirements through configuration flags and environment variables.

---

### Systemd Service for vLLM

Running vLLM as a systemd service gives you:

- **Automatic startup** -- the model server starts when the machine boots
- **Automatic restart** -- if vLLM crashes, systemd restarts it immediately
- **Resource control** -- systemd cgroups can limit CPU and memory usage
- **Logging** -- all output goes to journald, searchable with `journalctl`
- **Dependency management** -- the service can wait for GPU drivers to load before starting

The systemd unit file defines the model path, GPU allocation, port, and any other vLLM configuration.

---

### TLS Configuration

By default, vLLM serves on HTTP. For production, you need HTTPS to protect:

- **Inference requests** -- prompts may contain sensitive business data
- **Inference responses** -- model outputs may contain proprietary information
- **Authentication tokens** -- if you add API key authentication, tokens must not be sent in plaintext

vLLM supports TLS natively through `--ssl-certfile` and `--ssl-keyfile` flags. You can use certificates from your organization's CA, Let's Encrypt, or self-signed certificates for internal services.

---

### Multi-Model Serving

A single RHEL AI server can serve multiple models simultaneously by running multiple vLLM instances on different ports. Common scenarios:

- **Base model + fine-tuned model** -- serve both for A/B comparison
- **Different model sizes** -- a small model for low-latency tasks, a large model for complex tasks
- **Different domains** -- models fine-tuned for different business units

Each model instance needs its own:
- Systemd unit file
- Port number
- GPU allocation (or shared GPU with memory limits)

GPU memory is the primary constraint. A server with a single GPU can serve multiple small models or one large model. Use vLLM's `--gpu-memory-utilization` flag to control how much GPU memory each instance claims. When sharing a single GPU, the combined utilization values must not exceed approximately 0.95 to leave headroom for system overhead.

---

### Backup and Versioning

Fine-tuned models represent significant compute investment. You need to:

- **Back up models** -- copy model weights to durable storage (NFS, S3, external drive)
- **Version taxonomies** -- use git to track changes to your taxonomy directory
- **Version training data** -- keep generated synthetic data alongside the taxonomy version that produced it
- **Tag model versions** -- associate each model with the taxonomy and training run that created it

A naming convention like `granite-3.1-8b-openshift-v1.0` makes it clear which base model was used and what version of fine-tuning was applied.

---

### Upgrading RHEL AI

RHEL AI uses Image Mode for RHEL, which means upgrades are atomic and rollback-safe. This is fundamentally different from upgrading a traditional server with `yum update`:

- **Atomic image replacement** -- the entire OS (including GPU drivers, vLLM, InstructLab, and all dependencies) is delivered as a single container image. An upgrade replaces the boot image in one operation. If the upgrade fails, the previous image is still available at the bootloader.
- **Data partition is separate** -- models, taxonomies, and generated data stored under `/var` survive upgrades because the data partition is not part of the OS image. Your fine-tuned models are safe.
- **Rollback is instant** -- if a new RHEL AI version introduces a regression (a vLLM behavior change, a driver incompatibility), you reboot into the previous image. No need to debug or manually downgrade packages.

**Model compatibility across versions:** Always test after upgrading. A new vLLM version may change:

- Default quantization behavior or precision handling
- API response format details (new fields, changed defaults)
- Tokenizer handling or prompt templating
- Supported model architectures or configuration parameters

The safe upgrade procedure:

1. Back up your models and taxonomies (Step 7 below)
2. Pull and stage the new RHEL AI image
3. Reboot into the new image
4. Verify your models load and serve correctly
5. Run a representative set of test prompts to check output quality
6. If anything is wrong, reboot into the previous image

```bash
# Check current RHEL AI image version
rpm-ostree status

# Stage an upgrade (downloads but does not apply)
rpm-ostree upgrade --preview

# Apply the upgrade (takes effect on next reboot)
rpm-ostree upgrade

# Reboot into the new image
sudo systemctl reboot

# If something is wrong, rollback to the previous image
rpm-ostree rollback
sudo systemctl reboot
```

---

### Monitoring vLLM

vLLM exposes a Prometheus metrics endpoint at `/metrics` by default. Key metrics include:

| Metric | Description |
|--------|-------------|
| `vllm:num_requests_running` | Number of requests currently being processed |
| `vllm:num_requests_waiting` | Number of requests queued and waiting |
| `vllm:num_requests_total` | Total requests received (counter) |
| `vllm:avg_generation_throughput_toks_per_s` | Average token generation speed |
| `vllm:gpu_cache_usage_perc` | Percentage of GPU KV cache in use |
| `vllm:cpu_cache_usage_perc` | Percentage of CPU KV cache in use |
| `vllm:request_success_total` | Total successful requests (counter) |
| `vllm:avg_prompt_throughput_toks_per_s` | Average prompt processing speed |

These metrics tell you whether the server is overloaded (high queue depth), running out of memory (high cache usage), or performing well (high throughput).

## Step-by-Step

### Step 1: Create a Systemd Unit File for vLLM

Create a systemd service that runs vLLM as a persistent inference server.

```bash
# Create the systemd unit file
sudo tee /etc/systemd/system/vllm-inference.service << 'EOF'
[Unit]
Description=vLLM Inference Server - Primary Model
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=vllm
Group=vllm
WorkingDirectory=/var/lib/vllm

# Model and server configuration
ExecStart=/usr/bin/python3 -m vllm.entrypoints.openai.api_server \
    --model /var/lib/vllm/models/granite-3.1-8b-instruct \
    --served-model-name granite-3.1-8b \
    --host 0.0.0.0 \
    --port 8443 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 4096 \
    --dtype auto \
    --tensor-parallel-size 1 \
    --ssl-certfile /etc/vllm/tls/server.crt \
    --ssl-keyfile /etc/vllm/tls/server.key

# Restart policy
Restart=on-failure
RestartSec=10

# Resource limits
LimitNOFILE=65536
LimitMEMLOCK=infinity

# Security hardening
ProtectSystem=strict
ReadWritePaths=/var/lib/vllm /var/log/vllm
ProtectHome=yes
NoNewPrivileges=yes

# Environment
Environment=CUDA_VISIBLE_DEVICES=0
Environment=HF_HOME=/var/lib/vllm/.cache/huggingface

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vllm-inference

[Install]
WantedBy=multi-user.target
EOF
```

Key configuration choices in this unit file:

| Flag | Purpose |
|------|---------|
| `--gpu-memory-utilization 0.85` | Reserve 85% of GPU memory for the model, leaving headroom for the system |
| `--max-model-len 4096` | Maximum context length -- lower values use less GPU memory |
| `--tensor-parallel-size 1` | Number of GPUs to split the model across (1 for single GPU) |
| `--dtype auto` | Automatically select the best precision for your GPU |
| `--ssl-certfile` / `--ssl-keyfile` | Enable HTTPS |
| `CUDA_VISIBLE_DEVICES=0` | Pin to GPU 0 (important for multi-model serving) |

Create the vllm user and directories:

```bash
# Create a dedicated service user
sudo useradd -r -s /sbin/nologin -d /var/lib/vllm vllm

# Create required directories
sudo mkdir -p /var/lib/vllm/models
sudo mkdir -p /var/lib/vllm/.cache/huggingface
sudo mkdir -p /var/log/vllm
sudo mkdir -p /etc/vllm/tls

# Copy your fine-tuned model to the serving directory
sudo cp -r ~/.local/share/instructlab/models/granite-3.1-8b-instruct \
    /var/lib/vllm/models/

# Set ownership
sudo chown -R vllm:vllm /var/lib/vllm /var/log/vllm
```

### Step 2: Configure TLS

Generate a TLS certificate for the inference endpoint. For production, use certificates from your organization's CA. For this tutorial, we will create a self-signed certificate.

```bash
# Generate a self-signed certificate (valid for 365 days)
sudo openssl req -x509 -nodes \
    -days 365 \
    -newkey rsa:2048 \
    -keyout /etc/vllm/tls/server.key \
    -out /etc/vllm/tls/server.crt \
    -subj "/CN=rhel-ai-server.example.com" \
    -addext "subjectAltName=DNS:rhel-ai-server.example.com,DNS:localhost,IP:127.0.0.1"

# Set correct permissions
sudo chmod 640 /etc/vllm/tls/server.key
sudo chmod 644 /etc/vllm/tls/server.crt
sudo chown vllm:vllm /etc/vllm/tls/server.key /etc/vllm/tls/server.crt
```

For production environments, replace the self-signed certificate with one from your CA:

```bash
# Example with an organizational CA
sudo cp /path/to/ca-signed/server.crt /etc/vllm/tls/server.crt
sudo cp /path/to/ca-signed/server.key /etc/vllm/tls/server.key
sudo chown vllm:vllm /etc/vllm/tls/server.key /etc/vllm/tls/server.crt
```

### Step 3: Start and Verify the Service

Enable and start the vLLM service.

```bash
# Reload systemd to pick up the new unit file
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable vllm-inference.service

# Start the service
sudo systemctl start vllm-inference.service

# Check the service status
sudo systemctl status vllm-inference.service
```

Expected output:

```
● vllm-inference.service - vLLM Inference Server - Primary Model
     Loaded: loaded (/etc/systemd/system/vllm-inference.service; enabled; preset: disabled)
     Active: active (running) since ...
```

Verify the endpoint is responding:

```bash
# Test with curl (use -k for self-signed certificates)
curl -k https://localhost:8443/v1/models

# Expected response:
# {"object":"list","data":[{"id":"granite-3.1-8b","object":"model",...}]}

# Test inference
curl -k https://localhost:8443/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "granite-3.1-8b",
        "messages": [
            {"role": "user", "content": "What is OpenShift?"}
        ],
        "max_tokens": 100
    }'
```

View logs with journald:

```bash
# Follow real-time logs
sudo journalctl -u vllm-inference.service -f

# View recent logs
sudo journalctl -u vllm-inference.service --since "10 minutes ago"

# Search for errors
sudo journalctl -u vllm-inference.service -p err

# View logs for a specific time window (useful for debugging incidents)
sudo journalctl -u vllm-inference.service \
    --since "2025-01-15 10:00:00" \
    --until "2025-01-15 11:00:00"

# Show only the last 50 lines
sudo journalctl -u vllm-inference.service -n 50
```

### Step 4: Set Up Multi-Model Serving

To serve a second model, create another systemd unit file on a different port with a different GPU allocation. The key constraint is GPU memory -- you must partition it carefully.

**Multi-GPU setup** (recommended): assign each model to a separate GPU.

**Single-GPU setup**: reduce `--gpu-memory-utilization` for each model so the total stays below 0.95.

```
# Single GPU allocation examples:
#
# Two models on one 40GB GPU:
#   Primary model (8B):    --gpu-memory-utilization 0.55  (~22GB)
#   Secondary model (2B):  --gpu-memory-utilization 0.35  (~14GB)
#   Remaining:             ~4GB for system overhead
#
# Two models on one 80GB GPU:
#   Primary model (8B):    --gpu-memory-utilization 0.50  (~40GB)
#   Secondary model (8B):  --gpu-memory-utilization 0.40  (~32GB)
#   Remaining:             ~8GB for system overhead
```

Create the second service unit file:

```bash
# Create a second service for a smaller model
sudo tee /etc/systemd/system/vllm-inference-small.service << 'EOF'
[Unit]
Description=vLLM Inference Server - Small Model
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=vllm
Group=vllm
WorkingDirectory=/var/lib/vllm

ExecStart=/usr/bin/python3 -m vllm.entrypoints.openai.api_server \
    --model /var/lib/vllm/models/granite-3.1-2b-instruct \
    --served-model-name granite-3.1-2b \
    --host 0.0.0.0 \
    --port 8444 \
    --gpu-memory-utilization 0.35 \
    --max-model-len 2048 \
    --dtype auto \
    --tensor-parallel-size 1 \
    --ssl-certfile /etc/vllm/tls/server.crt \
    --ssl-keyfile /etc/vllm/tls/server.key

Restart=on-failure
RestartSec=10
LimitNOFILE=65536
LimitMEMLOCK=infinity
ProtectSystem=strict
ReadWritePaths=/var/lib/vllm /var/log/vllm
ProtectHome=yes
NoNewPrivileges=yes

# Multi-GPU: assign to GPU 1 with CUDA_VISIBLE_DEVICES=1
# Single-GPU: share GPU 0 with reduced memory allocation
Environment=CUDA_VISIBLE_DEVICES=0
Environment=HF_HOME=/var/lib/vllm/.cache/huggingface

StandardOutput=journal
StandardError=journal
SyslogIdentifier=vllm-inference-small

[Install]
WantedBy=multi-user.target
EOF
```

> **Important:** If sharing a single GPU, you must also reduce the primary model's `--gpu-memory-utilization` in `vllm-inference.service`. For example, change it from `0.85` to `0.55`, then restart the primary service before starting the secondary.

Start the second service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vllm-inference-small.service
sudo systemctl start vllm-inference-small.service

# Verify both services are running
sudo systemctl status vllm-inference.service vllm-inference-small.service

# Test the second model
curl -k https://localhost:8444/v1/models
```

Port routing summary:

| Port | Model | Purpose |
|------|-------|---------|
| 8443 | `granite-3.1-8b` | Primary model -- complex tasks, higher quality |
| 8444 | `granite-3.1-2b` | Secondary model -- simple tasks, lower latency |

Applications connect to the appropriate port based on their needs. For a unified entry point, place an HTTPS reverse proxy (nginx, HAProxy) in front of both instances and route by path or header.

### Step 5: Configure Prometheus Monitoring

vLLM exposes Prometheus metrics by default at `/metrics`. Configure Prometheus to scrape these endpoints.

Create a Prometheus scrape configuration. If you already have Prometheus running, add these targets to your existing configuration:

```bash
# Create Prometheus configuration directory
sudo mkdir -p /etc/prometheus
```

Example Prometheus configuration (`/etc/prometheus/prometheus.yml`):

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "vllm"
    scheme: https
    tls_config:
      insecure_skip_verify: true  # Remove this when using CA-signed certificates
    metrics_path: /metrics
    static_configs:
      - targets:
          - "localhost:8443"
        labels:
          model: "granite-3.1-8b"
          instance_role: "primary"
      - targets:
          - "localhost:8444"
        labels:
          model: "granite-3.1-2b"
          instance_role: "secondary"
```

Verify metrics are accessible:

```bash
# Check the metrics endpoint
curl -k https://localhost:8443/metrics | head -30

# You should see output like:
# # HELP vllm:num_requests_running Number of requests currently running
# # TYPE vllm:num_requests_running gauge
# vllm:num_requests_running 0
# # HELP vllm:num_requests_waiting Number of requests waiting to be processed
# # TYPE vllm:num_requests_waiting gauge
# vllm:num_requests_waiting 0
# ...
```

Key metrics to watch and what they mean:

| Metric | Healthy Range | Action When Exceeded |
|--------|---------------|----------------------|
| `vllm:num_requests_waiting` | 0-5 | Scale up or reduce traffic -- requests are queueing |
| `vllm:gpu_cache_usage_perc` | Below 0.90 | Reduce `--max-model-len` or add GPU memory |
| `vllm:avg_generation_throughput_toks_per_s` | Depends on model/GPU | Investigate if it drops significantly below baseline |
| `vllm:num_requests_running` | Varies | Correlate with latency to find your concurrency sweet spot |

### Step 6: Create a Health Check Script

Create a script for monitoring and alerting systems to verify the inference service is healthy.

```bash
sudo tee /usr/local/bin/vllm-health-check.sh << 'SCRIPT'
#!/bin/bash
# vLLM Health Check Script
# Returns 0 if all configured vLLM instances are healthy, 1 otherwise.

ENDPOINTS=(
    "https://localhost:8443/v1/models"
    "https://localhost:8444/v1/models"
)

EXIT_CODE=0

for endpoint in "${ENDPOINTS[@]}"; do
    HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 5 "$endpoint")
    if [ "$HTTP_CODE" != "200" ]; then
        echo "UNHEALTHY: $endpoint returned HTTP $HTTP_CODE"
        EXIT_CODE=1
    else
        echo "HEALTHY: $endpoint"
    fi
done

exit $EXIT_CODE
SCRIPT

sudo chmod +x /usr/local/bin/vllm-health-check.sh
```

Test the health check:

```bash
/usr/local/bin/vllm-health-check.sh
# Expected:
# HEALTHY: https://localhost:8443/v1/models
# HEALTHY: https://localhost:8444/v1/models
```

You can integrate this script with systemd timers, cron, or external monitoring tools (Nagios, Zabbix, Datadog) for continuous health monitoring.

### Step 7: Create Backup Scripts

Create a backup procedure for models, taxonomies, and training data.

```bash
sudo tee /usr/local/bin/vllm-backup.sh << 'SCRIPT'
#!/bin/bash
# RHEL AI Backup Script
# Backs up models, taxonomies, and training data to a specified directory.

BACKUP_DIR="${1:-/var/backups/rhel-ai}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

echo "Starting RHEL AI backup to ${BACKUP_PATH}..."

# Create backup directory
mkdir -p "${BACKUP_PATH}"

# Backup models (large -- consider rsync for incremental backups)
echo "Backing up models..."
rsync -a --progress /var/lib/vllm/models/ "${BACKUP_PATH}/models/"

# Backup taxonomy (small -- always do a full copy)
echo "Backing up taxonomy..."
cp -r ~/.local/share/instructlab/taxonomy "${BACKUP_PATH}/taxonomy"

# Backup generated training data
echo "Backing up training data..."
cp -r ~/.local/share/instructlab/generated "${BACKUP_PATH}/generated" 2>/dev/null || true

# Backup InstructLab configuration
echo "Backing up InstructLab config..."
cp -r ~/.config/instructlab "${BACKUP_PATH}/instructlab-config" 2>/dev/null || true

# Backup systemd unit files
echo "Backing up service configurations..."
mkdir -p "${BACKUP_PATH}/systemd"
cp /etc/systemd/system/vllm-inference*.service "${BACKUP_PATH}/systemd/"

# Backup TLS certificates
echo "Backing up TLS certificates..."
cp -r /etc/vllm/tls "${BACKUP_PATH}/tls"

# Create a manifest
cat > "${BACKUP_PATH}/MANIFEST.txt" << MANIFEST
RHEL AI Backup
Date: $(date)
Host: $(hostname)
RHEL AI Image: $(rpm-ostree status --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['deployments'][0].get('container-image-reference','N/A'))" 2>/dev/null || echo "N/A")
Kernel: $(uname -r)
GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo "N/A")
Models: $(ls /var/lib/vllm/models/ 2>/dev/null | tr '\n' ', ')
MANIFEST

echo "Backup complete: ${BACKUP_PATH}"
echo "Total size: $(du -sh "${BACKUP_PATH}" | cut -f1)"
SCRIPT

sudo chmod +x /usr/local/bin/vllm-backup.sh
```

Run the backup:

```bash
# Backup to default location
sudo /usr/local/bin/vllm-backup.sh

# Backup to a specific location (e.g., NFS mount)
sudo /usr/local/bin/vllm-backup.sh /mnt/nfs/ai-backups
```

For taxonomy versioning, use git:

```bash
cd ~/.local/share/instructlab/taxonomy

# Initialize git if not already done
git init
git add -A
git commit -m "Initial taxonomy: OpenShift networking knowledge + YAML-to-JSON skill"

# After making changes
git add -A
git commit -m "v1.1: improved OpenShift networking seed examples"

# Tag releases that correspond to trained models
git tag -a "model-v1.0" -m "Taxonomy used for granite-3.1-8b-openshift-v1.0"
```

**Model version tracking:** When you train a new model, record the relationship between the taxonomy version and the model artifact:

```bash
# After training, record the lineage
cat > /var/lib/vllm/models/granite-3.1-8b-openshift-v1.0/TRAINING_INFO.txt << INFO
Base model:     granite-3.1-8b-instruct
Taxonomy tag:   model-v1.0
Training date:  $(date)
SDG pipeline:   simple
Num instructions: 100
Host:           $(hostname)
GPU:            $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null)
INFO
```

## Verification

Your lesson is complete when:

1. **vLLM is running as a systemd service:**
   ```bash
   sudo systemctl is-active vllm-inference.service
   # Output: active
   ```

2. **TLS is configured and working:**
   ```bash
   curl -k https://localhost:8443/v1/models
   # Returns model list over HTTPS
   ```

3. **Multi-model serving is operational:**
   ```bash
   curl -k https://localhost:8443/v1/models  # Primary model
   curl -k https://localhost:8444/v1/models  # Secondary model
   # Both return their respective model information
   ```

4. **Prometheus metrics are accessible:**
   ```bash
   curl -k https://localhost:8443/metrics | grep "vllm:num_requests"
   # Returns Prometheus-format metrics
   ```

5. **Health check passes:**
   ```bash
   /usr/local/bin/vllm-health-check.sh
   # All endpoints report HEALTHY
   ```

6. **Backup script runs successfully:**
   ```bash
   sudo /usr/local/bin/vllm-backup.sh /tmp/test-backup
   ls /tmp/test-backup/*/MANIFEST.txt
   # Backup directory contains models, taxonomy, and configuration
   ```

## Key Takeaways

- Running vLLM as a **systemd service** provides automatic startup, restart on failure, journald logging, and resource control -- all essential for production reliability. The unit file is the single source of truth for your model serving configuration.
- **TLS is non-negotiable** for production inference endpoints. Prompts and completions often contain sensitive data. vLLM supports TLS natively through `--ssl-certfile` and `--ssl-keyfile` flags.
- **Multi-model serving** on a single server is possible by running multiple vLLM instances on different ports. GPU memory is the primary constraint -- use `--gpu-memory-utilization` to partition GPU memory between models (keeping the combined total below 0.95), or assign each model to a different GPU with `CUDA_VISIBLE_DEVICES`.
- **vLLM exposes Prometheus metrics** at `/metrics` by default. Monitor `num_requests_waiting` (queue depth), `gpu_cache_usage_perc` (memory pressure), and `avg_generation_throughput_toks_per_s` (performance) to detect problems before they affect users.
- **Back up your fine-tuned models** -- they represent significant compute investment. Use git for taxonomy versioning and rsync for incremental model backups. Tag taxonomy versions to associate them with trained model versions.
- **RHEL AI upgrades are atomic and rollback-safe** thanks to Image Mode for RHEL. Data under `/var` (models, taxonomies) survives upgrades, but always test model compatibility after upgrading -- vLLM behavior can change between versions.

## Next Steps

Continue to [L2-M3.1 -- End-to-End: Podman AI Lab to RHEL AI to OpenShift AI](../../M3_cross_tier_workflows/1_end_to_end/) to see how a model moves through all three tiers of the Red Hat AI stack, from desktop prototyping through fine-tuning to production deployment at scale.
