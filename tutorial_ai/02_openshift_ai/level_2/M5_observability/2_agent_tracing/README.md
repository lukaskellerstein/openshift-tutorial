# L2-M5.2 -- Agent Tracing with MLflow

**Level:** Practitioner
**Duration:** 1 hour

## Overview

When an AI agent calls an LLM, selects a tool, retrieves documents, and synthesizes a response, you need to see exactly what happened at each step -- which tool was invoked, how long retrieval took, what the LLM received as input, and where errors occurred. MLflow Tracing provides this visibility by recording the full execution graph of an agent as a hierarchy of spans, viewable in the MLflow UI.

In the previous lesson you deployed MLflow on OpenShift AI. In this lesson you will instrument a LangGraph agent with both automatic and manual tracing, view the resulting traces in the MLflow UI, and use the trace data to identify performance bottlenecks and errors across the agent's execution flow.

## Prerequisites

- Completed: [L2-M5.1 -- MLflow on OpenShift AI](../1_mlflow_openshift_ai/) -- MLflow tracking server running in the `ai-tutorial` project
- A vLLM InferenceService running (deployed in Level 1)
- Familiarity with LangChain/LangGraph agent concepts (covered in [L2-M3.1](../../M3_agent_deployment/1_deployment_patterns/) and [L2-M3.2](../../M3_agent_deployment/2_langchain_langgraph/))
- Python 3.11+ with `pip` available locally or in a workbench

## Concepts

### Traces, Spans, and the Execution Graph

MLflow Tracing borrows its terminology from distributed tracing systems like OpenTelemetry and Jaeger. The core abstraction is a **trace** -- a tree of **spans** that records the full execution of a request through your agent.

```
Trace (root)
├── Span: LangGraph Agent Loop
│   ├── Span: LLM Call #1 (tool selection)
│   │   ├── input: messages, tools schema
│   │   └── output: tool_call(search_products, {"query": "laptops"})
│   ├── Span: Tool Call -- search_products
│   │   ├── input: {"query": "laptops"}
│   │   └── output: [{"name": "ThinkPad X1", "price": 1299.99, ...}]
│   ├── Span: LLM Call #2 (tool selection)
│   │   └── output: tool_call(calculate_metric, {"expression": "1299.99 * 42"})
│   ├── Span: Tool Call -- calculate_metric
│   │   └── output: {"result": 54599.58}
│   └── Span: LLM Call #3 (final response)
│       └── output: "The total inventory value for ThinkPad X1 is $54,599.58"
```

Each span records:

| Field | Description |
|-------|-------------|
| **Name** | What this span represents (e.g. `ChatOpenAI`, `search_products`) |
| **Span type** | Category: `LLM`, `TOOL`, `CHAIN`, `RETRIEVER`, `FUNCTION` |
| **Inputs** | The data passed into this step |
| **Outputs** | The data returned from this step |
| **Start/end time** | Wall-clock timestamps for latency measurement |
| **Status** | `OK` or `ERROR` (with exception details) |
| **Attributes** | Key-value metadata (token counts, model name, temperature) |

The trace viewer in the MLflow UI renders this tree as a waterfall diagram, making it easy to see which steps took the most time and where errors occurred.

### Auto-Tracing vs Manual Tracing

MLflow provides two complementary tracing mechanisms:

**Auto-tracing** (`mlflow.langchain.autolog()`) instruments LangChain and LangGraph automatically. A single function call at startup captures every LLM call, tool invocation, and chain step without modifying your agent code. This is the right starting point -- it covers the common cases with zero effort.

What autolog captures automatically:

- `ChatOpenAI` / `ChatOllama` calls -- inputs (messages, tools), outputs (response, token usage)
- LangGraph node executions -- each node in the graph becomes a span
- Tool calls -- the tool name, inputs, and outputs
- Chain compositions -- `prompt | llm | parser` pipelines
- Retriever calls -- query and retrieved documents

**Manual tracing** fills the gaps that autolog cannot see. Your custom business logic, preprocessing functions, MCP tool server calls, and external API integrations are invisible to autolog because they are not LangChain components. Manual tracing instruments these with two mechanisms:

1. **`@mlflow.trace` decorator** -- wrap a function to automatically create a span each time it is called. Best for standalone functions.

2. **`mlflow.start_span()` context manager** -- create a span for a block of code. Best for inline logic where you want fine-grained control over span boundaries, especially when decomposing a pipeline into phases (e.g., retrieval vs generation in a RAG pipeline).

**When to use each:**

| Scenario | Mechanism |
|----------|-----------|
| Instrument all LangChain/LangGraph components | `mlflow.langchain.autolog()` |
| Trace a custom function (preprocessing, postprocessing) | `@mlflow.trace` decorator |
| Trace a code block within a larger function | `mlflow.start_span()` |
| Trace MCP tool server HTTP calls | `mlflow.start_span()` around the HTTP request |
| Decompose RAG into retrieval + generation latency | Nested `mlflow.start_span()` calls |

### Tracing MCP Tool Calls

When your agent calls an MCP tool server over HTTP, the network round-trip and server-side processing time are invisible to LangChain autolog. The autolog sees the LangChain `Tool` wrapper, but not the underlying HTTP call to the MCP server.

To get full visibility, wrap the MCP call with `mlflow.start_span()`:

```python
with mlflow.start_span(name="mcp_tool:inventory_lookup", span_type="TOOL") as span:
    span.set_inputs({"product_id": "SKU-001"})
    
    # The actual MCP server HTTP call
    response = requests.post(
        "http://mcp-inventory:8080/invoke",
        json={"tool": "inventory_lookup", "args": {"product_id": "SKU-001"}},
    )
    result = response.json()
    
    span.set_outputs(result)
```

This creates a dedicated span for the MCP call, showing the exact latency of the external tool invocation separately from the LangChain tool wrapper overhead.

### RAG Trace Decomposition

For RAG pipelines, the most important performance question is: how much time is spent on retrieval vs generation? By wrapping each phase in its own span, the trace viewer shows this breakdown visually:

```python
with mlflow.start_span(name="rag_pipeline", span_type="CHAIN") as parent:
    with mlflow.start_span(name="retrieval", span_type="RETRIEVER") as ret_span:
        # Embed query, search vector DB
        ret_span.set_outputs({"num_docs": len(docs), "retrieval_ms": 42})

    with mlflow.start_span(name="generation", span_type="LLM") as gen_span:
        # Build augmented prompt, call LLM
        gen_span.set_outputs({"tokens": 350, "generation_ms": 890})
```

The `RETRIEVER` and `LLM` span types are recognized by MLflow and rendered with distinct icons in the trace viewer, making it easy to scan a list of traces and spot retrieval-heavy vs generation-heavy requests.

### Using Trace Data for Optimization

Traces are not just for debugging -- they are a performance analysis tool. Once you have traces flowing into MLflow, you can answer questions like:

- **Which tool calls are slowest?** Sort spans by duration to find bottlenecks. If `search_products` consistently takes 500ms while `calculate_metric` takes 10ms, focus optimization on the search tool.
- **How many LLM calls does the agent make per request?** Count `LLM` spans per trace. An agent making 5+ LLM calls per simple query may need a better system prompt or tool schema.
- **What is the retrieval-to-generation latency ratio?** If retrieval is 80% of total time, consider caching embeddings or adding an index. If generation dominates, consider a smaller/faster model.
- **Where do errors occur?** Filter traces by `ERROR` status. The span tree shows exactly which step failed and what inputs triggered the failure.
- **How many tokens is the agent consuming?** LLM spans include token counts in their attributes. Sum across traces to estimate cost.

## Step-by-Step

### Step 1: Install Python Dependencies

Install the required packages in your local environment or workbench:

```bash
pip install mlflow langchain-openai langgraph
```

If you plan to run in mock mode (no live LLM), you still need all three packages -- the mock mode skips LLM calls but still uses LangChain and MLflow tracing APIs.

### Step 2: Set Environment Variables

Retrieve the MLflow tracking server URL and vLLM endpoint:

```bash
# MLflow tracking URI (deployed in L2-M5.1)
export MLFLOW_TRACKING_URI="https://$(oc get route mlflow-tracking -n ai-tutorial -o jsonpath='{.spec.host}')"
echo "MLflow URI: $MLFLOW_TRACKING_URI"

# vLLM endpoint (deployed in Level 1)
export VLLM_ENDPOINT="https://$(oc get route -l serving.kserve.io/inferenceservice -n ai-tutorial -o jsonpath='{.items[0].spec.host}')/v1"
export VLLM_MODEL_NAME="granite-3.3-8b-instruct"
echo "vLLM endpoint: $VLLM_ENDPOINT"

# Experiment name for this lesson
export MLFLOW_EXPERIMENT_NAME="agent-tracing-demo"
```

If you do not have a live vLLM endpoint, enable mock mode:

```bash
export MOCK_LLM=true
```

Mock mode skips the agent invocation demo (Demo 1) but runs all manual tracing demos (Demos 2-4), producing real traces in MLflow.

### Step 3: Review the Traced Agent Script

The script at `scripts/traced_agent.py` demonstrates four tracing patterns. Open it and review the key sections before running it.

**Auto-tracing setup** -- a single call that instruments all LangChain components:

```python
mlflow.langchain.autolog(
    log_models=False,          # Do not log serialized model artifacts
    log_input_examples=True,   # Record inputs to each span
    log_model_signatures=True, # Record input/output schemas
)
```

**Agent definition** -- a LangGraph ReAct agent with two tools:

```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

llm = ChatOpenAI(
    base_url=VLLM_ENDPOINT,
    api_key="EMPTY",
    model=VLLM_MODEL_NAME,
    temperature=0,
)

agent_executor = create_react_agent(
    llm,
    tools=[search_products, calculate_metric],
)
```

**Manual tracing with `@mlflow.trace`** -- decorates a preprocessing function:

```python
@mlflow.trace(name="custom_data_preprocessing", span_type="FUNCTION")
def preprocess_query(raw_query: str) -> dict:
    cleaned = raw_query.strip().lower()
    tokens = cleaned.split()
    keywords = [t for t in tokens if len(t) > 3]
    return {"cleaned": cleaned, "token_count": len(tokens), "keywords": keywords}
```

**Span-level tracing with `mlflow.start_span()`** -- decomposes a RAG pipeline:

```python
with mlflow.start_span(name="rag_pipeline", span_type="CHAIN") as parent:
    with mlflow.start_span(name="retrieval", span_type="RETRIEVER") as ret_span:
        # Embed query, search vector DB, return documents
        ret_span.set_outputs({"num_documents": len(docs)})

    with mlflow.start_span(name="generation", span_type="LLM") as gen_span:
        # Build augmented prompt, call LLM, return answer
        gen_span.set_outputs({"answer_length": len(answer)})
```

**MCP tool call wrapping** -- traces an external tool invocation:

```python
with mlflow.start_span(name="mcp_tool_call:inventory_lookup", span_type="TOOL") as span:
    span.set_inputs({"tool_name": "inventory_lookup", "tool_input": args})
    result = call_mcp_server(args)  # HTTP call to MCP server
    span.set_outputs({"response": result, "call_duration_ms": duration})
```

### Step 4: Run the Traced Agent

Run the script:

```bash
python3 scripts/traced_agent.py
```

Expected output (with `MOCK_LLM=false` and a live vLLM endpoint):

```
Configuring MLflow...
  Tracking URI:    https://mlflow-tracking-ai-tutorial.apps.<cluster>
  Experiment:      agent-tracing-demo
  Mock LLM mode:   False
  LangChain autolog enabled

  Connecting to vLLM: https://<vllm-route>/v1
  Model: granite-3.3-8b-instruct
  ReAct agent created with tools: search_products, calculate_metric

======================================================================
DEMO 1: Agent with auto-tracing (mlflow.langchain.autolog)
======================================================================

Query: Search for laptops in stock and calculate the total inventory value

Agent response:
  The total inventory value for laptops is $54,599.58 (ThinkPad X1 Carbon:
  42 units x $1,299.99) plus $30,772.00 (MacBook Air M3: 28 units x $1,099.00)...

Trace ID: abc123def456...

======================================================================
DEMO 2: Manual tracing with @mlflow.trace decorator
======================================================================

Query: What are the best-selling headphones in Q2?

Preprocessed query:
  Original:    What are the best-selling headphones in Q2?
  Cleaned:     what are the best-selling headphones in q2?
  Token count: 8
  Keywords:    ['best-selling', 'headphones']

Trace ID: ghi789jkl012...

======================================================================
DEMO 3: RAG pipeline with retrieval/generation span decomposition
======================================================================

Query: What was the revenue growth in Q2?

Answer: Based on the available data: Total revenue for Q2 was $2.4M, up
  15% from Q1. Laptop sales grew 22%... (Synthesized from 2 retrieved documents.)

Sources:
  - Q2 Sales Report (doc-001)
  - Customer Satisfaction Survey (doc-003)

Latency breakdown:
  Retrieval:  41.2 ms
  Generation: 103.5 ms
  Total:      144.7 ms

Trace ID: mno345pqr678...

======================================================================
DEMO 4: MCP tool call tracing with mlflow.start_span()
======================================================================

  Calling MCP tool: inventory_lookup
    Input: {'product_id': 'SKU-001', 'warehouse': 'us-east'}
    Status: success
    Duration: 82.1 ms

  Calling MCP tool: price_check
    Input: {'product_id': 'SKU-001', 'currency': 'USD'}
    Status: success
    Duration: 81.4 ms

Trace ID: stu901vwx234...

======================================================================
TRACE SUMMARY
======================================================================

MLflow Tracking URI: https://mlflow-tracking-ai-tutorial.apps.<cluster>
Experiment: agent-tracing-demo

Traces generated:

  Demo 1: Agent auto-tracing:
    Trace ID: abc123def456...
    View in UI: https://mlflow-tracking-ai-tutorial.apps.<cluster>/#/experiments/1/traces/abc123def456...

  Demo 2: @mlflow.trace decorator:
    Trace ID: ghi789jkl012...
  ...
```

If you are running in mock mode (`MOCK_LLM=true`), Demo 1 is skipped and the output begins at Demo 2. Demos 2-4 produce real traces in MLflow regardless of mock mode.

### Step 5: View Traces in the MLflow UI

Open the MLflow UI in your browser:

```bash
# Get the MLflow UI URL
echo "https://$(oc get route mlflow-tracking -n ai-tutorial -o jsonpath='{.spec.host}')"
```

Navigate to the `agent-tracing-demo` experiment and click the **Traces** tab. You will see a list of traces generated by the script.

**Trace list view:**

The trace list shows each trace as a row with:
- **Trace ID** -- unique identifier
- **Timestamp** -- when the trace was created
- **Status** -- `OK` or `ERROR`
- **Latency** -- total duration of the trace
- **Number of spans** -- how many spans the trace contains

Click on any trace to open the **trace detail view**.

**Trace detail view -- the waterfall diagram:**

The trace detail view shows the span tree as a waterfall diagram. Each span is a horizontal bar whose length represents its duration. Spans are nested to show parent-child relationships.

For the agent auto-tracing trace (Demo 1), the waterfall looks like:

```
AgentExecutor                     |████████████████████████████████████|  2.3s
  ├── ChatOpenAI (call #1)        |██████████|                          0.8s
  ├── search_products             |  ██|                                0.1s
  ├── ChatOpenAI (call #2)        |      ████████|                      0.7s
  ├── calculate_metric            |              █|                     0.05s
  └── ChatOpenAI (call #3)        |                ████████████|        0.6s
```

For the RAG pipeline trace (Demo 3), the waterfall clearly separates retrieval from generation:

```
rag_pipeline (CHAIN)              |████████████████████████████████████|  145ms
  ├── retrieval (RETRIEVER)       |████████|                             41ms
  └── generation (LLM)            |          ████████████████████████|   104ms
```

**Inspecting span details:**

Click on any span to see its details in the right panel:
- **Inputs** -- the exact data passed into this step (e.g., the messages sent to the LLM, the tool arguments)
- **Outputs** -- the data returned (e.g., the LLM response, tool results)
- **Attributes** -- metadata like `model_name`, `temperature`, `token_usage.prompt_tokens`, `token_usage.completion_tokens`
- **Events** -- any logged events during the span's lifetime

For LLM spans, the inputs include the full message array (system prompt, user message, tool results) and the outputs include the model's response with token counts. This is invaluable for debugging unexpected agent behavior -- you can see exactly what the model received and what it produced at each step.

### Step 6: Analyze Performance from Trace Data

With traces in MLflow, you can answer key performance questions.

**Find the slowest spans across all traces:**

In the MLflow UI, use the trace search functionality to filter and sort traces. From the trace list, click on traces with high latency values to identify which spans contribute most to the total duration.

**Compare retrieval vs generation latency:**

Open the Demo 3 traces and compare the `retrieval` and `generation` span durations. In a real RAG system, this breakdown reveals whether your bottleneck is in the vector database (retrieval) or the LLM (generation).

**Count LLM calls per agent invocation:**

In the Demo 1 trace, count the number of `ChatOpenAI` spans. Each span represents one LLM call. A well-designed agent should solve most queries in 2-3 LLM calls. If you see 5+ calls, the agent may be looping or the tool schema may be ambiguous.

**Identify failed spans:**

If any span has an `ERROR` status, click on it to see the exception details. Common issues include:
- LLM timeout -- the vLLM endpoint took too long to respond
- Tool execution failure -- a tool raised an exception
- Invalid tool arguments -- the LLM generated malformed tool call arguments

**Programmatic trace analysis:**

You can also query trace data programmatically using the MLflow client:

```python
import mlflow

client = mlflow.MlflowClient()

# Search for all traces in the experiment
experiment = client.get_experiment_by_name("agent-tracing-demo")
traces = client.search_traces(
    experiment_ids=[experiment.experiment_id],
)

for trace in traces:
    print(f"Trace: {trace.info.request_id}")
    print(f"  Status: {trace.info.status}")
    print(f"  Duration: {trace.info.execution_time_millis} ms")
    print(f"  Num spans: {len(trace.data.spans)}")

    for span in trace.data.spans:
        print(f"    {span.name} ({span.span_type}): "
              f"{span.end_time_ns - span.start_time_ns:.0f} ns")
```

### Step 7: Add Tracing to Your Own Agent

To instrument your own LangGraph agent with MLflow tracing, follow this checklist:

**1. Enable autologging at startup:**

```python
import mlflow
import mlflow.langchain

mlflow.set_tracking_uri("https://mlflow-tracking-ai-tutorial.apps.<cluster>")
mlflow.set_experiment("my-agent")
mlflow.langchain.autolog()
```

This single block covers all LangChain/LangGraph components automatically.

**2. Add `@mlflow.trace` to custom functions:**

```python
@mlflow.trace(name="my_preprocessing", span_type="FUNCTION")
def my_custom_function(data):
    # Your logic here
    return result
```

**3. Wrap external calls with `mlflow.start_span()`:**

```python
with mlflow.start_span(name="external_api_call", span_type="TOOL") as span:
    span.set_inputs({"url": url, "payload": payload})
    response = requests.post(url, json=payload)
    span.set_outputs({"status": response.status_code, "body": response.json()})
```

**4. Decompose RAG pipelines:**

```python
with mlflow.start_span(name="rag", span_type="CHAIN"):
    with mlflow.start_span(name="embed_and_retrieve", span_type="RETRIEVER"):
        docs = vector_store.similarity_search(query, k=5)
    with mlflow.start_span(name="generate", span_type="LLM"):
        answer = llm.invoke(build_prompt(query, docs))
```

## Verification

Run through this checklist to confirm the lesson is complete:

1. The traced agent script ran successfully and produced trace IDs:

```bash
# Re-run if needed to verify
python3 scripts/traced_agent.py
```

2. Traces are visible in the MLflow UI:

```bash
# Open the MLflow UI
echo "https://$(oc get route mlflow-tracking -n ai-tutorial -o jsonpath='{.spec.host}')"
```

Navigate to the `agent-tracing-demo` experiment and confirm the **Traces** tab shows entries.

3. The trace detail view displays the span tree with inputs and outputs for each span.

4. You can identify the following in the traces:
   - Demo 1 (if run with a live LLM): multiple `ChatOpenAI` spans and `Tool` spans nested under the agent executor
   - Demo 2: a single `custom_data_preprocessing` span with the preprocessed query as output
   - Demo 3: a `rag_pipeline` span containing `retrieval` and `generation` child spans with latency data
   - Demo 4: an `agent_tool_calling_loop` span containing `mcp_tool_call:inventory_lookup` and `mcp_tool_call:price_check` child spans

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| Tracing infrastructure | Deploy Jaeger/Zipkin yourself, configure OpenTelemetry collectors | MLflow Tracing built into the AI platform; deploy MLflow server via operator or manual deployment |
| LLM call tracing | No built-in support -- instrument manually with OpenTelemetry spans | `mlflow.langchain.autolog()` captures all LangChain/LangGraph LLM calls automatically |
| Agent execution tracing | Build custom instrumentation for each agent framework | Auto-tracing instruments LangGraph agent loops, tool calls, and chain steps with one line |
| Trace storage | Set up a trace backend (Jaeger, Tempo, Elasticsearch) | MLflow stores traces alongside experiments and runs -- single UI for metrics, models, and traces |
| RAG pipeline visibility | Custom instrumentation required to separate retrieval from generation | `mlflow.start_span()` with `RETRIEVER` and `LLM` span types, rendered with distinct icons |
| Tool call visibility | Generic HTTP span from OpenTelemetry | Named spans with tool inputs/outputs, queryable from the MLflow API |
| Trace analysis | Query Jaeger API or Grafana Tempo | MLflow Python client `search_traces()` + built-in UI filtering and sorting |

## Key Takeaways

- `mlflow.langchain.autolog()` is a single line that instruments all LangChain and LangGraph components -- LLM calls, tool invocations, chain steps, and agent loops are captured as spans automatically
- Auto-tracing covers framework-managed components; manual tracing with `@mlflow.trace` and `mlflow.start_span()` covers custom logic, MCP tool calls, and external API integrations that autolog cannot see
- The trace hierarchy (Trace > Span > Child Span) mirrors the agent's execution flow, making it possible to see exactly which step took the most time or produced an error
- RAG pipelines benefit from explicit span decomposition -- separating retrieval latency from generation latency reveals whether the bottleneck is in the vector database or the LLM
- MCP tool calls should be wrapped in their own spans so that network round-trip time to the tool server is visible independently of the LangChain tool wrapper
- Trace data enables performance optimization: identifying slow tools, counting LLM calls per request, measuring token consumption, and detecting error patterns across agent invocations

## Cleanup

If you want to remove the traces created in this lesson, delete the experiment from the MLflow UI:

1. Open the MLflow UI.
2. Navigate to the `agent-tracing-demo` experiment.
3. Delete the experiment (this removes all associated traces and runs).

Alternatively, keep the experiment -- subsequent lessons build on the same MLflow deployment, and having historical traces is useful for comparison.

No OpenShift resources were created in this lesson beyond what was deployed in L2-M5.1.

## Next Steps

Continue to [L2-M5.3 -- OpenTelemetry for Inference](../3_opentelemetry/) to instrument the inference layer itself. While MLflow Tracing captures the agent's view of execution (tool calls, LLM requests, chain steps), OpenTelemetry captures the infrastructure view -- request latency at the vLLM server, GPU utilization during inference, queue depth, and inter-service communication. Together, MLflow traces and OpenTelemetry traces provide full-stack observability from the user's query through the agent to the model.
