# DagPipe

> **Zero-cost, crash-proof LLM pipeline orchestrator.**

![Tests](https://img.shields.io/badge/tests-37%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-0.1.0-orange)
![Dependencies](https://img.shields.io/badge/dependencies-2-lightgrey)

Building with LLMs is too expensive and too fragile. Pipelines break mid-run. Rate limits waste completed work. Paying for GPT-4 on every node is overkill. **DagPipe fixes all three.**

It turns any multi-step LLM workflow into a resilient, checkpointed DAG that routes tasks to the right free-tier model — and resumes from the last successful step if anything goes wrong.

---

## Why DagPipe

| Problem | DagPipe Solution |
|---|---|
| Pipeline crashes = start over | JSON checkpointing — resume from last successful node |
| Paying for large models on simple tasks | Complexity-based routing to free-tier LLMs |
| LLM returns malformed JSON | Pydantic validation + automatic retry with error feedback |
| Tight coupling to one LLM provider | Provider-agnostic — wire any callable as your model |
| Fragile sequential chains | Explicit DAG with topological sort and cycle detection |

---

## Installation

```bash
pip install dagpipe
```

**Requirements:** Python 3.12+ · pydantic ≥ 2.0 · pyyaml

---

## Quickstart

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
import groq  # or any OpenAI-compatible client

client = groq.Groq()

def groq_70b(messages):
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile", messages=messages
    ).choices[0].message.content

def groq_8b(messages):
    return client.chat.completions.create(
        model="llama3-8b-8192", messages=messages
    ).choices[0].message.content


# ── 3. Build the router ───────────────────────────────────────
router = ModelRouter(
    low_complexity_fn=groq_8b,       label_low="groq_8b",
    high_complexity_fn=groq_70b,     label_high="groq_70b",
    fallback_fn=groq_8b,             label_fallback="groq_8b_fallback",
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

## Core Modules

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

## YAML Pipeline Definition

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

## Use Cases

- **Content pipelines** — Research → draft → edit → publish with zero loss on failure
- **Code generation** — Spec → scaffold → implement → test across free models
- **Data extraction** — Fetch → parse → validate → store with schema enforcement
- **API integrations** — Multi-step workflows where any step can fail and retry
- **Automated reporting** — Collect → analyze → format → deliver on a schedule

---

## Zero-Cost Stack

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

## Project Status

```
Phase 1 — Core Library         ████████████████████  COMPLETE
Phase 2 — PyPI Publish         ████░░░░░░░░░░░░░░░░  IN PROGRESS  
Phase 3 — MCP Servers          ░░░░░░░░░░░░░░░░░░░░  UPCOMING
Phase 4 — Auto-Migrator        ░░░░░░░░░░░░░░░░░░░░  UPCOMING
```

**Test coverage:** 37 tests · 4 modules · 0 regressions

---

## Contributing

Issues and PRs welcome. Please read the contribution guidelines before submitting.

---

## License

MIT License — Built for the global developer community.

---

<p align="center">
  Built by <a href="https://github.com/devilsfave">@devilsfave</a> ·
</p>
