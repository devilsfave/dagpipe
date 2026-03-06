<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:161b22,100:00d9ff&height=120&section=header"/>

<div align="center">
  
<img src="assets/logo.png" alt="DagPipe Logo" width="160" />

# DagPipe

[![Typing SVG](https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=20&duration=3000&pause=1000&color=00D9FF&center=true&vCenter=true&multiline=true&repeat=true&width=600&height=80&lines=Zero-cost,+crash-proof+LLM+orchestration;Route+tasks+safely+to+free-tier+models;Never+lose+progress+mid-pipeline)](https://git.io/typing-svg)

<p>
  <img src="https://img.shields.io/badge/tests-59%20passing-00d9ff?style=flat-square" alt="Tests" />
  <img src="https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/license-MIT-0d1117?style=flat-square&color=00d9ff" alt="License" />
  <img src="https://img.shields.io/badge/version-0.1.0-FF4500?style=flat-square" alt="Version" />
  <a href="https://www.bestpractices.dev/projects/12089"><img src="https://www.bestpractices.dev/projects/12089/badge" alt="OpenSSF Best Practices" /></a>
</p>

</div>

---

### DagPipe is the reliability layer that makes AI-generated workflows safe to ship — crash recovery, schema validation, and cost routing in 150 lines of Python.

---


##  Stop paying for failed LLM pipelines.

Building with LLMs is too expensive and too fragile. Pipelines break mid-run. Rate limits waste your completed work. Paying for massive frontier models to handle every single node is overkill. **DagPipe fixes all three.**

It turns any multi-step LLM workflow into a resilient, checkpointed DAG that routes tasks to the right free-tier model — and resumes exactly from the last successful step if anything goes wrong.

---

##  Why DagPipe?

<div align="center">

| 🔴 Without DagPipe | 🟢 With DagPipe |
|---|---|
| Pipeline crashes = start over | **JSON checkpointing** — resume from last successful node |
| Paying for large models on simple tasks | **Cognitive routing** — route easy tasks to free-tier LLMs |
| LLM returns malformed JSON | **Guaranteed structured output** — auto-retry with error feedback |
| Tight coupling to one LLM provider | **Provider-agnostic** — wire any callable as your model |
| Fragile sequential scripts | **Topological DAG execution** — safe dependency resolution |

</div>

---

## Two Ways to Use DagPipe

**For developers** — Install the library and build crash-proof LLM pipelines in Python:
```bash
pip install dagpipe-core
```

**For everyone** — Describe your workflow in plain English. Receive production-ready, crash-proof pipeline code as a downloadable zip. No coding required: [👉 Pipeline Generator on Apify ($0.05/run)](https://apify.com/gastronomic_desk/pipeline-generator)

> The generator outputs DagPipe pipelines — so every generated zip is already wired with crash recovery, schema validation, and cost routing from the library above.

---

## ⚙️ Requirements

> Python 3.12+ · `pydantic >= 2.0` · `pyyaml`

---

##  Quickstart

```python
from pathlib import Path
from dagpipe.dag import PipelineOrchestrator, DAGNode, FilesystemCheckpoint
from dagpipe.router import ModelRouter
from dagpipe.constrained import constrained_generate

# ── 1. Define your node functions ─────────────────────────────
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
    # Deterministic node — no LLM needed
    print(f"Publishing: {context['write_draft']['draft'][:100]}...")
    return {"status": "published", "url": "https://example.com/article"}


# ── 2. Wire your LLM providers ────────────────────────────────
# DagPipe handles ANY Python callable. Mix and match providers:

from google.genai import Client
import groq

# Example A: A blazing fast 70B model for complex tasks (Groq Llama 3.3)
groq_client = groq.Groq()
def llama33_70b(messages):
    return groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile", messages=messages
    ).choices[0].message.content

# Example B: A high-rate-limit free-tier for easy tasks (Gemini 2.5 Flash)
gemini_client = Client()
def gemini_flash(messages):
    return gemini_client.models.generate_content(
        model='gemini-2.5-flash', contents=messages[0]["content"]
    ).text


# ── 3. Build the router ───────────────────────────────────────
# Save money by assigning cheap models to low-complexity tasks
router = ModelRouter(
    low_complexity_fn=gemini_flash,  low_label="google_gemini_flash",
    high_complexity_fn=llama33_70b,  high_label="groq_llama_33",
    fallback_fn=gemini_flash,        fallback_label="fallback_gemini",
    complexity_threshold=0.6,
)


# ── 4. Define the DAG ─────────────────────────────────────────
nodes = [
    DAGNode(id="research",    fn_name="research",    complexity=0.4),
    DAGNode(id="write_draft", fn_name="write_draft", complexity=0.7,
            depends_on=["research"]),
    DAGNode(id="publish",     fn_name="publish",
            depends_on=["write_draft"], is_deterministic=True),
]


# ── 5. Run it ─────────────────────────────────────────────────
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

##  How It Works

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

> Default Behavior: **v0.1.x runs nodes sequentially.**

Even if nodes are topologically independent, the orchestrator executes them one-at-a-time to ensure maximum crash predictability. Parallel execution is explicitly on the roadmap for v0.2.0.

---

## 🤖 AEO-Native by Design

Every actor exposes machine-readable `input_schema.json` and `output_schema.json` — making DagPipe tools discoverable and executable by AI agents without human configuration.

## 📦 Core Modules

### `dagpipe.dag` — The Orchestrator
The central engine. Loads a DAG from a Python list or YAML file, sorts nodes by dependency, and executes them in order with checkpointing and retry.

```python
from dagpipe.dag import PipelineOrchestrator, DAGNode, load_dag

# Load from YAML
nodes = load_dag(Path("my_pipeline.yaml"))

# Or define in Python
nodes = [DAGNode(id="step_a", fn_name="fn_a", complexity=0.3)]
```

### `dagpipe.checkpoints` — Crash Recovery
Saves node output to disk after every successful execution. On resume, completed nodes are skipped entirely.

> **New in v0.1.0:** The `CheckpointStorage` Protocol. 

`FilesystemCheckpoint` is used by default. To use a custom backend (Redis, S3, in-memory), implement the protocol:

```python
from dagpipe.dag import CheckpointStorage

class RedisCheckpoint(CheckpointStorage):
    def save(self, id: str, data: dict): redis_client.set(id, json.dumps(data))
    def load(self, id: str): return json.loads(redis_client.get(id) or "null")
    def exists(self, id: str): return redis_client.exists(id) > 0
    def clear(self): redis_client.flushdb()
```
*(Note: Passing `checkpoint_dir` directly to the Orchestrator is deprecated).*

### `dagpipe.router` — Intelligent Model Selection
Routes tasks to the cheapest model that can handle them. Tracks rate limit budgets and escalates on retry.

```python
from dagpipe.router import ModelRouter, classify_complexity

score = classify_complexity("implement OAuth authentication", token_count=1200)
# → 0.8 (high — triggers high_complexity_fn)

router = ModelRouter(
    low_complexity_fn=cheap_model,   low_label="7b",
    high_complexity_fn=smart_model,  high_label="70b",
    fallback_fn=backup_model,        fallback_label="backup",
)
fn, label = router.route(complexity=0.8)
```

### `dagpipe.constrained` — Guaranteed Structured Output
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
# result is a validated ArticleOutput instance — guaranteed
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



##  The Zero-Cost Stack

DagPipe is designed to run entirely on free tiers:

| Provider | Model | Free Tier |
|---|---|---|
| Groq | Llama 3.3 70B | 30 req/min |
| Groq | Llama 3 8B | 30 req/min |
| Google | Gemini 2.5 Flash | 10 req/min |
| Modal | Any 7B model | $30/month free credits (Starter plan) |
| Ollama | Any model | Local, unlimited |

Wire any of these as your `low_complexity_fn`, `high_complexity_fn`, or `fallback_fn`. DagPipe is provider-agnostic.

---

## ❓ FAQ & Architecture Decisions

**Why not just use LangChain or LangGraph?**
The key difference: DagPipe includes a self-referential generator that produces entire pipelines from plain English — something LangGraph does not offer. Beyond that, LangGraph is powerful but comes with a massive latency and complexity tax. DagPipe is intentionally stripped down. It’s strictly a DAG executor with disk-based checkpointing and Pydantic validation. The goal was zero bloated abstractions, just pure Python callables solving the "crash and restart" problem for long-running batch jobs.

**How does it route without using an LLM?**
Using an LLM to route an LLM is too expensive. The router uses pure Python heuristics (keyword matching, token thresholds) to estimate cognitive complexity. If the task scores below your threshold, it routes to your `low_complexity_fn` (like a local 8B model). Above it, it hits your `high_complexity_fn`.

**What happens if the schema validator gets stuck in an infinite loop?**
The `PipelineOrchestrator` respects the `max_retries` parameter. If a node exhausts its retry budget (e.g., the model keeps failing to return valid JSON despite error feedback), DagPipe halts and raises a `RuntimeError`. Because of the checkpointing, you can adjust the prompt or the schema and restart without losing previous work.

**Does this support parallel/async execution?**
Currently, `v0.1.0` executes the topological sort sequentially. Full `asyncio` support for concurrent execution of independent nodes is on the roadmap for the next major release. The immediate focus of this version is entirely on crash resilience and state persistence.

---

## 🛒 Templates

Ready-to-run pipeline packages built on DagPipe. Download, drop in your API key, and execute.

| Template | Description | Link |
|---|---|---|
| **Content Pipeline** | Research → draft → edit → SEO-optimize blog posts using Groq's free tier | [Get it →](https://dagpipe.lemonsqueezy.com/checkout/buy/8877121e-5ad7-415f-b3e0-192b583ebfcd) |

### 🎭 Apify Actors

Resilient, schema-enforced data extraction as a service.

| Actor | Purpose | Link |
|---|---|---|
| **Pipeline Generator** | 🌟 **The flagship workflow architect** | [Apify Store →](https://apify.com/gastronomic_desk/pipeline-generator) |
| **Structured Extract** | Multi-model (Groq/OpenAI/Ollama) data extractor | [Apify Store →](https://apify.com/gastronomic_desk/structured-extract) |
| **E-Commerce Extractor** | Specialized price & product data extraction | [Apify Store →](https://apify.com/gastronomic_desk/ecommerce-price-extractor) |

More templates coming soon. Have a use case? [Open an issue.](https://github.com/devilsfave/dagpipe/issues)

---

## 📊 Project Status

```
Phase 1 — Core Library         ████████████████████  COMPLETE
Phase 2 — PyPI + Templates     ████████████████████  COMPLETE  
Phase 3 — Actors + MCP         ████████████████░░░░  IN PROGRESS
Phase 4 — Auto-Migrator        ░░░░░░░░░░░░░░░░░░░░  UPCOMING
```

**Test coverage:** 59 tests · 4 modules · 0 regressions

---



## 📄 License

MIT License — Built for the global developer community.

---

<div align="center">
  <img src="https://quotes-github-readme.vercel.app/api?type=horizontal&theme=algolia" alt="Dev Quote"/>
</div>

<p align="center">
  Built by <a href="https://github.com/devilsfave">@devilsfave</a> ·
</p>

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:161b22,100:00d9ff&height=120&section=footer"/>
