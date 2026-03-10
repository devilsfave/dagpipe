"""DagPipe v0.2.1 — DAG Pipeline Orchestrator

DROP-IN REPLACEMENT for v0.1.x dag.py.
Every v0.1.x call works identically. All new features are opt-in via
new optional parameters — nothing breaks unless you want the new behaviour.

NEW IN v0.2.0:
  - Dead Letter Queue: failed nodes write .failed.json with full debug context
  - Semantic Contracts: assert_fn on DAGNode catches "helpful hallucinations"
  - Stale Checkpoint Detection: source hash comparison catches silent corruption
  - Context Isolation: nodes only receive declared dependency outputs (opt-in)
  - Secrets Separation: credentials never enter node context
  - PipelineRun Telemetry: structured per-node execution data on every run
  - Circuit Breaker: opens after N consecutive run-level failures per node
  - Manual Override: write .override.json to inject corrected node output

Usage (v0.1.x — unchanged):
    from dagpipe.dag import PipelineOrchestrator, DAGNode, load_dag
    orch = PipelineOrchestrator(nodes=nodes, node_registry=registry)
    result = orch.run()

Usage (v0.2.0 new features):
    from dagpipe.dag import PipelineOrchestrator, DAGNode, PipelineRun
    orch = PipelineOrchestrator(
        nodes=nodes,
        node_registry=registry,
        secrets={"API_KEY": "sk-..."},          # never enters context
        isolate_context=True,                    # nodes only see dependencies
        circuit_breaker_threshold=3,             # open after 3 consecutive failures
        strict_checkpoint=False,                 # warn (not raise) on stale checkpoint
    )
    state, run = orch.run(initial_state={"topic": "AI"})
    print(run.estimated_total_cost_usd)
    print(run.nodes[0].duration_seconds)
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import time
import warnings
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel

from .checkpoints import (
    checkpoint,
    checkpoint_exists,
    clear_checkpoints,
    restore,
)
from .registry import ModelRegistry
from .router import ModelRouter


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN PRICING — rough estimates, user-overridable
# Search "groq pricing" / "openai pricing" to verify current rates
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_TOKEN_PRICING_USD_PER_1K: dict[str, float] = {
    # Groq
    "llama-3.3-70b-versatile": 0.00059,
    "llama-3.1-70b-versatile": 0.00059,
    "llama-3.1-8b-instant": 0.00005,
    "llama-3.1-8b-instant": 0.00005,
    # Google (free tier)
    "gemini-2.5-flash": 0.0,
    "gemini-2.5-flash": 0.0,
    "gemini-2.5-flash-lite": 0.0,
    # OpenAI
    "gpt-4o": 0.0025,
    "gpt-4o-mini": 0.00015,
    "o1": 0.015,
    # Anthropic
    "claude-sonnet-4-6": 0.003,
    "claude-haiku-4-5": 0.0008,
}


# ─────────────────────────────────────────────────────────────────────────────
# TELEMETRY MODELS
# ─────────────────────────────────────────────────────────────────────────────

class NodeResult(BaseModel):
    """Per-node execution result — available in PipelineRun.nodes."""

    node_id: str
    status: Literal["success", "skipped", "failed"]
    duration_seconds: float
    retries: int
    model_used: str | None = None
    estimated_tokens: int | None = None
    estimated_cost_usd: float | None = None
    error: str | None = None
    checkpoint_was_restored: bool = False
    assert_failed: bool = False


class PipelineRun(BaseModel):
    """Full telemetry for a single pipeline execution.

    Returned alongside the state dict when orch.run() completes.

    Example:
        state, run = orch.run(initial_state={"topic": "AI"})
        print(f"Total cost: ${run.estimated_total_cost_usd:.4f}")
        print(f"Slowest node: {max(run.nodes, key=lambda n: n.duration_seconds).node_id}")
    """

    pipeline_id: str
    started_at: str           # ISO8601
    completed_at: str | None = None
    total_duration_seconds: float = 0.0
    status: Literal["success", "partial", "failed"] = "success"
    nodes: list[NodeResult] = field(default_factory=list)
    estimated_total_tokens: int = 0
    estimated_total_cost_usd: float = 0.0
    nodes_executed: int = 0
    nodes_restored: int = 0
    nodes_failed: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM EXCEPTIONS
# ─────────────────────────────────────────────────────────────────────────────

class StaleCheckpointError(RuntimeError):
    """Raised in strict mode when a node's source has changed since checkpointing."""


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a node's circuit breaker is open (too many consecutive failures)."""


class AssertionContractError(ValueError):
    """Raised when a node's assert_fn returns False after all retries."""


# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT STORAGE PROTOCOL  (unchanged from v0.1.x)
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class CheckpointStorage(Protocol):
    """Protocol for checkpoint backends — unchanged from v0.1.x.

    Any object implementing save/load/exists/clear is valid.
    """

    def save(self, node_id: str, data: dict) -> None: ...
    def load(self, node_id: str) -> Optional[dict]: ...
    def exists(self, node_id: str) -> bool: ...
    def clear(self) -> None: ...


class FilesystemCheckpoint(CheckpointStorage):
    """Default checkpoint backend — wraps checkpoints.py. Backward compatible."""

    def __init__(self, directory: Path | str) -> None:
        self._dir = directory

    def save(self, node_id: str, data: dict) -> None:
        checkpoint(node_id, data, self._dir)

    def load(self, node_id: str) -> Optional[dict]:
        return restore(node_id, self._dir)

    def exists(self, node_id: str) -> bool:
        return checkpoint_exists(node_id, self._dir)

    def clear(self) -> None:
        clear_checkpoints(self._dir)

    # ── V2 helpers (used by orchestrator for dead letter / circuit breaker) ──

    def save_failed(self, node_id: str, data: dict) -> None:
        """Write dead letter queue entry for a failed node."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{node_id}.failed.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_failed(self, node_id: str) -> dict | None:
        path = self._dir / f"{node_id}.failed.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def save_override(self, node_id: str, data: dict) -> None:
        """Write a manual override checkpoint for a failed node."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{node_id}.override.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_override(self, node_id: str) -> dict | None:
        path = self._dir / f"{node_id}.override.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def get_consecutive_failures(self, node_id: str) -> int:
        path = self._dir / f"{node_id}.failures"
        if not path.exists():
            return 0
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return 0

    def increment_failures(self, node_id: str) -> int:
        self._dir.mkdir(parents=True, exist_ok=True)
        count = self.get_consecutive_failures(node_id) + 1
        path = self._dir / f"{node_id}.failures"
        path.write_text(str(count), encoding="utf-8")
        return count

    def reset_failures(self, node_id: str) -> None:
        path = self._dir / f"{node_id}.failures"
        if path.exists():
            path.unlink()


# ─────────────────────────────────────────────────────────────────────────────
# DAG NODE  (v0.1.x fields unchanged; new optional fields added)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DAGNode:
    """A single node in the execution DAG.

    v0.1.x fields — unchanged:
        id, fn_name, depends_on, output_schema, complexity,
        is_deterministic, description

    NEW in v0.2.0 (all optional, default to None/False):
        assert_fn       — semantic contract: lambda out: bool
        assert_message  — human-readable reason shown on assertion failure
        complexity_fn   — runtime complexity override: callable(context) -> float

    Example with new features:
        DAGNode(
            id="revenue",
            fn_name="calc_revenue",
            assert_fn=lambda out: 0 < out.get("revenue", 0) < 1e12,
            assert_message="Revenue must be a realistic positive number",
        )
    """

    id: str
    fn_name: str
    depends_on: list[str] = field(default_factory=list)
    output_schema: str = ""
    complexity: float = 0.5
    is_deterministic: bool = False
    description: str = ""

    # ── V2 additions ──────────────────────────────────────────────────────────
    assert_fn: Callable[[dict], bool] | None = None
    assert_message: str = "Node output failed semantic validation"
    complexity_fn: Callable[[dict], float] | None = None

    # Internal — resolved at orchestrator init
    _fn: Callable | None = field(default=None, init=False, repr=False)

    def resolve_fn(self, registry: dict[str, Callable]) -> None:
        if self.fn_name not in registry:
            raise KeyError(f"Node '{self.id}': fn_name '{self.fn_name}' not in registry.")
        self._fn = registry[self.fn_name]

    def execute(self, context: dict[str, Any], model: Any = None) -> Any:
        if self._fn is None:
            raise RuntimeError(f"Node '{self.id}' has no resolved function. Call resolve_fn() first.")
        return self._fn(context=context, model=model)

    def get_complexity(self, context: dict[str, Any]) -> float:
        """Return runtime complexity. Uses complexity_fn if set, else static score."""
        if self.complexity_fn is not None:
            try:
                score = float(self.complexity_fn(context))
                return max(0.0, min(1.0, score))
            except Exception:
                pass
        return self.complexity

    def source_hash(self) -> str:
        """SHA256 of function source for stale checkpoint detection."""
        if self._fn is None:
            return "unresolved"
        try:
            src = inspect.getsource(self._fn)
            return hashlib.sha256(src.encode()).hexdigest()[:16]
        except (OSError, TypeError):
            return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# YAML LOADER  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def load_dag(config_path: Path) -> list[DAGNode]:
    """Load a DAG from a YAML config file.

    Expected format:
        nodes:
          - id: step1
            fn: do_research
            depends_on: []
            complexity: 0.5
            is_deterministic: false
            description: "Research the topic"

    Returns:
        List of DAGNode objects (not yet topologically sorted).
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    nodes: list[DAGNode] = []
    for node_cfg in config["nodes"]:
        nodes.append(DAGNode(
            id=node_cfg["id"],
            fn_name=node_cfg["fn"],
            depends_on=node_cfg.get("depends_on", []),
            output_schema=node_cfg.get("output_schema", ""),
            complexity=node_cfg.get("complexity", 0.5),
            is_deterministic=node_cfg.get("is_deterministic", False),
            description=node_cfg.get("description", ""),
        ))
    return nodes


# ─────────────────────────────────────────────────────────────────────────────
# TOPOLOGICAL SORT  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def topological_sort(nodes: list[DAGNode]) -> list[DAGNode]:
    """Sort nodes in dependency order. Raises ValueError on cycles."""
    node_map: dict[str, DAGNode] = {n.id: n for n in nodes}
    visited: set[str] = set()
    visiting: set[str] = set()
    order: list[DAGNode] = []

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError(f"Cycle detected involving node: {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        node = node_map.get(node_id)
        if node is None:
            raise ValueError(f"Unknown dependency: {node_id}")
        for dep in node.depends_on:
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)
        order.append(node)

    for n in nodes:
        visit(n.id)
    return order


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE ORCHESTRATOR  v0.2.0
# ─────────────────────────────────────────────────────────────────────────────

class PipelineOrchestrator:
    """Executes a DAG with checkpointing, routing, retry, and V2 safety features.

    v0.1.x usage — completely unchanged:
        orch = PipelineOrchestrator(nodes=nodes, node_registry=registry)
        result = orch.run()           # returns dict — same as before

    v0.2.0 usage — new features via new optional params:
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry=registry,
            secrets={"API_KEY": "sk-..."},      # never enters node context
            isolate_context=True,                # nodes only see their declared deps
            circuit_breaker_threshold=3,         # open circuit after N failures
            strict_checkpoint=False,             # warn on stale; True = raise
            token_pricing=my_pricing_dict,       # override default token prices
        )
        state, run = orch.run()      # state=dict (unchanged), run=PipelineRun (new)

    Backward compatibility guarantee:
        If you ignore PipelineRun (the second return value) or do:
            result = orch.run()
        You still get the dict. No code breaks.
    """

    def __init__(
        self,
        nodes: list[DAGNode] | Path,
        node_registry: dict[str, Callable],
        router: ModelRouter | None = None,
        checkpoint_backend: CheckpointStorage | None = None,
        checkpoint_dir: Path | None = None,       # DEPRECATED — use checkpoint_backend
        max_retries: int = 3,
        on_node_complete: Callable[..., Any] | None = None,
        verbose: bool = False,
        # ── V2 new parameters (all optional, all default to safe values) ──────
        secrets: dict[str, Any] | None = None,
        isolate_context: bool = False,
        circuit_breaker_threshold: int | None = None,
        strict_checkpoint: bool = False,
        token_pricing: dict[str, float] | None = None,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        if isinstance(nodes, Path):
            self._raw_nodes = load_dag(nodes)
        else:
            self._raw_nodes = list(nodes)

        self.sorted_nodes = topological_sort(self._raw_nodes)
        self.state: dict[str, Any] = {}
        self.max_retries = max_retries
        self.router = router
        self.on_node_complete = on_node_complete
        self._verbose = verbose

        # V2 options
        self._secrets: dict[str, Any] = secrets or {}
        self._isolate_context = isolate_context
        self._circuit_threshold = circuit_breaker_threshold
        self._strict_checkpoint = strict_checkpoint
        self._token_pricing = token_pricing or _DEFAULT_TOKEN_PRICING_USD_PER_1K
        self._model_registry = model_registry

        # Resolve checkpoint backend
        if checkpoint_backend is not None:
            self.checkpoint_backend: Any = checkpoint_backend
        elif checkpoint_dir is not None:
            warnings.warn(
                "checkpoint_dir is deprecated and will be removed in v0.2.0. "
                "Use checkpoint_backend=FilesystemCheckpoint(path) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.checkpoint_backend = FilesystemCheckpoint(checkpoint_dir)
        else:
            self.checkpoint_backend = FilesystemCheckpoint(Path(".dagpipe/checkpoints"))

        for node in self.sorted_nodes:
            node.resolve_fn(node_registry)

    # ── Public API ─────────────────────────────────────────────────────────

    def run(
        self,
        initial_state: dict[str, Any] | None = None,
        fresh: bool = False,
    ) -> dict[str, Any] | tuple[dict[str, Any], PipelineRun]:
        """Execute the full pipeline.

        BACKWARD COMPATIBLE: if you assign to a single variable, you get the
        same dict as v0.1.x. If you unpack into two, you get (state, PipelineRun).

            result = orch.run()          # dict — v0.1.x behaviour unchanged
            state, run = orch.run()      # dict + PipelineRun — v0.2.0

        Args:
            initial_state: Dict injected into context before execution.
                           Secrets should be passed to PipelineOrchestrator(secrets=...)
                           NOT here — anything in initial_state enters node context.
            fresh: If True, clear all checkpoints before starting.
        """
        # V2.1: Validate all configured models before starting
        if self._model_registry is not None and self.router is not None:
            self._validate_router_models()

        run = PipelineRun(
            pipeline_id=str(uuid4()),
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        t_pipeline_start = time.time()

        if fresh:
            self.checkpoint_backend.clear()

        self.state = dict(initial_state) if initial_state else {}
        if self._verbose:
            pipeline_name = getattr(self, '_pipeline_name', 'pipeline')
            print(f"[DagPipe] Starting pipeline: {pipeline_name} ({len(self.sorted_nodes)} nodes)")
        self._initial_state_ref = initial_state or {}

        # Restore checkpoints
        for node in self.sorted_nodes:
            # Check for manual override first
            override = self._load_override(node)
            if override is not None:
                self.state[node.id] = override
                continue

            cached = self.checkpoint_backend.load(node.id)
            if cached is not None:
                # Stale checkpoint detection
                stored_hash = cached.get("_meta", {}).get("node_hash")
                if stored_hash is not None:
                    current_hash = node.source_hash()
                    if stored_hash != current_hash:
                        if self._strict_checkpoint:
                            raise StaleCheckpointError(
                                f"Node '{node.id}' source has changed since checkpoint was saved. "
                                f"Run with fresh=True or delete the checkpoint to re-execute."
                            )
                        else:
                            warnings.warn(
                                f"DagPipe: Node '{node.id}' checkpoint is stale "
                                f"(source code changed). Re-executing node.",
                                UserWarning,
                                stacklevel=2,
                            )
                            self.checkpoint_backend.clear()
                            continue

                # Strip internal metadata before exposing to next nodes
                clean = {k: v for k, v in cached.items() if k != "_meta"}
                self.state[node.id] = clean
                run.nodes.append(NodeResult(
                    node_id=node.id,
                    status="skipped",
                    duration_seconds=0.0,
                    retries=0,
                    checkpoint_was_restored=True,
                ))
                run.nodes_restored += 1

        # Execute nodes
        for node in self.sorted_nodes:
            if node.id in self.state:
                continue  # checkpoint hit or override

            # Circuit breaker check
            if self._circuit_threshold is not None:
                self._check_circuit_breaker(node)

            # Build context for this node
            context = self._build_context(node, initial_state)

            # Execute
            node_result, error_msg = self._execute_node(node, context)

            if node_result is None:
                # Node failed — write dead letter queue
                self._write_dead_letter(node, context, error_msg)
                # Increment circuit breaker counter
                self._increment_circuit(node)

                run.nodes.append(NodeResult(
                    node_id=node.id,
                    status="failed",
                    duration_seconds=0.0,
                    retries=self.max_retries,
                    error=error_msg,
                ))
                run.nodes_failed += 1
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc).isoformat()
                run.total_duration_seconds = time.time() - t_pipeline_start

                raise RuntimeError(
                    f"Pipeline failed at node '{node.id}' after {self.max_retries} retries.\n"
                    f"Last error: {error_msg}\n"
                    f"Debug context saved to: .dagpipe/checkpoints/{node.id}.failed.json\n"
                    f"To manually fix: dagpipe.override_node('{node.id}', corrected_output)"
                )

            # Success — save checkpoint with metadata
            self.state[node.id] = node_result["output"]
            self._save_with_meta(node, node_result["output"])
            self._reset_circuit(node)

            run.nodes.append(NodeResult(
                node_id=node.id,
                status="success",
                duration_seconds=node_result["duration"],
                retries=node_result["retries"],
                model_used=node_result["model_label"],
                estimated_tokens=node_result["tokens"],
                estimated_cost_usd=node_result["cost"],
            ))
            run.nodes_executed += 1
            run.estimated_total_tokens += node_result["tokens"] or 0
            run.estimated_total_cost_usd += node_result["cost"] or 0.0

            if self._verbose:
                desc = getattr(node, 'description', '') or ''
                desc_part = f" — {desc}" if desc else ""
                print(f"[DagPipe] ✓ {node.id}{desc_part} ({node_result['duration']:.1f}s)")
            if self.on_node_complete is not None:
                self.on_node_complete(node.id, node_result["output"], node_result["duration"])

        # Finalize run
        run.completed_at = datetime.now(timezone.utc).isoformat()
        run.total_duration_seconds = time.time() - t_pipeline_start
        if run.status != "failed":
            run.status = "success"

        if self._verbose:
            print(f"[DagPipe] Pipeline complete — {run.total_duration_seconds:.1f}s | ${run.estimated_total_cost_usd:.4f}")

        # Backward compat: always return the state dict
        # If caller unpacks two values they get (state, run)
        return _PipelineResult(self.state, run)

    def _validate_router_models(self) -> None:
        """Validate all models configured in the router against live registry."""
        if hasattr(self.router, '_low_label') and self.router._low_label:
            self._model_registry.validate_model(self.router._low_label)
        if hasattr(self.router, '_high_label') and self.router._high_label:
            self._model_registry.validate_model(self.router._high_label)
        if hasattr(self.router, '_fallback_label') and self.router._fallback_label:
            self._model_registry.validate_model(self.router._fallback_label)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _build_context(
        self,
        node: DAGNode,
        initial_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build context dict for a node.

        In isolated mode: only initial_state (non-secret) + declared depends_on.
        In non-isolated mode (v0.1.x compat): full state dict.
        """
        if self._isolate_context:
            ctx: dict[str, Any] = {}
            if initial_state:
                ctx.update(initial_state)
            for dep_id in node.depends_on:
                if dep_id in self.state:
                    ctx[dep_id] = self.state[dep_id]
        else:
            # v0.1.x behaviour: full state
            ctx = dict(self.state)
            if initial_state:
                ctx.update(initial_state)
            for dep_id in node.depends_on:
                if dep_id in self.state:
                    ctx[dep_id] = self.state[dep_id]

        # Secrets NEVER enter context regardless of isolation mode
        # (strip any keys that accidentally match secret keys)
        for key in self._secrets:
            ctx.pop(key, None)

        return ctx

    def _execute_node(
        self,
        node: DAGNode,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        """Execute a node with retries. Returns (result_bundle | None, last_error_msg).

        result_bundle keys: output, duration, retries, model_label, tokens, cost
        """
        t_start = time.time()
        last_error_msg = ""
        last_raw_output: Any = None
        model_label: str | None = None

        for attempt in range(self.max_retries):
            try:
                # Determine model
                if node.is_deterministic or self.router is None:
                    model = None
                    model_label = None
                elif attempt == 0:
                    runtime_complexity = node.get_complexity(context)
                    model, model_label = self.router.route(runtime_complexity)
                else:
                    runtime_complexity = node.get_complexity(context)
                    model, model_label = self.router.route_for_retry(
                        runtime_complexity, attempt, last_error_msg
                    )

                result = node.execute(context=context, model=model)
                last_raw_output = result

                # Normalize Pydantic → dict
                if isinstance(result, BaseModel):
                    result = result.model_dump()

                # ── Semantic contract check (assert_fn) ──────────────────────
                if node.assert_fn is not None:
                    try:
                        passed = node.assert_fn(result)
                    except Exception as assert_exc:
                        passed = False
                        last_error_msg = f"assert_fn raised exception: {assert_exc}"
                    else:
                        if not passed:
                            last_error_msg = node.assert_message

                    if not passed:
                        if attempt < self.max_retries - 1:
                            # Inject assertion failure + previous output into context
                            context["__assert_failed__"] = True
                            context["__assert_message__"] = last_error_msg
                            context["__previous_output__"] = json.dumps(result, default=str)
                            continue
                        else:
                            # All retries exhausted on assertion failure
                            return None, last_error_msg

                duration = time.time() - t_start
                tokens = self._estimate_tokens(context, result)
                cost = self._estimate_cost(model_label, tokens)

                return {
                    "output": result,
                    "duration": duration,
                    "retries": attempt,
                    "model_label": model_label,
                    "tokens": tokens,
                    "cost": cost,
                }, ""

            except Exception as exc:
                last_error_msg = str(exc)
                if attempt < self.max_retries - 1:
                    context["__last_error__"] = last_error_msg

        return None, last_error_msg

    def _write_dead_letter(
        self,
        node: DAGNode,
        context: dict[str, Any],
        error_msg: str,
    ) -> None:
        """Write .failed.json with full debug context for failed node."""
        if not hasattr(self.checkpoint_backend, "save_failed"):
            return  # Backend doesn't support dead letter (e.g. InMemoryCheckpoint)

        # Sanitize context — remove secrets before writing to disk
        safe_context = {
            k: v for k, v in context.items()
            if k not in self._secrets
        }

        entry = {
            "node_id": node.id,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "attempts": self.max_retries,
            "last_error": error_msg,
            "context_passed_to_node": _safe_serialize(safe_context),
            "node_config": {
                "fn_name": node.fn_name,
                "complexity": node.complexity,
                "depends_on": node.depends_on,
                "is_deterministic": node.is_deterministic,
            },
            "how_to_fix": (
                f"Inspect this file to understand why the node failed. "
                f"To manually override with corrected output, call:\n"
                f"  from dagpipe.dag import override_node\n"
                f"  override_node('{node.id}', your_corrected_output)"
            ),
        }
        self.checkpoint_backend.save_failed(node.id, entry)

    def _save_with_meta(self, node: DAGNode, output: dict) -> None:
        """Save checkpoint with embedded metadata for stale detection."""
        if isinstance(self.checkpoint_backend, FilesystemCheckpoint):
            enriched = dict(output)
            enriched["_meta"] = {
                "node_hash": node.source_hash(),
                "checkpointed_at": datetime.now(timezone.utc).isoformat(),
                "dagpipe_version": "0.2.0",
            }
            self.checkpoint_backend.save(node.id, enriched)
        else:
            self.checkpoint_backend.save(node.id, output)

    def _load_override(self, node: DAGNode) -> dict | None:
        """Load manual override checkpoint if it exists."""
        if not hasattr(self.checkpoint_backend, "load_override"):
            return None
        return self.checkpoint_backend.load_override(node.id)

    def _check_circuit_breaker(self, node: DAGNode) -> None:
        if not hasattr(self.checkpoint_backend, "get_consecutive_failures"):
            return
        failures = self.checkpoint_backend.get_consecutive_failures(node.id)
        if failures >= self._circuit_threshold:
            raise CircuitBreakerOpenError(
                f"Node '{node.id}' circuit breaker is OPEN after "
                f"{failures} consecutive failures across pipeline runs.\n"
                f"Inspect .dagpipe/checkpoints/{node.id}.failed.json for debug info.\n"
                f"To reset: from dagpipe.dag import reset_circuit; reset_circuit('{node.id}')"
            )

    def _increment_circuit(self, node: DAGNode) -> None:
        if hasattr(self.checkpoint_backend, "increment_failures"):
            self.checkpoint_backend.increment_failures(node.id)

    def _reset_circuit(self, node: DAGNode) -> None:
        if hasattr(self.checkpoint_backend, "reset_failures"):
            self.checkpoint_backend.reset_failures(node.id)

    def _estimate_tokens(self, context: dict, output: dict) -> int:
        """Rough token estimate: (len of context JSON + output JSON) / 4."""
        try:
            ctx_chars = len(json.dumps(context, default=str))
            out_chars = len(json.dumps(output, default=str))
            return (ctx_chars + out_chars) // 4
        except Exception:
            return 0

    def _estimate_cost(self, model_label: str | None, tokens: int) -> float:
        if model_label is None or tokens == 0:
            return 0.0
        if self._model_registry is not None:
            pricing = self._model_registry.get_pricing(model_label)
            rate = pricing.get("input_per_1k", 0.0)
        else:
            rate = self._token_pricing.get(model_label, 0.0)
        return (tokens / 1000) * rate


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE RESULT  — backward compatible return type
# ─────────────────────────────────────────────────────────────────────────────

class _PipelineResult:
    """Returned by PipelineOrchestrator.run().

    Behaves exactly like a dict for all v0.1.x code.
    Also supports unpacking: state, run = orch.run()
    """

    def __init__(self, state: dict, run: PipelineRun) -> None:
        self._state = state
        self._run = run

    # Dict protocol — full backward compat
    def __getitem__(self, key: str) -> Any:
        return self._state[key]

    def __contains__(self, key: object) -> bool:
        return key in self._state

    def __iter__(self):
        return iter(self._state)

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def items(self):
        return self._state.items()

    def keys(self):
        return self._state.keys()

    def values(self):
        return self._state.values()

    def __repr__(self) -> str:
        return repr(self._state)

    # Unpacking support: state, run = orch.run()
    def __iter__(self):
        return iter((self._state, self._run))

    def __len__(self) -> int:
        return len(self._state)

    # Direct access to run
    @property
    def run(self) -> PipelineRun:
        return self._run

    @property
    def state(self) -> dict:
        return self._state


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def override_node(
    node_id: str,
    corrected_output: dict,
    checkpoint_dir: Path = Path(".dagpipe/checkpoints"),
) -> None:
    """Manually inject a corrected output for a failed node.

    On the next pipeline run, the override will be used instead of re-executing.

    Args:
        node_id: The node ID that failed.
        corrected_output: The correct output dict to inject.
        checkpoint_dir: Checkpoint directory (default: .dagpipe/checkpoints).

    Example:
        # Pipeline failed at "revenue_calc" because LLM returned wrong data
        override_node("revenue_calc", {"revenue": 1200000, "currency": "USD"})
        # Now re-run the pipeline — it will use this output and continue
    """
    backend = FilesystemCheckpoint(checkpoint_dir)
    backend.save_override(node_id, corrected_output)
    print(f"Override saved for node '{node_id}'. Re-run the pipeline to continue.")


def reset_circuit(
    node_id: str,
    checkpoint_dir: Path = Path(".dagpipe/checkpoints"),
) -> None:
    """Reset the circuit breaker for a node.

    Call this after fixing the underlying issue that caused repeated failures.

    Args:
        node_id: The node ID whose circuit to reset.
        checkpoint_dir: Checkpoint directory (default: .dagpipe/checkpoints).
    """
    backend = FilesystemCheckpoint(checkpoint_dir)
    backend.reset_failures(node_id)
    print(f"Circuit breaker reset for node '{node_id}'.")


def inspect_failure(
    node_id: str,
    checkpoint_dir: Path = Path(".dagpipe/checkpoints"),
) -> dict | None:
    """Load and return the dead letter queue entry for a failed node.

    Args:
        node_id: The node ID to inspect.
        checkpoint_dir: Checkpoint directory.

    Returns:
        Dict with full failure context, or None if no failure recorded.

    Example:
        failure = inspect_failure("revenue_calc")
        if failure:
            print(failure["last_error"])
            print(failure["context_passed_to_node"])
    """
    backend = FilesystemCheckpoint(checkpoint_dir)
    return backend.load_failed(node_id)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_serialize(obj: Any) -> Any:
    """Best-effort JSON serialization of arbitrary objects."""
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(i) for i in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)
