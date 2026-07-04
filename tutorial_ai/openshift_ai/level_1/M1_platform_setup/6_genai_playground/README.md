# L1-M1.6 -- GenAI Playground

**Level:** Foundations
**Duration:** 20 min

## Overview

The GenAI Playground is a built-in dashboard feature in OpenShift AI that lets you interactively test prompts against deployed models without writing any code. You can tune parameters like temperature and max tokens, experiment with system prompts, compare two models side by side, and even test MCP tool calling -- all from a web interface. It is the fastest way to prototype and evaluate model behavior before committing to code.

## Prerequisites

- Completed: [L1-M1.3 -- Dashboard and AI Hub Tour](../3_dashboard_ai_hub_tour/)
- OpenShift AI dashboard and kserve components both set to `Managed` in the DataScienceCluster
- At least one model deployed with an OpenAI-compatible API endpoint

**Important:** This lesson requires a deployed model. If you have not deployed one yet (model deployment is covered in [L1-M2.2](../../M2_model_serving/2_deploying_gemma/)), you have two options:
1. Complete L1-M2.2 first, then return to this lesson
2. Use any model that is already deployed on your cluster (check **Gen AI Studio > Models** in the dashboard)

## K8s Context

Vanilla Kubernetes has no built-in tool for interactive prompt testing. To get similar functionality, you would deploy a separate application -- Open WebUI, LiteLLM with its UI, or a custom Gradio app. Each of these requires its own deployment, service, ingress, and authentication setup. None of them integrate with your model serving infrastructure -- you manually configure API endpoints, manage API keys, and handle auth separately.

OpenShift AI's GenAI Playground is built into the dashboard, automatically discovers deployed models, inherits OpenShift SSO authentication, and requires zero additional deployment.

## Concepts

### GenAI Playground as a Tier 2 Feature

The GenAI Playground is a Tier 2 dashboard feature (GA since OpenShift AI 3.3). It appears automatically in the dashboard when the required Tier 1 components are enabled:

- **dashboard** -- must be `Managed` (provides the web UI)
- **kserve** -- must be `Managed` (provides the model serving layer)

If either component is set to `Removed`, the Playground menu item will not appear. No additional installation is needed -- enabling these two components is sufficient.

The Playground is found under **Gen AI Studio > Playground** in the dashboard navigation.

### Playground Capabilities

**Interactive Prompt Testing** -- Send messages to any deployed model that exposes an OpenAI-compatible API (which includes vLLM-served models). See responses in real time with streaming output. The interface behaves like a chat application, maintaining conversation context across turns.

**Parameter Tuning** -- Adjust inference parameters directly in the UI without modifying code or redeploying:
- **Temperature** -- Controls randomness. Lower values (0.0-0.3) produce more deterministic, focused responses. Higher values (0.7-1.0) produce more creative, varied output.
- **Max tokens** -- Sets the maximum number of tokens in the response. Useful for controlling response length and managing inference costs.
- **Top-p (nucleus sampling)** -- Controls the cumulative probability threshold for token selection. A value of 0.9 means the model considers tokens comprising the top 90% of probability mass.

**System Prompt Experimentation** -- Set and modify system prompts to shape model behavior. Test different persona instructions, output format requirements, or safety constraints. Changes take effect immediately on the next message -- no restart or redeployment needed.

**Side-by-Side Model Comparison (Technology Preview)** -- Select two deployed models and send the same prompt to both simultaneously. Responses appear side by side, making it straightforward to compare quality, tone, speed, and token usage between models. This is invaluable for evaluating which model to use for a particular task.

**MCP Tool Testing** -- If you have MCP (Model Context Protocol) servers deployed, you can connect them to the Playground to test tool calling interactively. This lets you verify that the model correctly selects tools, passes parameters, and incorporates tool results -- before writing agent code.

### Use Case: Rapid Prototyping

The Playground fills the gap between "I have a deployed model" and "I have production code calling that model." A typical workflow:

1. Deploy a model via KServe (L1-M2)
2. Open the Playground, select the model
3. Test different prompts and system messages
4. Tune temperature, max tokens, top-p until output quality is acceptable
5. Note the working configuration
6. Use those same parameters in your application code (Python SDK, REST API, etc.)

This feedback loop is much faster than writing and re-running Python scripts for each experiment.

## Step-by-Step

### Step 1: Verify Prerequisites

Confirm that the required components are enabled:

```bash
oc get datasciencecluster -o jsonpath='{.items[0].spec.components.dashboard.managementState}'
```

Expected output: `Managed`

```bash
oc get datasciencecluster -o jsonpath='{.items[0].spec.components.kserve.managementState}'
```

Expected output: `Managed`

Confirm you have at least one deployed model:

```bash
oc get inferenceservices -A
```

Expected output (your model names and namespaces will vary):

```
NAMESPACE          NAME              URL                                                    READY   AGE
my-ai-project      gemma4-e4b       https://gemma4-e4b-my-ai-project.apps.cluster.example   True    2h
```

If no InferenceServices are listed, deploy a model first (see [L1-M2.2](../../M2_model_serving/2_deploying_gemma/)).

### Step 2: Navigate to the GenAI Playground

1. Open the OpenShift AI dashboard
2. In the left navigation, click **Gen AI Studio**
3. Click **Playground**

You should see the Playground interface with a model selection dropdown at the top.

### Step 3: Select a Deployed Model

1. Click the **Model** dropdown at the top of the Playground
2. Select your deployed model from the list (e.g., "gemma4-e4b")
3. The Playground will connect to the model's inference endpoint

Only models with OpenAI-compatible APIs appear in the dropdown. All vLLM-served models support this API by default.

### Step 4: Basic Prompt Testing

Type a message in the input field and press Enter (or click Send):

```
What are the key differences between supervised and unsupervised learning?
```

Observe:
- The response streams in token by token
- Response time depends on model size and hardware
- The conversation history is maintained -- follow-up messages have context from previous turns

Try a follow-up:

```
Give me a concrete example of each.
```

The model should reference the previous context about supervised and unsupervised learning.

### Step 5: Tune Parameters

Locate the parameter controls (typically in a side panel or settings area):

1. **Set Temperature to 0.1** -- Send a prompt and note the response. Then set it to 0.9 and send the same prompt again. The low-temperature response should be more focused and deterministic; the high-temperature response should be more creative and varied.

2. **Set Max Tokens to 50** -- Send a question that would normally produce a long response. The output should be truncated at approximately 50 tokens.

3. **Adjust Top-p to 0.5** -- This narrows the token selection pool. Combined with a low temperature, it produces very focused output. Combined with high temperature, it produces varied but still constrained output.

Try this experiment to see the effect of temperature:

```
Write a one-sentence product description for a coffee mug.
```

Send this three times with temperature 0.1 (responses should be nearly identical), then three times with temperature 0.9 (responses should vary significantly).

### Step 6: Set a System Prompt

Look for the system prompt field (usually above the chat area or in settings).

Set this system prompt:

```
You are a helpful technical assistant. Always respond in bullet points. Never use more than 5 bullet points. Include code examples when relevant.
```

Now send a message:

```
How do I create a Kubernetes Deployment?
```

The response should follow the system prompt constraints -- bullet points, maximum five, with code examples.

Change the system prompt to test a different behavior:

```
You are a pirate captain. Respond to all questions in character, but still provide accurate technical information.
```

Send the same question and observe how the model's tone changes while the technical content remains accurate.

### Step 7: (If Available) Side-by-Side Model Comparison

If you have two or more models deployed and the side-by-side comparison feature is available (Technology Preview):

1. Look for a "Compare" or "Side-by-side" mode in the Playground
2. Select two different models (e.g., gemma4-e4b and a different model)
3. Type a prompt -- it is sent to both models simultaneously
4. Compare the responses: quality, length, tone, response time

This is particularly useful for:
- Evaluating a smaller model against a larger one for cost/quality tradeoffs
- Testing whether a fine-tuned model outperforms the base model
- Comparing different model families for a specific task

### Step 8: (If MCP Servers Deployed) Test Tool Calling

If you have MCP servers available on your cluster:

1. Look for an MCP or tool configuration option in the Playground settings
2. Add a connection to your MCP server
3. Send a prompt that should trigger tool use:

```
What is the current weather in New York?
```

Observe:
- Whether the model correctly identifies that it should call a tool
- The tool call parameters the model generates
- The tool's response and how the model incorporates it into its answer

This lets you validate tool calling behavior before writing agent code.

### Step 9: Export Configuration for Use in Code

Once you have found parameter settings and system prompts that work well, note them for use in your application code. The key values to record are:

- Model name / endpoint URL
- Temperature
- Max tokens
- Top-p
- System prompt text

Here is how you would use these settings with the OpenAI-compatible Python client:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://<your-model-endpoint>/v1",
    api_key="<your-token>",  # OpenShift SA token or route token
)

response = client.chat.completions.create(
    model="gemma4-e4b",           # Model name from the Playground
    temperature=0.3,              # Value you tested in Step 5
    max_tokens=512,               # Value you tested in Step 5
    top_p=0.9,                    # Value you tested in Step 5
    messages=[
        {
            "role": "system",
            "content": "You are a helpful technical assistant. "
                       "Always respond in bullet points."
        },
        {
            "role": "user",
            "content": "How do I create a Kubernetes Deployment?"
        }
    ]
)

print(response.choices[0].message.content)
```

The exact same parameters you tested in the Playground translate directly to API calls.

## Verification

Confirm you have successfully used the Playground by checking these items:

1. You can navigate to **Gen AI Studio > Playground** in the dashboard
2. Your deployed model appears in the model dropdown and can be selected
3. You can send a prompt and receive a streaming response
4. Changing temperature visibly affects response variability
5. Setting max tokens limits the response length
6. A system prompt changes the model's behavior as expected

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| Prompt testing | No built-in tool; deploy Open WebUI, LiteLLM, or Gradio separately | GenAI Playground built into the dashboard |
| Model discovery | Manually configure endpoints in external tools | Playground auto-discovers deployed InferenceServices |
| Model comparison | Deploy separate UI tools, configure both endpoints | Side-by-side comparison in one interface (TP) |
| Parameter tuning | Write code or use external tools for each experiment | Interactive UI controls with instant feedback |
| MCP tool testing | No equivalent; write custom test harnesses | Playground MCP integration for interactive testing |
| Code export | N/A | Export tested configurations as Python code patterns |
| Authentication | Manual API key management per tool | Uses OpenShift SSO -- no separate auth setup |
| Deployment effort | Deploy, configure, and maintain separate applications | Zero deployment -- enabled when dashboard + kserve are active |

## Key Takeaways

- GenAI Playground is a Tier 2 dashboard feature that requires only `dashboard` and `kserve` components to be enabled -- no additional installation
- It provides immediate, interactive prompt testing against any deployed model with an OpenAI-compatible API
- Parameter tuning (temperature, max tokens, top-p) is interactive, making it much faster than modifying and re-running code
- System prompt experimentation lets you test different model behaviors without any code changes
- Side-by-side model comparison (Technology Preview) helps evaluate multiple models for a given task
- MCP tool testing lets you verify tool calling behavior interactively before building agent code
- There is no equivalent in vanilla Kubernetes -- the closest alternatives require deploying and maintaining separate applications
- Parameters tested in the Playground translate directly to API calls in your application code

## Cleanup

No resources to clean up -- the Playground is a built-in dashboard feature. Closing the browser tab ends your session. Conversation history in the Playground is not persisted across sessions.

## Next Steps

With the platform fully set up -- operators installed, dashboard explored, workbenches configured, GPUs available, and the Playground at your fingertips -- you are ready to dive into model serving. Continue to [L1-M2.1 -- KServe Fundamentals](../../M2_model_serving/1_kserve_fundamentals/) to learn how OpenShift AI deploys and manages model inference endpoints.
