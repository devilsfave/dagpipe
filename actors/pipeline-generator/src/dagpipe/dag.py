"""DagPipe — DAG Pipeline Orchestrator

Executes a directed acyclic graph of user-defined functions with
checkpointing, retry, and optional model routing. Generic — knows
nothing about any downstream application.

Usage:
    from dagpipe.dag import PipelineOrchestrator, DAGNode, load_dag

    nodes = [
        DAGNode(id="step1", fn_name="do_research"),
        DAGNode(id="step2", fn_name="write_draft", depends_on=["step1"]),
    ]
    registry = {"do_research": my_research_fn, "write_draft": my_write_fn}
    orch = PipelineOrchestrator(nodes=nodes, node_registry=registry)
    result = orch.run()
"""
import time
import warnings
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from .checkpoints import checkpoint, restore, checkpoint_exists, clear_checkpoints
from .router import ModelRouter


# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT STORAGE PROTOCOL
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class CheckpointStorage(Protocol):
    """Protocol for checkpoint backends.

    Any object that implements save/load/exists/clear can be used as a
    checkpoint backend — filesystem, Redis, S3, in-memory (for testing), etc.
    This is what makes DagPipe safe to deploy in ephemeral environments like
    Smithery, Lambda, and Vercel.
    """
    def save(self, node_id: str, data: dict) -> None: ...
    def load(self, node_id: str) -> Optional[dict]: ...
    def exists(self, node_id: str) -> bool: ...
    def clear(self) -> None: ...


class FilesystemCheckpoint:
    """Default checkpoint backend — wraps existing checkpoints.py. Backward compatible.

    Stores one JSON file per node under `checkpoint_dir`.
    This is the backend used when no custom `checkpoint_backend` is provided.
    """

    def __init__(self, checkpoint_dir: Path) -> None:
        self._dir = checkpoint_dir

    def save(self, node_id: str, data: dict) -> None:
        checkpoint(node_id, data, checkpoint_dir=self._dir)

    def load(self, node_id: str) -> Optional[dict]:
        return restore(node_id, checkpoint_dir=self._dir)

    def exists(self, node_id: str) -> bool:
        return checkpoint_exists(node_id, checkpoint_dir=self._dir)

    def clear(self) -> None:
        clear_checkpoints(checkpoint_dir=self._dir)


# ─────────────────────────────────────────────────────────────────────────────
# DAG NODE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DAGNode:
    """A single node in the execution DAG.

    Attributes:
        id: Unique identifier for this node.
        fn_name: Key into the node_registry dict.
        depends_on: List of node IDs that must complete before this node.
        output_schema: Optional label for the expected output schema.
        complexity: Float 0.0–1.0 used by the router to pick a model.
        is_deterministic: If True, node runs without an LLM (model=None).
        description: Human-readable description of what this node does.
    """
    id: str
    fn_name: str
    depends_on: list[str] = field(default_factory=list)
    output_schema: str = ""
    complexity: float = 0.5
    is_deterministic: bool = False
    description: str = ""

    _fn: Callable | None = field(default=None, repr=False)

    def resolve_fn(self, registry: dict[str, Callable]) -> None:
        """Resolve function name to actual callable from a registry dict.

        Args:
            registry: Mapping of fn_name → callable.

        Raises:
            KeyError: If fn_name is not found in the registry.
        """
        if self.fn_name not in registry:
            raise KeyError(
                f"Node '{self.id}' references function '{self.fn_name}' "
                f"which is not in the node registry."
            )
        self._fn = registry[self.fn_name]

    def execute(self, context: dict[str, Any], model: Any = None) -> Any:
        """Execute this node's function.

        Args:
            context: Dict of upstream node outputs + any injected state.
            model: LLM callable (None for deterministic nodes).

        Returns:
            The node function's return value.

        Raises:
            RuntimeError: If the function has not been resolved yet.
        """
        if self._fn is None:
            raise RuntimeError(
                f"Node '{self.id}' function not resolved. "
                f"Call resolve_fn() first."
            )
        return self._fn(context=context, model=model)


# ─────────────────────────────────────────────────────────────────────────────
# DAG LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_dag(config_path: Path) -> list[DAGNode]:
    """Load DAG configuration from a YAML file.

    Expected YAML format::

        nodes:
          - id: step1
            fn: do_research
            depends_on: []
            complexity: 0.5
            is_deterministic: false
            description: "Research the topic"

    Args:
        config_path: Path to the YAML config file.

    Returns:
        List of DAGNode objects (NOT yet topologically sorted).
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
# TOPOLOGICAL SORT
# ─────────────────────────────────────────────────────────────────────────────

def topological_sort(nodes: list[DAGNode]) -> list[DAGNode]:
    """Sort nodes in dependency order. Raises ValueError on cycles.

    Uses depth-first traversal with cycle detection.

    Args:
        nodes: Unsorted list of DAGNode objects.

    Returns:
        Topologically sorted list of DAGNode objects.

    Raises:
        ValueError: If a cycle is detected or an unknown dependency is found.
    """
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
# PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class PipelineOrchestrator:
    """Executes a DAG of tasks with checkpointing, routing, and retry.

    This is a GENERIC orchestrator. It knows nothing about any specific
    application — it runs user-defined callables in dependency order.

    Args:
        nodes: List of DAGNode objects, or a Path to a YAML config.
        node_registry: Dict mapping fn_name → callable.
        router: Optional ModelRouter for LLM-backed nodes.
            If None, all nodes get model=None (deterministic mode).
        checkpoint_backend: CheckpointStorage implementation to use.
            Defaults to FilesystemCheckpoint(".dagpipe/checkpoints").
            Use any object satisfying CheckpointStorage Protocol — e.g.,
            an in-memory backend for testing, or a Redis backend for cloud.
        checkpoint_dir: DEPRECATED. Pass checkpoint_backend instead.
            Kept for backward compatibility — will be removed in v0.2.0.
        max_retries: Max attempts per node before raising RuntimeError.
        on_node_complete: Optional callback(node_id, result, duration).
    """

    def __init__(
        self,
        nodes: list[DAGNode] | Path,
        node_registry: dict[str, Callable],
        router: ModelRouter | None = None,
        checkpoint_backend: CheckpointStorage | None = None,
        checkpoint_dir: Path | None = None,
        max_retries: int = 3,
        on_node_complete: Callable[..., Any] | None = None,
    ) -> None:
        # Load from YAML if a Path is given
        if isinstance(nodes, Path):
            self._raw_nodes = load_dag(nodes)
        else:
            self._raw_nodes = list(nodes)

        self.sorted_nodes = topological_sort(self._raw_nodes)
        self.state: dict[str, Any] = {}
        self.max_retries = max_retries
        self.router = router
        self.on_node_complete = on_node_complete

        # Resolve checkpoint backend — new API takes precedence.
        # Deprecated checkpoint_dir is wrapped for backward compat.
        if checkpoint_backend is not None:
            self.checkpoint_backend: CheckpointStorage = checkpoint_backend
        elif checkpoint_dir is not None:
            warnings.warn(
                "checkpoint_dir is deprecated and will be removed in v0.2.0. "
                "Use checkpoint_backend=FilesystemCheckpoint(path) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.checkpoint_backend = FilesystemCheckpoint(checkpoint_dir)
        else:
            # Default: filesystem backend at the standard location
            self.checkpoint_backend = FilesystemCheckpoint(
                Path(".dagpipe/checkpoints")
            )

        # Resolve every node's function from the registry
        for node in self.sorted_nodes:
            node.resolve_fn(node_registry)

    def run(
        self,
        initial_state: dict[str, Any] | None = None,
        fresh: bool = False,
    ) -> dict[str, Any]:
        """Execute the full pipeline.

        Args:
            initial_state: Optional dict of values injected before execution.
                Keys are available to all node functions via context.
            fresh: If True, clear all checkpoints before starting.

        Returns:
            Dict of all node outputs keyed by node_id.

        Raises:
            RuntimeError: If any node exhausts all retries.
        """
        if fresh:
            self.checkpoint_backend.clear()

        self.state = dict(initial_state) if initial_state else {}

        # Restore existing checkpoints
        for node in self.sorted_nodes:
            cached = self.checkpoint_backend.load(node.id)
            if cached is not None:
                self.state[node.id] = cached

        # Execute nodes in topological order
        for node in self.sorted_nodes:
            if node.id in self.state:
                continue  # Already completed (checkpoint hit)

            # Build context from dependencies + initial state
            context: dict[str, Any] = {}
            # Include any initial_state keys
            if initial_state:
                context.update(initial_state)
            for dep_id in node.depends_on:
                if dep_id in self.state:
                    context[dep_id] = self.state[dep_id]

            # Execute with retries
            result = self._execute_node(node, context)

            if result is None:
                raise RuntimeError(
                    f"Pipeline failed at node '{node.id}' "
                    f"after {self.max_retries} retries."
                )

            # Store result and checkpoint
            self.state[node.id] = result
            self.checkpoint_backend.save(node.id, result)

        return self.state

    def _execute_node(
        self,
        node: DAGNode,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Execute a single node with retries.

        Args:
            node: The DAGNode to execute.
            context: Assembled context dict for this node.

        Returns:
            Output dict, or None if all retries are exhausted.
        """
        t_start = time.time()
        last_error_msg = ""

        for attempt in range(self.max_retries):
            try:
                # Route to appropriate model
                if node.is_deterministic or self.router is None:
                    model = None
                elif attempt == 0:
                    model, _ = self.router.route(node.complexity)
                else:
                    model, _ = self.router.route_for_retry(
                        node.complexity, attempt, last_error_msg
                    )

                # Execute the node function
                result = node.execute(context=context, model=model)

                # Convert Pydantic model to dict if needed
                if isinstance(result, BaseModel):
                    result = result.model_dump()

                duration = time.time() - t_start

                # Fire callback if provided
                if self.on_node_complete is not None:
                    self.on_node_complete(node.id, result, duration)

                return result

            except Exception as e:
                last_error_msg = str(e)

                if attempt < self.max_retries - 1:
                    # Inject error context for retry
                    context["__last_error__"] = str(e)

        return None  # All retries exhausted
