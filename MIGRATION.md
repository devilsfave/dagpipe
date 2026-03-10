# Migrating from DagPipe v0.1.x to v0.2.0

**The short version:** Nothing breaks. Every v0.1.x call works in v0.2.0 unchanged.
New features are all opt-in via new optional parameters.

---

## WHAT YOU DO NOT NEED TO CHANGE

Every existing line of code that works in v0.1.x works in v0.2.0.

These all continue to work with zero changes:

```python
# ✅ All of these still work in v0.2.0 with no changes

from dagpipe.dag import PipelineOrchestrator, DAGNode, load_dag
from dagpipe.router import ModelRouter
from dagpipe.constrained import constrained_generate
from dagpipe.checkpoints import FilesystemCheckpoint

nodes = [
    DAGNode(id="research", fn_name="do_research"),
    DAGNode(id="draft", fn_name="write_draft", depends_on=["research"]),
]

orch = PipelineOrchestrator(
    nodes=nodes,
    node_registry=registry,
    router=router,
    max_retries=3,
)

result = orch.run(initial_state={"topic": "AI"})
print(result["research"])    # ✅ still works
print(result["draft"])       # ✅ still works
result.get("research")       # ✅ still works
"research" in result         # ✅ still works
```

---

## ONE DEPRECATION WARNING (not a break)

If you use `checkpoint_dir=` you will see a deprecation warning:

```
DeprecationWarning: checkpoint_dir is deprecated and will be removed in v0.2.0.
Use checkpoint_backend=FilesystemCheckpoint(path) instead.
```

**Fix (takes 30 seconds):**

```python
# BEFORE (deprecated, still works but warns):
orch = PipelineOrchestrator(
    nodes=nodes,
    node_registry=registry,
    checkpoint_dir=Path(".dagpipe/checkpoints"),
)

# AFTER (correct):
from dagpipe.dag import FilesystemCheckpoint

orch = PipelineOrchestrator(
    nodes=nodes,
    node_registry=registry,
    checkpoint_backend=FilesystemCheckpoint(Path(".dagpipe/checkpoints")),
)
```

---

## CHECKPOINT FILE FORMAT CHANGE

v0.2.0 adds a `_meta` key to checkpoint files when nodes succeed:

```json
{
  "your_output_key": "your_output_value",
  "_meta": {
    "node_hash": "a3f8c1d2e4b7f9a1",
    "checkpointed_at": "2026-03-08T14:00:00Z",
    "dagpipe_version": "0.2.0"
  }
}
```

**Impact on your code:** None. The `_meta` key is stripped before it reaches the next node's
context. You will never see it in your node functions.

**Impact on existing checkpoints:** If you have v0.1.x checkpoints on disk and run v0.2.0,
they will be used normally. They will not have `_meta`, so stale checkpoint detection will not
apply to them (it only activates when `_meta.node_hash` is present). This is safe.

---

## NEW FEATURES (all opt-in, all optional)

These do nothing unless you explicitly use them.

### 1. PipelineRun Telemetry

```python
# Old way (still works):
result = orch.run()

# New way (optional):
state, run = orch.run()
print(run.estimated_total_cost_usd)
print(run.total_duration_seconds)
print(run.nodes[0].status)
```

The return value of `orch.run()` is now a `_PipelineResult` object that behaves like a dict
(for backward compat) AND supports tuple unpacking (for new telemetry access).
All dict methods (`get`, `items`, `keys`, `in`) still work exactly as before.

### 2. Semantic Contracts (per node, optional)

```python
DAGNode(
    id="revenue",
    fn_name="calc_revenue",
    assert_fn=lambda out: 0 < out.get("revenue", 0) < 1e12,
    assert_message="Revenue must be realistic",
)
```

If you do not add `assert_fn`, nothing changes.

### 3. Secrets Separation (optional)

```python
orch = PipelineOrchestrator(
    nodes=nodes,
    node_registry=registry,
    secrets={"API_KEY": "sk-..."},  # Never enters any node's context
)
```

If you do not pass `secrets=`, nothing changes.

### 4. Context Isolation (optional, opt-in)

```python
orch = PipelineOrchestrator(
    nodes=nodes,
    node_registry=registry,
    isolate_context=True,  # Nodes only see declared deps
)
```

Default is `False` (v0.1.x behaviour). If you do not pass `isolate_context=True`, nothing changes.

**Note:** If you turn this ON for an existing pipeline, check that your node functions
only use data from their declared `depends_on` nodes. Any node that reads from
`context["some_other_node"]` without declaring it in `depends_on` will break.

### 5. Dead Letter Queue (automatic, no config)

When any node exhausts all retries, v0.2.0 automatically writes:
`.dagpipe/checkpoints/{node_id}.failed.json`

You do not need to do anything for this. It is always on when using `FilesystemCheckpoint`.

To inspect a failure:
```python
from dagpipe.dag import inspect_failure
failure = inspect_failure("my_node_id")
print(failure["last_error"])
```

To manually fix and resume:
```python
from dagpipe.dag import override_node
override_node("my_node_id", {"corrected": "output"})
# Re-run the pipeline — it will use this and continue
```

### 6. Circuit Breaker (optional)

```python
orch = PipelineOrchestrator(
    nodes=nodes,
    node_registry=registry,
    circuit_breaker_threshold=3,
)
```

Default is `None` (off). Only activates when you set a threshold.

To reset after fixing the issue:
```python
from dagpipe.dag import reset_circuit
reset_circuit("node_id")
```

---

## GEMINI MODEL UPDATE (ACTION REQUIRED if you use Gemini)

`gemini-2.0-flash` was retired by Google on **March 3, 2026**. Any pipeline using this
model string will fail with an API error.

**Update your model strings:**

```python
# BEFORE (broken as of March 3, 2026):
gemini_fn = lambda messages: call_gemini(messages, model="gemini-2.0-flash")

# AFTER (correct):
gemini_fn = lambda messages: call_gemini(messages, model="gemini-2.5-flash")
```

Search your entire project for `gemini-2.0-flash` and replace with `gemini-2.5-flash`.

---

## SUMMARY TABLE

| Change | Type | Action Required |
|--------|------|-----------------|
| `checkpoint_dir=` deprecated | Deprecation warning | Update to `checkpoint_backend=FilesystemCheckpoint(path)` — 30 seconds |
| `_meta` added to checkpoint files | Transparent | None |
| `orch.run()` returns `_PipelineResult` | Backward compat | None — behaves like dict |
| Dead letter queue | New feature, automatic | None |
| `assert_fn` on DAGNode | New feature, opt-in | None unless you want it |
| `secrets=` parameter | New feature, opt-in | None unless you want it |
| `isolate_context=` parameter | New feature, opt-in | None unless you want it |
| `gemini-2.0-flash` retired | External change | **Required: update model string** |
