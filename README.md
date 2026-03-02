<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:161b22,100:00d9ff&height=120&section=header"/>

<div align="center">
  
<img src="assets/logo.png" alt="DagPipe Logo" width="160" />

# DagPipe

[![Typing SVG](https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=20&duration=3000&pause=1000&color=00D9FF&center=true&vCenter=true&multiline=true&repeat=true&width=600&height=80&lines=Zero-cost,+crash-proof+LLM+orchestration;Route+tasks+safely+to+free-tier+models;Never+lose+progress+mid-pipeline)](https://git.io/typing-svg)

<p>
  <img src="https://img.shields.io/badge/tests-37%20passing-00d9ff?style=flat-square" alt="Tests" />
  <img src="https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/license-MIT-0d1117?style=flat-square&color=00d9ff" alt="License" />
  <img src="https://img.shields.io/badge/version-0.1.0-FF4500?style=flat-square" alt="Version" />
</p>

</div>

---

###  Stop paying for failed LLM pipelines.

Building with LLMs is too expensive and too fragile. Pipelines break mid-run. Rate limits waste your completed work. Paying for GPT-4 to handle every single node is massive overkill. **DagPipe fixes all three.**

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

## ⚙️ Installation

```bash
pip install dagpipe-core
```
> **Requirements:** Python 3.12+ · `pydantic >= 2.0` · `pyyaml`

---

##  Quickstart

```python
from pathlib import Path
from dagpipe.dag import PipelineOrchestrator, DAGNode
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

from openai import OpenAI
import groq

# Example A: A paid OpenAI model for complex tasks
openai_client = OpenAI()
def gpt_4o(messages):
    return openai_client.chat.completions.create(
        model="gpt-4o", messages=messages
    ).choices[0].message.content

# Example B: A free Groq (or local Ollama) model for easy tasks
groq_client = groq.Groq()
def groq_8b(messages):
    return groq_client.chat.completions.create(
        model="llama3-8b-8192", messages=messages
    ).choices[0].message.content


# ── 3. Build the router ───────────────────────────────────────
# Save money by assigning cheap models to low-complexity tasks
router = ModelRouter(
    low_complexity_fn=groq_8b,       label_low="free_llama3",
    high_complexity_fn=gpt_4o,       label_high="paid_gpt4o",
    fallback_fn=groq_8b,             label_fallback="fallback_llama3",
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
    checkpoint_dir=Path(".dagpipe/checkpoints"),
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

```python
from dagpipe.checkpoints import checkpoint, restore, checkpoint_exists

checkpoint("node_id", {"output": "data"}, checkpoint_dir=Path(".dagpipe"))
data = restore("node_id", checkpoint_dir=Path(".dagpipe"))  # None if not found
```

### `dagpipe.router` — Intelligent Model Selection
Routes tasks to the cheapest model that can handle them. Tracks rate limit budgets and escalates on retry.

```python
from dagpipe.router import ModelRouter, classify_complexity

score = classify_complexity("implement OAuth authentication", token_count=1200)
# → 0.8 (high — triggers high_complexity_fn)

router = ModelRouter(
    low_complexity_fn=cheap_model,   label_low="7b",
    high_complexity_fn=smart_model,  label_high="70b",
    fallback_fn=backup_model,        label_fallback="backup",
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
    description: "Gather source material"

  - id: summarize
    fn: summarize_fn
    depends_on: [research]
    complexity: 0.5
    description: "Compress to key points"

  - id: publish
    fn: publish_fn
    depends_on: [summarize]
    complexity: 0.0
    is_deterministic: true
    description: "Push to CMS — no LLM needed"
```

---

##  Use Cases

- **Content pipelines** — Research → draft → edit → publish with zero loss on failure
- **Code generation** — Spec → scaffold → implement → test across free models
- **Data extraction** — Fetch → parse → validate → store with schema enforcement
- **API integrations** — Multi-step workflows where any step can fail and retry
- **Automated reporting** — Collect → analyze → format → deliver on a schedule

---

##  The Zero-Cost Stack

DagPipe is designed to run entirely on free tiers:

| Provider | Model | Free Tier |
|---|---|---|
| Groq | Llama 3.3 70B | 30 req/min |
| Groq | Llama 3 8B | 30 req/min |
| Google | Gemini 2.0 Flash | 15 req/min |
| Modal | Any 7B model | 30 GPU-sec/day |
| Ollama | Any model | Local, unlimited |

Wire any of these as your `low_complexity_fn`, `high_complexity_fn`, or `fallback_fn`. DagPipe is provider-agnostic.

---

## ❓ FAQ & Architecture Decisions

**Why not just use LangChain or LangGraph?**
LangGraph is powerful but comes with a massive latency and complexity tax. DagPipe is intentionally stripped down. It’s strictly a DAG executor with disk-based checkpointing and Pydantic validation. The goal was zero bloated abstractions,just pure Python callables solving the "crash and restart" problem for long-running batch jobs.

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

More templates coming soon. Have a use case? [Open an issue.](https://github.com/devilsfave/dagpipe/issues)

---

## 📊 Project Status

```
Phase 1 — Core Library         ████████████████████  COMPLETE
Phase 2 — PyPI + Templates     ████████████████████  COMPLETE  
Phase 3 — MCP Servers          ░░░░░░░░░░░░░░░░░░░░  UPCOMING
Phase 4 — Auto-Migrator        ░░░░░░░░░░░░░░░░░░░░  UPCOMING
```

**Test coverage:** 37 tests · 4 modules · 0 regressions

---

## 🤝 Contributing

Issues and PRs welcome. Please read the contribution guidelines before submitting.

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
