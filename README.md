# DagPipe — The Crash-Proof LLM Pipeline Engine

![Tests](https://github.com/devilsfave/dagpipe/actions/workflows/test.yml/badge.svg)
![Security](https://github.com/devilsfave/dagpipe/actions/workflows/security.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/dagpipe-core)
![Python](https://img.shields.io/pypi/pyversions/dagpipe-core)
![License](https://img.shields.io/github/license/devilsfave/dagpipe)

> NeurIPS 2025 research analyzing **1,642 real-world multi-agent execution traces**
> found a **41–86.7% failure rate** across 7 state-of-the-art open-source systems.
> The root cause: cascading error propagation — one failed node corrupts all downstream nodes.
>
> **DagPipe makes cascade failure structurally impossible.**

Every node's output is independently validated and checkpointed before the next node executes.
A failure at node 4 cannot corrupt nodes 1, 2, or 3. Delete nothing. Just re-run.
DagPipe resumes exactly where it stopped — automatically.

```
Pipeline: research → outline → draft → edit → publish
                                  ↑
                            crashed here
                            
Re-run → research ✓ (restored) → outline ✓ (restored) → draft (re-runs) → ...
```

**Zero infrastructure. Zero subscription. Runs entirely on Groq's free tier.**

---

## Why DagPipe Exists

Every LLM orchestrator has the same fatal flaw: when a node fails, the entire
pipeline fails. You lose everything. You restart from zero. You burn API credits re-running
work that already succeeded.

DagPipe solves this with one rule: **a node's output is checkpointed the moment it succeeds.**
The execution graph is a static YAML file — no LLM can modify it at runtime. This makes
DagPipe pipelines auditable, reproducible, and safe to run on sensitive data.

---

## Security Architecture

### Static Execution Graph
DagPipe pipelines cannot self-modify. The graph is declared in YAML before runtime.
No LLM call can add, remove, or reorder nodes. This is what makes DagPipe safe to run
on sensitive data — unlike agent frameworks where the LLM decides what executes next.

### Semantic Output Contracts (v0.2+)
Beyond schema validation, nodes can declare semantic assertions:
```python
DAGNode(
    id="revenue",
    fn_name="calculate_revenue",
    assert_fn=lambda out: 0 < out.get("revenue", 0) < 1e12,
    assert_message="Revenue must be a realistic positive number",
)
```
If the LLM returns structurally valid but semantically wrong data, the assertion catches it,
injects the failure context into the retry prompt, and forces self-correction.

### Context Isolation (v0.2+)
Nodes only receive outputs from their declared dependencies. A node processing untrusted
web data cannot access API keys, credentials, or outputs from unrelated pipeline branches.

### Dead Letter Queue (v0.2+)
When a node fails after all retries, DagPipe saves the full failure context to
`.dagpipe/checkpoints/{node_id}.failed.json` — including the context passed to the node,
the last error, and instructions for manual correction. No failure context is ever lost.

---

## Install

```bash
pip install dagpipe-core
```

**Requirements:** Python 3.12+, a free [Groq](https://console.groq.com) account

---

### DagPipe is the reliability layer that makes AI-generated workflows safe to ship: crash recovery, schema validation, and cost routing in 150 lines of Python.

---

## Stop paying for failed LLM pipelines.

Building with LLMs is too expensive and too fragile. Pipelines break mid-run. Rate limits waste your completed work. Paying for massive frontier models to handle every single node is overkill. **DagPipe fixes all three.**

It turns any multi-step LLM workflow into a resilient, checkpointed DAG that routes tasks to the right free-tier model and resumes exactly from the last successful step if anything goes wrong.

---

## Why DagPipe?

<div align="center">

| 🔴 Without DagPipe | 🟢 With DagPipe |
|---|---|
| Pipeline crashes = start over | **JSON checkpointing**: resume from last successful node |
| Paying for large models on simple tasks | **Cognitive routing**: route easy tasks to free-tier LLMs |
| LLM returns malformed JSON | **Guaranteed structured output**: auto-retry with error feedback |
| Tight coupling to one LLM provider | **Provider-agnostic**: wire any callable as your model |
| Fragile sequential scripts | **Topological DAG execution**: safe dependency resolution |

</div>

---

## Three Ways to Use DagPipe

**For developers:** install the library and build crash-proof LLM pipelines in Python:
```bash
pip install dagpipe-core
```

**For non-coders:** describe your workflow in plain English, receive production-ready crash-proof pipeline code as a downloadable zip. No coding required: [👉 Pipeline Generator on Apify ($0.05/run)](https://apify.com/gastronomic_desk/pipeline-generator)

**For AI agents and IDE users:** connect directly via MCP (Model Context Protocol). Use DagPipe from Claude Desktop, Cursor, Windsurf, or any MCP-compatible client without writing any code: [👉 DagPipe Generator MCP on Smithery](https://smithery.ai/server/gastronomic-desk/dagpipe-generator)

> The generator outputs DagPipe pipelines, so every generated zip is already wired with crash recovery, schema validation, and cost routing from the library above.

> No other LLM pipeline framework ships a built-in generator that produces crash-proof, checkpointed, cost-routed pipeline code from a plain English description. You can ask any coding assistant to generate a pipeline. Only DagPipe's generator outputs code that already has checkpoint recovery, free-tier routing, and Pydantic validation built in by default.

---

## 🔌 MCP Server

DagPipe exposes a live MCP server that lets any MCP-compatible AI client generate crash-proof pipelines through natural language. No API calls, no setup beyond one config line.

**Live endpoint:**
```
https://gastronomic-desk--dagpipe-generator-mcp.apify.actor/mcp
```

**Listed on Smithery:**
https://smithery.ai/server/gastronomic-desk/dagpipe-generator

### Available Tools

| Tool | Description |
|---|---|
| `generate_pipeline` | Generates a complete crash-proof DagPipe workflow ZIP from a plain English description |

### Connect via Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dagpipe-generator": {
      "url": "https://gastronomic-desk--dagpipe-generator-mcp.apify.actor/mcp?groqApiKey=YOUR_GROQ_KEY",
      "transport": "streamable-http"
    }
  }
}
```

### Connect via Cursor / Windsurf

Add to your MCP settings:

```json
{
  "dagpipe-generator": {
    "url": "https://gastronomic-desk--dagpipe-generator-mcp.apify.actor/mcp?groqApiKey=YOUR_GROQ_KEY",
    "transport": "streamable-http"
  }
}
```

> Get your free Groq API key at console.groq.com/keys. Takes 2 minutes, no credit card required.

### Run Locally (stdio transport)

For local use with Cursor or Windsurf without Apify:

```bash
git clone https://github.com/devilsfave/dagpipe
cd dagpipe
pip install -r servers/dagpipe-generator/requirements.txt
export GROQ_API_KEY=your_key_here
python servers/dagpipe-generator/server.py
```

Then point your MCP client to the local server using stdio transport.

---

## ⚙️ Requirements

> Python 3.12+ · `pydantic >= 2.0` · `pyyaml`

---

## Quickstart

```python
from pathlib import Path
from dagpipe.dag import PipelineOrchestrator, DAGNode, FilesystemCheckpoint
from dagpipe.router import ModelRouter
from dagpipe.constrained import constrained_generate

# 1. Define your node functions
def research(context, model):
    # model is whatever callable your router selected
    prompt = [{"role": "user", "content": f"Research: {context['topic']}"}]
    raw = model(prompt)
    return {"summary": raw}

def write_draft(context, model):
    summary = context["research"]["summary"]
    prompt = [{"role": "user", "content": f"Write an article based on: {summary}"}]
    raw = model(prompt)
    return {"draft": raw}

def publish(context, model):
    # deterministic node, no LLM needed
    print(f"Publishing: {context['write_draft']['draft'][:100]}...")
    return {"status": "published", "url": "https://example.com/article"}


# 2. Wire your LLM providers
# DagPipe handles ANY Python callable. Mix and match providers:

from google.genai import Client
import groq

# Example A: a fast 70B model for complex tasks (Groq Llama 3.3)
groq_client = groq.Groq()
def llama33_70b(messages):
    return groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile", messages=messages
    ).choices[0].message.content

# Example B: a high-rate-limit free-tier model for easy tasks (Gemini 2.5 Flash)
gemini_client = Client()
def gemini_flash(messages):
    return gemini_client.models.generate_content(
        model='gemini-2.5-flash', contents=messages[0]["content"]
    ).text


# 3. Build the router
# Save money by assigning cheap models to low-complexity tasks
router = ModelRouter(
    low_complexity_fn=gemini_flash,  low_label="google_gemini_flash",
    high_complexity_fn=llama33_70b,  high_label="groq_llama_33",
    fallback_fn=gemini_flash,        fallback_label="fallback_gemini",
    complexity_threshold=0.6,
)


# 4. Define the DAG
nodes = [
    DAGNode(id="research",    fn_name="research",    complexity=0.4),
    DAGNode(id="write_draft", fn_name="write_draft", complexity=0.7,
            depends_on=["research"]),
    DAGNode(id="publish",     fn_name="publish",
            depends_on=["write_draft"], is_deterministic=True),
]


# 5. Run it
orchestrator = PipelineOrchestrator(
    nodes=nodes,
    node_registry={
        "research":    research,
        "write_draft": write_draft,
        "publish":     publish,
    },
    router=router,
    checkpoint_backend=FilesystemCheckpoint(
        Path(".dagpipe/checkpoints")
    ),
    max_retries=3,
    on_node_complete=lambda node_id, result, duration:
        print(f"  ✓ {node_id} ({duration:.1f}s)"),
)

result = orchestrator.run(initial_state={"topic": "AI in African fintech"})
```

**Crash mid-run?** Delete nothing. Just re-run. DagPipe reads the checkpoints and skips completed nodes automatically.

---

## How It Works

```
Your Tasks (YAML or Python list of DAGNodes)
                    │
                    ▼
         ┌──────────────────┐
         │  Topological     │  resolves execution order,
         │  Sort            │  detects cycles before running
         └────────┬─────────┘
                  │
        ┌─────────▼──────────┐
        │  Checkpoint        │  restores any completed nodes
        │  Restore           │  from previous runs
        └─────────┬──────────┘
                  │
          ┌───────▼────────┐
          │  For each node │◄─────────────────────────┐
          └───────┬────────┘                          │
                  │                                   │
        ┌─────────▼──────────┐    ┌────────────────┐  │
        │  ModelRouter       │───▶│ low / high /   │  │
        │  (complexity score)│    │ fallback fn    │  │
        └─────────┬──────────┘    └────────────────┘  │
                  │                                   │
        ┌─────────▼──────────┐                        │
        │  Constrained       │  forces valid output   │
        │  Generator         │  retries with error    │
        └─────────┬──────────┘  feedback on failure   │
                  │                                   │
        ┌─────────▼──────────┐                        │
        │  Checkpoint Save   │  writes result to disk │
        └─────────┬──────────┘                        │
                  │                                   │
          crash here = resume from ✓            next node
```

---

## ⏱️ Sequential Execution

> Default behavior: **v0.1.x runs nodes sequentially.**

Even if nodes are topologically independent, the orchestrator executes them one at a time to ensure maximum crash predictability. Parallel execution is on the roadmap for v0.3.0.

---

## 🤖 AEO-Native by Design

Every actor exposes machine-readable `input_schema.json` and `output_schema.json`, making DagPipe tools discoverable and executable by AI agents without human configuration.

---

## 📦 Core Modules

### `dagpipe.dag`: The Orchestrator
The central engine. Loads a DAG from a Python list or YAML file, sorts nodes by dependency, and executes them in order with checkpointing and retry.

```python
from dagpipe.dag import PipelineOrchestrator, DAGNode, load_dag

# Load from YAML
nodes = load_dag(Path("my_pipeline.yaml"))

# Or define in Python
nodes = [DAGNode(id="step_a", fn_name="fn_a", complexity=0.3)]
```

### `dagpipe.checkpoints`: Crash Recovery
Saves node output to disk after every successful execution. On resume, completed nodes are skipped entirely.

> **New in v0.2.0:** the `CheckpointStorage` Protocol.

`FilesystemCheckpoint` is used by default. To use a custom backend (Redis, S3, in-memory), implement the protocol:

```python
from dagpipe.dag import CheckpointStorage

class RedisCheckpoint(CheckpointStorage):
    def save(self, id: str, data: dict): redis_client.set(id, json.dumps(data))
    def load(self, id: str): return json.loads(redis_client.get(id) or "null")
    def exists(self, id: str): return redis_client.exists(id) > 0
    def clear(self): redis_client.flushdb()
```
*(Note: passing `checkpoint_dir` directly to the Orchestrator is deprecated.)*

### `dagpipe.router`: Intelligent Model Selection
Routes tasks to the cheapest model that can handle them. Tracks rate limit budgets and escalates on retry.

```python
from dagpipe.router import ModelRouter, classify_complexity

score = classify_complexity("implement OAuth authentication", token_count=1200)
# → 0.8 (high complexity, triggers high_complexity_fn)

router = ModelRouter(
    low_complexity_fn=cheap_model,   low_label="7b",
    high_complexity_fn=smart_model,  high_label="70b",
    fallback_fn=backup_model,        fallback_label="backup",
)
fn, label = router.route(complexity=0.8)
```

### `dagpipe.constrained`: Guaranteed Structured Output
Wraps any LLM call with Pydantic schema validation. On failure, injects the error back into the prompt and retries automatically.

```python
from pydantic import BaseModel
from dagpipe.constrained import constrained_generate

class ArticleOutput(BaseModel):
    title: str
    body: str
    word_count: int

result = constrained_generate(
    messages=[{"role": "user", "content": "Write a short article about AI."}],
    schema=ArticleOutput,
    llm_call_fn=my_llm,
    max_retries=3,
)
# result is a validated ArticleOutput instance, every time
```

---

## 📝 YAML Pipeline Definition

```yaml
# my_pipeline.yaml
nodes:
  - id: research
    fn: research_fn
    complexity: 0.4
  - id: summarize
    fn: summarize_fn
    depends_on: [research]
    complexity: 0.5
  - id: publish
    fn: publish_fn
    depends_on: [summarize]
    is_deterministic: true
```

---

## The Zero-Cost Stack

DagPipe is designed to run entirely on free tiers:

| Provider | Model | Free Tier |
|---|---|---|
| Groq | Llama 3.3 70B | 30 req/min |
| Groq | Llama 3.1 8B | 30 req/min |
| Google | Gemini 2.5 Flash | 10 req/min |
| Modal | Any 7B model | $30/month free credits (Starter plan) |
| Ollama | Any model | Local, unlimited |

Groq has a generous free tier with Llama 3.3 70B and Llama 3.1 8B. Google's Gemini 2.5 Flash and 2.5 Flash-Lite are both free. Note that Gemini 2.0 Flash was retired March 3, 2026, so any code referencing that model string will break. Update to `gemini-2.5-flash`.

Wire any of these as your `low_complexity_fn`, `high_complexity_fn`, or `fallback_fn`. DagPipe is provider-agnostic.

---

## ❓ FAQ & Architecture Decisions

<details>
<summary><b>Click to expand</b></summary>

**Why not just use LangChain or LangGraph?**

LangGraph has checkpointing, but it is tightly coupled to their `TypedDict` state system and graph compilation model. You adopt the full framework to get it. DagPipe's checkpoints are plain JSON files on disk, readable with any text editor, with no framework lock-in required.

Beyond that, DagPipe ships a built-in generator that produces entire crash-proof pipelines from a plain English description. LangGraph does not have this. DagPipe is intentionally narrow: a DAG executor with disk-based checkpointing and Pydantic validation. No bloated abstractions, just Python callables solving the crash-and-restart problem.

**Why not just wrap my pipeline in a try/except and restart manually?**

A `try/except` tells you something failed. It does not save the work that succeeded before the crash. DagPipe's checkpointing saves the output of every completed node to disk before moving to the next one. When you restart, nodes 1 through 6 are skipped automatically. You only pay to re-run the node that actually failed.

**How is DagPipe's checkpointing different from LangGraph's?**

LangGraph's checkpointing requires a `StateGraph`, `TypedDict` schemas, and a compiled checkpointer object. You are adopting their full framework architecture to access it. DagPipe's checkpoints are just JSON files. You can open them in a text editor, copy them, inspect them, or move them without any framework code.

**Can I use this with OpenAI, Anthropic, or any other provider?**

Yes. Any Python function that takes a list of messages and returns a string works as a model function. Whether it is OpenAI, Anthropic, Cohere, a local Ollama call, or a mock function for testing, if it is callable, DagPipe can route to it.

**Does DagPipe store my checkpoint data anywhere online?**

No. Checkpoints are plain JSON files written to a local directory on your machine (default: `.dagpipe/checkpoints/`). Nothing leaves your environment unless you build a custom `CheckpointStorage` backend pointing to Redis, S3, or wherever you choose.

**Does the router work without configuration?**

Yes. Out of the box, the router uses keyword heuristics and token count thresholds to estimate task complexity. You set a `complexity` score between 0.0 and 1.0 on each node, and the router handles the rest. If the defaults do not fit your use case, you can override routing manually per node.

**How does it route without using an LLM?**

Using an LLM to route an LLM is too expensive. The router uses pure Python heuristics (keyword matching, token thresholds) to estimate cognitive complexity. If the task scores below your threshold, it routes to your `low_complexity_fn`. Above it, it hits your `high_complexity_fn`.

**What happens if the schema validator keeps failing?**

The `PipelineOrchestrator` respects the `max_retries` parameter. If a node exhausts its retry budget, DagPipe halts and raises a `RuntimeError`. Because of checkpointing, you can adjust the prompt or schema and restart without losing any previously completed work.

**Does this support parallel or async execution?**

Not yet. `v0.1.x` executes nodes sequentially. Full `asyncio` support for concurrent execution of independent nodes is on the roadmap for `v0.3.0`. The focus of this version is crash resilience and state persistence.

**How do I use DagPipe from Claude Desktop or Cursor?**

Install the MCP server from Smithery at [smithery.ai/server/gastronomic-desk/dagpipe-generator](https://smithery.ai/server/gastronomic-desk/dagpipe-generator). You will need a free Groq API key from console.groq.com/keys. Once connected, type "Generate a pipeline that does X" in your AI chat and receive a deployable ZIP in seconds.

**Does this work if my pipeline was built with an AI coding tool?**

Yes. DagPipe does not care how your node functions were written. Whether you wrote them by hand, with GitHub Copilot, or with a vibe coding tool, the checkpointing, validation, and routing work the same way. If the pipeline crashes, DagPipe picks up from the last successful node regardless of how the code was produced.

</details>

---

## 🛒 Templates

Ready-to-run pipeline packages built on DagPipe. Download, drop in your API key, and run.

| Template | Description | Link |
|---|---|---|
| **DagPipe Generator MCP** | 🔌 **MCP server: connect from any AI IDE** | [Smithery →](https://smithery.ai/server/gastronomic-desk/dagpipe-generator) |
| **Content Pipeline** | Research, draft, edit, and SEO-optimize blog posts using Groq's free tier | [Get it →](https://dagpipe.lemonsqueezy.com/checkout/buy/8877121e-5ad7-415f-b3e0-192b583ebfcd) |

### 🎭 Apify Actors

Resilient, schema-enforced data extraction as a service.

| Actor | Purpose | Link |
|---|---|---|
| **Pipeline Generator** | 🌟 **The flagship workflow architect** | [Apify Store →](https://apify.com/gastronomic_desk/pipeline-generator) |
| **Structured Extract** | Multi-model (Groq/Gemini/Ollama) data extractor | [Apify Store →](https://apify.com/gastronomic_desk/structured-extract) |
| **E-Commerce Extractor** | Specialized price and product data extraction | [Apify Store →](https://apify.com/gastronomic_desk/ecommerce-price-extractor) |

More templates coming. Have a use case? [Open an issue.](https://github.com/devilsfave/dagpipe/issues)

---

## 📊 Project Status

```
Phase 1: Core Library         ████████████████████  COMPLETE
Phase 2: PyPI + Templates     ████████████████████  COMPLETE
Phase 3: Actors + MCP         ████████████████████  COMPLETE
Phase 4: Auto-Migrator        ░░░░░░░░░░░░░░░░░░░░  UPCOMING
```

**Test coverage:** 108 tests · 4 modules · 0 regressions

---

## 🤝 Contributing

Issues and PRs are welcome. If you find a bug, open an issue with the error output and the Python version. If you want to add a feature, open an issue first so we can agree on the design before any code is written.

---

## 📄 License

MIT License, built for the global developer community.

---

<div align="center">
  <img src="https://quotes-github-readme.vercel.app/api?type=horizontal&theme=algolia" alt="Dev Quote"/>
</div>

<p align="center">
  Built by <a href="https://github.com/devilsfave">@devilsfave</a>
</p>

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:161b22,100:00d9ff&height=120&section=footer"/>