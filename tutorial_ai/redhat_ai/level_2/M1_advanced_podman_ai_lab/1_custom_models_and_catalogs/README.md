# L2-M1.1 — Custom Models and Catalogs

**Level:** Practitioner
**Duration:** 45 min

## Overview

Podman AI Lab ships with a curated model catalog and pre-built recipes, but real-world teams need to bring their own models and build custom AI applications. In this lesson you will import a GGUF model from HuggingFace, create a custom catalog entry for your team, and build a custom recipe that runs as a containerized application inside Podman AI Lab.

## Prerequisites

- Completed Level 1 (L1-M2: Podman AI Lab lessons)
- Podman Desktop with Podman AI Lab extension installed
- Podman 5.0.1+ running
- Basic familiarity with HuggingFace model hub
- ~10 GB free disk space for model downloads

## Concepts

### Custom Model Import

Podman AI Lab uses **GGUF** (GPT-Generated Unified Format) models for local inference via its llama.cpp backend. You already know from L1-M2 that the built-in catalog provides a curated selection. But what about:

- A smaller or larger variant of Granite not in the catalog?
- A community model you found on HuggingFace (Phi, Qwen, Gemma)?
- A model you fine-tuned on RHEL AI or OpenShift AI?

For fine-tuned models coming from RHEL AI (which produces SafeTensors/PyTorch format via InstructLab), you need to convert to GGUF before importing. The `llama.cpp` project provides conversion tools, and many HuggingFace repos include pre-converted GGUF variants.

### Custom Recipe Catalogs

Podman AI Lab's recipe catalog is defined in a JSON format. You can extend it with a **user catalog** (`user-catalog.json`) that adds:

- **Custom models**: your own GGUF models with metadata (name, description, license, download URL)
- **Custom recipes**: your own AI applications with build instructions
- **Custom categories**: organize recipes into logical groups

User catalogs overlay the built-in catalog. Your team can share a single `user-catalog.json` to ensure everyone has the same models and recipes available.

### Custom Recipes

A recipe is a containerized AI application that Podman AI Lab can build and run. Under the hood, every recipe is:

1. A Git repository (or local directory) with application code
2. A `Containerfile` (Dockerfile) that builds the application image
3. Metadata in the catalog JSON that tells AI Lab how to wire it up with a model server

You can build any AI application as a recipe: RAG pipelines, code assistants, document analyzers, customer support bots. The key constraint is that the application connects to the model server via the OpenAI-compatible API on the container network.

## Step-by-Step

### Step 1: Find and Download a GGUF Model from HuggingFace

We will import a Granite model variant that is not in the default Podman AI Lab catalog. Browse HuggingFace for a GGUF-formatted model.

**Option A: Download via the HuggingFace CLI**

```bash
# Install the HuggingFace CLI if you don't have it
pip install huggingface-hub

# Download a specific GGUF file (example: Granite 3.3 2B Instruct)
huggingface-cli download \
  lmstudio-community/granite-3.3-2b-instruct-GGUF \
  granite-3.3-2b-instruct-Q4_K_M.gguf \
  --local-dir ~/ai-models/
```

**Option B: Download directly with curl**

```bash
# Create a directory for your models
mkdir -p ~/ai-models

# Download the GGUF file (example URL — check HuggingFace for the actual link)
curl -L -o ~/ai-models/granite-3.3-2b-instruct-Q4_K_M.gguf \
  "https://huggingface.co/lmstudio-community/granite-3.3-2b-instruct-GGUF/resolve/main/granite-3.3-2b-instruct-Q4_K_M.gguf"
```

> **Tip:** Q4_K_M quantization is a good balance of quality and size for local development. For production evaluation, use Q8_0 or FP16.

### Step 2: Import the Model into Podman AI Lab

There are two ways to import a custom model:

**Via the UI:**

1. Open Podman Desktop and navigate to **AI Lab > Models**
2. Click **Import Model** (or the "+" button)
3. Browse to your downloaded `.gguf` file (e.g., `~/ai-models/granite-3.3-2b-instruct-Q4_K_M.gguf`)
4. Fill in the metadata:
   - **Name**: `granite-3.3-2b-instruct`
   - **Description**: `IBM Granite 3.3 2B Instruct — Q4_K_M quantization`
   - **License**: `Apache-2.0`
5. Click **Import**

**Via the CLI (advanced):**

Podman AI Lab stores model metadata in its application data directory. You can also place the GGUF file directly into the AI Lab models directory:

```bash
# Find where Podman AI Lab stores models (varies by OS)
# macOS:
ls ~/Library/Application\ Support/containers/podman-desktop/extensions-storage/redhat.ai-lab/models/

# Linux:
ls ~/.local/share/containers/podman-desktop/extensions-storage/redhat.ai-lab/models/
```

### Step 3: Test the Imported Model

Once imported, verify the model works:

1. Go to **AI Lab > Model Services**
2. Click **New Model Service**
3. Select your imported model (`granite-3.3-2b-instruct`)
4. Click **Start**
5. Wait for the service to become ready (status: Running)

Test with curl:

```bash
# The port is shown in the AI Lab Model Services UI
curl http://localhost:<PORT>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "granite-3.3-2b-instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain what GGUF format is in one sentence."}
    ],
    "temperature": 0.7,
    "max_tokens": 100
  }'
```

Then test it interactively in the Playground:

1. Go to **AI Lab > Playground**
2. Select your imported model from the model dropdown
3. Send a test message to verify the model responds correctly

### Step 4: Convert a Fine-Tuned Model to GGUF (If Needed)

If you have a model fine-tuned on RHEL AI (via InstructLab), it will be in SafeTensors format. Convert it to GGUF for use in Podman AI Lab:

```bash
# Clone the llama.cpp repository (contains conversion tools)
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# Install Python dependencies for conversion
pip install -r requirements/requirements-convert_hf_to_gguf.txt

# Convert the model (point to the directory with safetensors files)
python convert_hf_to_gguf.py \
  /path/to/your/finetuned-model/ \
  --outtype q4_k_m \
  --outfile ~/ai-models/my-finetuned-model-Q4_K_M.gguf
```

> **Note:** The conversion requires enough RAM to load the model weights. For a 7B/8B model, expect ~16 GB RAM usage during conversion.

### Step 5: Create a Custom Recipe Catalog

Create a `user-catalog.json` file that adds your custom model and a custom recipe to Podman AI Lab.

```bash
mkdir -p ~/podman-ai-lab-catalog
```

Create the catalog file:

```json
{
  "version": "1.0",
  "models": [
    {
      "id": "granite-3.3-2b-custom",
      "name": "Granite 3.3 2B Instruct (Team Custom)",
      "description": "IBM Granite 3.3 2B Instruct model for our team's use cases",
      "license": "Apache-2.0",
      "url": "https://huggingface.co/lmstudio-community/granite-3.3-2b-instruct-GGUF/resolve/main/granite-3.3-2b-instruct-Q4_K_M.gguf",
      "memory": 2147483648,
      "properties": {
        "chatFormat": "openchat"
      }
    }
  ],
  "recipes": [
    {
      "id": "team-support-bot",
      "name": "Internal Support Bot",
      "description": "AI-powered support bot trained on our internal documentation",
      "categories": ["custom"],
      "repository": "https://github.com/your-org/support-bot-recipe.git",
      "recommended": ["granite-3.3-2b-custom"],
      "basedir": ".",
      "readme": "A custom support bot recipe for internal team use."
    }
  ],
  "categories": [
    {
      "id": "custom",
      "name": "Team Recipes",
      "description": "Custom AI recipes built by our team"
    }
  ]
}
```

> **Key fields explained:**
> - `memory`: estimated RAM usage in bytes (helps AI Lab warn users)
> - `chatFormat`: tells llama.cpp how to format prompts (e.g., `openchat`, `llama3`, `chatml`)
> - `recommended`: which models work best with this recipe
> - `repository`: Git repo containing the recipe application code

To load the custom catalog in Podman AI Lab:

1. Open Podman Desktop > **AI Lab > Settings** (gear icon)
2. Under **User Catalog**, point to your `user-catalog.json` file path
3. The custom models and recipes will appear alongside the built-in catalog

### Step 6: Build a Custom Recipe Application

Create a simple custom recipe: an internal Q&A bot using a Granite model. This recipe will be a Python application using FastAPI and the OpenAI SDK.

```bash
mkdir -p ~/podman-ai-lab-catalog/support-bot
```

Create the application code:

**`app.py`**:

```python
"""Simple Q&A bot recipe for Podman AI Lab."""

import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI

app = FastAPI()

# The model server URL is passed via environment variable by Podman AI Lab
MODEL_ENDPOINT = os.getenv("MODEL_ENDPOINT", "http://localhost:8080/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "granite-3.3-2b-instruct")

client = OpenAI(base_url=MODEL_ENDPOINT, api_key="unused")

SYSTEM_PROMPT = """You are an internal support assistant. Answer questions
about company processes, tools, and procedures. If you don't know the answer,
say so clearly. Be concise and helpful."""


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    user_message = body.get("message", "")

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
        max_tokens=500,
    )
    return {"reply": response.choices[0].message.content}


@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
    <head><title>Support Bot</title></head>
    <body>
      <h1>Internal Support Bot</h1>
      <textarea id="input" rows="3" cols="60" placeholder="Ask a question..."></textarea>
      <br><button onclick="send()">Send</button>
      <pre id="output"></pre>
      <script>
        async function send() {
          const msg = document.getElementById('input').value;
          const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: msg})
          });
          const data = await res.json();
          document.getElementById('output').textContent = data.reply;
        }
      </script>
    </body>
    </html>
    """
```

**`Containerfile`** (UBI-based, as required by Red Hat standards):

```dockerfile
FROM registry.access.redhat.com/ubi9/python-311:latest

WORKDIR /opt/app-root/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8501

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8501"]
```

**`requirements.txt`**:

```
fastapi==0.115.0
uvicorn==0.30.0
openai==1.50.0
```

### Step 7: Build and Test the Recipe Locally

Build and run the recipe container with Podman to verify it works before adding it to the catalog:

```bash
cd ~/podman-ai-lab-catalog/support-bot

# Build the container image
podman build -t support-bot:latest .

# Run the container (assumes a model service is running on port 8080)
podman run -d --name support-bot \
  -p 8501:8501 \
  -e MODEL_ENDPOINT=http://host.containers.internal:<MODEL_SERVICE_PORT>/v1 \
  -e MODEL_NAME=granite-3.3-2b-instruct \
  support-bot:latest
```

> **Note:** Replace `<MODEL_SERVICE_PORT>` with the actual port from your running Podman AI Lab model service. Use `host.containers.internal` to reach the host network from inside the container.

Test it:

```bash
# Check the health of the application
curl http://localhost:8501/

# Send a test question
curl -X POST http://localhost:8501/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I reset my password?"}'
```

Open `http://localhost:8501` in your browser to use the web interface.

### Step 8: Share the Catalog with Your Team

To share the custom catalog across your team:

```bash
# Option 1: Commit to a shared Git repository
cd ~/podman-ai-lab-catalog
git init
git add user-catalog.json support-bot/
git commit -m "Add team custom AI Lab catalog and support bot recipe"
git remote add origin https://github.com/your-org/ai-lab-catalog.git
git push -u origin main

# Option 2: Distribute via shared storage
# Copy user-catalog.json to a shared network drive or S3 bucket
```

Each team member configures their Podman AI Lab to point to the shared catalog file. When someone adds a new model or recipe, the whole team gets it after pulling the latest version.

## Verification

Confirm the following:

| Check | How to verify |
|-------|---------------|
| Custom model imported | AI Lab > Models shows your imported GGUF model |
| Model service runs | AI Lab > Model Services shows status "Running" for your model |
| Model responds | curl to the model service endpoint returns a valid completion |
| Playground works | AI Lab > Playground produces responses with the custom model |
| Custom recipe builds | `podman build` completes without errors |
| Recipe connects to model | curl to the recipe endpoint returns AI-generated responses |
| Catalog loads | AI Lab > Settings shows user catalog loaded, models/recipes visible |

## Key Takeaways

- Podman AI Lab accepts any GGUF-format model -- you are not limited to the built-in catalog. This lets you test community models, different quantizations, or your own fine-tuned models locally before committing to a deployment.
- Fine-tuned models from RHEL AI (SafeTensors format) require conversion to GGUF via `llama.cpp`'s conversion tools before import.
- Custom recipe catalogs (`user-catalog.json`) let teams standardize on a shared set of models and AI applications. This is the "inner loop" equivalent of an enterprise model registry.
- Custom recipes are regular containerized applications that talk to the model server over the OpenAI-compatible API. Use UBI base images for Red Hat ecosystem compatibility.
- Testing recipes locally with Podman before deploying to OpenShift reduces the feedback loop from hours to minutes.

## Cleanup

```bash
# Stop and remove the custom recipe container
podman stop support-bot
podman rm support-bot

# Stop the model service in Podman AI Lab UI:
# AI Lab > Model Services > select your model > Stop

# Remove the custom model from AI Lab (optional):
# AI Lab > Models > select your model > Delete

# Remove downloaded files (optional)
rm -rf ~/ai-models/granite-3.3-2b-instruct-Q4_K_M.gguf
rm -rf ~/podman-ai-lab-catalog
```

## Next Steps

In [L2-M1.2 — Building Applications with Podman AI Lab](../2_building_applications/), you will build a full local AI application stack using the OpenAI-compatible API, integrate a vector database for RAG, and orchestrate everything with Podman Compose.
