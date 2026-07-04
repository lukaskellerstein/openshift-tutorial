# L2-M2.5 — Testing MCP in GenAI Playground

**Level:** Practitioner
**Duration:** 20 min

## Overview

Before deploying an agent that uses MCP tools in production, you want to verify that the tools work correctly with your model. The GenAI Playground in OpenShift AI provides an interactive UI for exactly this --- you can connect MCP servers, test tool calling with a deployed model, and export working configurations as Python code templates. This lesson walks through testing the MCP servers deployed in the previous lessons using the Playground.

## Prerequisites

- Completed: L2-M2.2 (ShopInsights MCP server deployed)
- Completed: L2-M2.3 (OpenShift MCP Server deployed) --- optional, but recommended
- A model deployed with tool calling enabled (from L1-M2):
  - The `ServingRuntime` must include `--enable-auto-tool-choice` and `--tool-call-parser hermes`
- OpenShift AI dashboard accessible
- Cluster-admin access (to create the MCP servers ConfigMap in `redhat-ods-applications`)

## Concepts

### GenAI Playground and MCP

The GenAI Playground is a web-based chat interface in the OpenShift AI dashboard (Gen AI Studio section). It is powered by LlamaStack under the hood, which handles MCP server connections and routes tool calls.

The Playground settings panel has four tabs:

| Tab | Purpose |
|-----|---------|
| **Model** | Select the deployed model, adjust temperature and other parameters |
| **Prompt** | Write and save system instructions (persisted in MLflow) |
| **Knowledge** | Upload documents for RAG or connect a vector store |
| **MCP** | Connect to MCP servers, toggle individual tools on/off |

The MCP tab shows registered MCP servers with toggle switches. When you enable a server and send a chat message, the Playground includes the MCP tools in the request to the model. If the model decides to call a tool, LlamaStack routes the call to the MCP server, gets the result, and feeds it back to the model for a final response.

### Registering MCP Servers with the Playground

There are two ways to register MCP servers with the Playground:

**Method 1: ConfigMap (3.0+)**

A cluster administrator creates a ConfigMap named `gen-ai-aa-mcp-servers` in the `redhat-ods-applications` namespace. Each key is the display name; each value is JSON with `url` and `description`.

**Method 2: MCP Catalog (3.4+, Dev Preview)**

If the MCP Catalog is enabled, servers deployed via the MCP Lifecycle Operator automatically appear in the Playground.

### Model Requirements for Tool Calling

Not all models support tool calling. The model must:

1. Be trained to generate structured tool call outputs
2. Be served with tool calling enabled in vLLM:
   - `--enable-auto-tool-choice` --- allows the model to autonomously generate tool calls
   - `--tool-call-parser hermes` --- parser for extracting tool calls from model output

Without these flags, vLLM returns 400 errors when tools are passed in the request.

Models known to support tool calling include: Llama 3.1+ Instruct, Qwen3, IBM Granite3, Mistral, and Gemma models with tool calling support.

## Step-by-Step

### Step 1: Verify Tool Calling is Enabled on the Model

Check that your deployed model's `ServingRuntime` includes the tool calling flags:

```bash
# Check the current ServingRuntime args
oc get servingruntime -o yaml | grep -A 5 "enable-auto-tool-choice"
```

If not enabled, update the `ServingRuntime` to add the flags:

```bash
# Example: patch the serving runtime to enable tool calling
# Adjust the runtime name to match your deployment
oc edit servingruntime <your-runtime-name>

# Add these args to the container command:
#   --enable-auto-tool-choice
#   --tool-call-parser hermes
```

After updating, wait for the model pod to restart:

```bash
oc get pods -l serving.kserve.io/inferenceservice=<model-name> -w
```

### Step 2: Register MCP Servers with the Playground

Apply the ConfigMap that registers your MCP servers:

```bash
# This requires cluster-admin access (the ConfigMap goes in redhat-ods-applications)
oc apply -f manifests/mcp-servers-configmap.yaml
```

The ConfigMap registers two servers:

```yaml
data:
  ShopInsights: |
    {
      "url": "http://shopinsights-mcp.mcp-servers.svc.cluster.local:8080/mcp",
      "description": "Product catalog and order analytics tools for ShopInsights."
    }
  OpenShift-Resources: |
    {
      "url": "http://openshift-mcp-server.mcp-servers.svc.cluster.local:8080/mcp",
      "description": "Read-only access to Kubernetes and OpenShift cluster resources."
    }
```

> **Note:** The ConfigMap uses cluster-internal URLs (Service DNS). The Playground runs inside the cluster, so it can reach these services directly.

### Step 3: Open the GenAI Playground

1. Navigate to the OpenShift AI Dashboard
2. In the left sidebar, click **Gen AI Studio**
3. Click **Playground**

### Step 4: Configure the Model

In the Playground settings panel (left side):

1. Click the **Model** tab
2. Select your deployed model (e.g., Gemma4-e4b)
3. Adjust parameters if desired:
   - **Temperature:** 0.7 (default, good for general use)
   - **Max tokens:** 1024
   - **Streaming:** enabled (for real-time response display)

### Step 5: Enable MCP Servers

1. Click the **MCP** tab in the settings panel
2. You should see the registered MCP servers:
   - **ShopInsights** --- toggle switch
   - **OpenShift-Resources** --- toggle switch
3. Toggle **ShopInsights** to **enabled**
4. If authentication is required, click the **Authorize** button and enter your access token
5. Click **View tools** to see the available tools:
   - `get_product_info`
   - `list_products`
   - `get_order_summary`
   - `get_low_stock_alerts`

### Step 6: Test Tool Calling

Try these prompts in the chat to trigger tool calls:

**Test 1: Product query**
```
What electronics products do you have available?
```

Expected behavior:
- The model calls the `list_products` tool with `category: "Electronics"`
- The tool returns product data
- The model formats the response in natural language

**Test 2: Order summary**
```
Give me a summary of orders from the last 7 days.
```

Expected behavior:
- The model calls `get_order_summary` with `days: 7`
- The tool returns order statistics
- The model presents total orders, revenue, and status breakdown

**Test 3: Stock alerts**
```
Are there any products running low on stock?
```

Expected behavior:
- The model calls `get_low_stock_alerts` with a default threshold
- The tool returns products below the threshold
- The model lists the affected products

**Test 4: Multi-tool query**
```
What is the price of PROD-005 and do we have enough in stock?
```

Expected behavior:
- The model calls `get_product_info` with `product_id: "PROD-005"`
- Depending on the result, it may also call `get_low_stock_alerts`
- The model combines the information in its response

### Step 7: Test with OpenShift Resource Tools (Optional)

1. In the **MCP** tab, toggle **OpenShift-Resources** to enabled
2. Try these prompts:

```
What projects exist on the cluster?
```

```
List the pods in the mcp-servers namespace.
```

> **Security note:** Be mindful of what cluster information you expose through the Playground. The OpenShift MCP Server is configured read-only, but users can still see resource names, statuses, and metadata.

### Step 8: Iterate on Tool Descriptions

If the model is not selecting the right tools, improve the tool descriptions in your MCP server code:

1. In the chat, observe which tools the model selects (or fails to select)
2. Update the tool descriptions in `mcp_server.py`:
   - Be specific about what the tool does
   - Include example inputs in the description
   - Clarify when the tool should (and should not) be used
3. Restart the MCP server pod to pick up changes
4. Test again in the Playground

Good tool descriptions are critical for reliable tool calling. The Playground provides a fast feedback loop for this iteration.

### Step 9: Export Code Template

Once your MCP tools work correctly in the Playground:

1. Click the **View code** button in the Playground toolbar
2. A dialog displays a Python code template showing your configuration:
   - Model endpoint URL
   - System prompt
   - MCP server connections
   - Tool definitions
3. Click **Copy code** to paste into your IDE or notebook

> **Note:** The exported code is a starting point, not a production-ready script. See `scripts/exported_template.py` for an example of what the exported code looks like and how to adapt it for production use.

The template in `scripts/exported_template.py` shows the key pattern:
1. Discover tools from the MCP server
2. Convert MCP tools to OpenAI function calling format
3. Send user messages to the LLM with tools available
4. Execute tool calls via MCP when the LLM requests them
5. Send tool results back to the LLM for the final response

## Verification

Confirm the Playground integration is working:

- [ ] MCP servers appear in the Playground's MCP tab
- [ ] Toggling a server enables/disables its tools
- [ ] Chat messages trigger appropriate tool calls
- [ ] Tool results are incorporated into the model's responses
- [ ] The View code button generates a usable Python template
- [ ] Disabling a tool prevents the model from calling it

## Key Takeaways

- The GenAI Playground provides an **interactive feedback loop** for testing MCP tools with a deployed model before writing agent code. This is faster than the code-deploy-test cycle.
- MCP servers are registered via a **ConfigMap** (`gen-ai-aa-mcp-servers`) in the `redhat-ods-applications` namespace, or via the MCP Catalog (3.4+). After registration, they appear in the Playground's MCP tab with toggle switches.
- The model must be served with **`--enable-auto-tool-choice`** and **`--tool-call-parser hermes`** for tool calling to work. Without these flags, tool requests fail.
- **Tool descriptions are the most important factor** in reliable tool calling. Use the Playground to iterate on descriptions until the model consistently selects the right tools.
- The **View code** export generates a Python template that captures your model, prompt, and MCP configuration --- use it as a starting point for production agent code.
- The Playground is **Technology Preview** in OpenShift AI 3.4. Use it for development and testing, not as a production chat interface.

## Cleanup

```bash
# Remove the MCP servers ConfigMap
oc delete configmap gen-ai-aa-mcp-servers -n redhat-ods-applications
```

If you want to clean up all M2 resources:

```bash
# Delete everything from this module
oc delete all,configmap,serviceaccount,clusterrolebinding,mcpserver,mcpgwe,mcpsr,authpolicy \
  -l tutorial-module=M2 -n mcp-servers

# Delete the project
# oc delete project mcp-servers
```

## Next Steps

You now have a complete MCP infrastructure on OpenShift AI: custom servers deployed via the Lifecycle Operator, federated behind a Gateway with authentication, and tested in the Playground.

Continue to [L2-M3.1 --- Agent Deployment Patterns on OpenShift AI](../../M3_agent_deployment/1_deployment_patterns/) to learn how to build and deploy AI agents that use these MCP tools in production.
