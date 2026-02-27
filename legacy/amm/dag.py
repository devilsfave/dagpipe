"""AMM Phase 5 — DAG Pipeline Orchestrator

Replaces CrewAI's Crew(process=Process.sequential) with a Python-driven
DAG walker. Python defines the graph, drives the machine, validates output.
The LLM fills in blanks — schema-constrained, context-bounded, checkpoint-backed.

Usage:
    from amm.dag import PipelineOrchestrator
    orchestrator = PipelineOrchestrator()
    result = orchestrator.run("Build a coffee shop landing page")
"""
import json
import time
import importlib
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any, Type
from datetime import datetime, timezone

from pydantic import BaseModel

from .config import AMM_DAG_CONFIG, AMM_BUILD_OUTPUT_DIR
from .checkpoints import checkpoint, restore, checkpoint_exists, clear_checkpoints
from .router import route_task, route_for_retry
from .schemas import SCHEMA_REGISTRY
from .db import get_session, PipelineRun, NodeExecution


# ─────────────────────────────────────────────────────────────────────────────
# DAG NODE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DAGNode:
    """A single node in the execution DAG."""
    id: str
    fn_name: str                                    # Function name in nodes.py
    depends_on: list[str] = field(default_factory=list)
    output_schema: str = ""                         # Key in SCHEMA_REGISTRY
    complexity: float = 0.5
    is_deterministic: bool = False                  # No LLM — pure Python
    description: str = ""

    _fn: Callable | None = field(default=None, repr=False)

    def resolve_fn(self, nodes_module) -> None:
        """Resolve function name to actual callable from nodes module."""
        if not hasattr(nodes_module, self.fn_name):
            raise AttributeError(
                f"Node '{self.id}' references function '{self.fn_name}' "
                f"which does not exist in nodes module."
            )
        self._fn = getattr(nodes_module, self.fn_name)

    def execute(self, context: dict, model=None) -> Any:
        """Execute this node's function."""
        if self._fn is None:
            raise RuntimeError(f"Node '{self.id}' function not resolved. Call resolve_fn() first.")
        return self._fn(context=context, model=model)

    def get_schema(self) -> Type[BaseModel] | None:
        """Look up the Pydantic schema for this node's output."""
        if not self.output_schema:
            return None
        return SCHEMA_REGISTRY.get(self.output_schema)


# ─────────────────────────────────────────────────────────────────────────────
# DAG LOADING + TOPOLOGICAL SORT
# ─────────────────────────────────────────────────────────────────────────────

def load_dag(config_path: Path | None = None) -> list[DAGNode]:
    """Load DAG configuration from YAML.

    Args:
        config_path: Path to dag_config.yaml. Defaults to AMM_DAG_CONFIG.

    Returns:
        List of DAGNode objects (NOT yet topologically sorted).
    """
    path = config_path or AMM_DAG_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    nodes = []
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


def topological_sort(nodes: list[DAGNode]) -> list[DAGNode]:
    """Sort nodes in dependency order. Raises ValueError on cycles.

    Uses depth-first traversal with cycle detection.
    """
    node_map = {n.id: n for n in nodes}
    visited: set[str] = set()
    visiting: set[str] = set()  # For cycle detection
    order: list[DAGNode] = []

    def visit(node_id: str):
        if node_id in visiting:
            raise ValueError(f"Cycle detected involving node: {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)

    # Note: The logic in the original file was truncated at 400 lines but I should ensure it's complete.
    # Actually, the file was 400 lines total and I read all 400 lines.
    # Re-writing the topological_sort from the read content.
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
    """Executes a DAG of tasks with checkpointing, routing, and validation.

    This is the Phase 5 replacement for CrewAI's Crew class.
    """

    def __init__(self, dag_config_path: Path | None = None, max_retries: int = 3):
        self.nodes = load_dag(dag_config_path)
        self.sorted_nodes = topological_sort(self.nodes)
        self.state: dict[str, Any] = {}  # node_id → validated output
        self.max_retries = max_retries

        # Resolve node functions from nodes module
        try:
            nodes_module = importlib.import_module(".nodes", package="amm")
            for node in self.sorted_nodes:
                node.resolve_fn(nodes_module)
        except (ImportError, AttributeError) as e:
            print(f"[DAG] WARNING: Could not resolve node functions: {e}")
            print("[DAG] Node functions will be resolved lazily at execution time.")

    def run(self, concept: str, fresh: bool = False) -> dict:
        """Execute the full pipeline for a given concept.

        Args:
            concept: Text description of what to build.
            fresh: If True, clear all checkpoints before starting.

        Returns:
            Dict of all node outputs keyed by node_id.
        """
        if fresh:
            clear_checkpoints()
            # FIX 2: Wipe build output directory so previous runs don't conflict
            import shutil
            if AMM_BUILD_OUTPUT_DIR.exists():
                shutil.rmtree(AMM_BUILD_OUTPUT_DIR, ignore_errors=True)

        print("\n" + "=" * 60)
        print("🚀 AMM DAG ORCHESTRATOR — Starting Pipeline")
        print("=" * 60)
        print(f"📋 Concept: {concept}")
        print(f"📊 Nodes: {len(self.sorted_nodes)}")
        print("=" * 60)

        # Ensure output directory exists
        AMM_BUILD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Create pipeline run in DB
        run_id = self._create_run(concept)

        # Inject concept into initial state
        self.state["__concept__"] = concept

        # Fetch live versions
        try:
            from amm.version_fetcher import fetch
            import re
            stack_match = re.search(r'\*\*TECH STACK\*\*:\s*([^\n]+)', concept, re.IGNORECASE)
            if stack_match:
                stack_raw = stack_match.group(1)
                stack_list = [s.strip() for s in re.split(r'[,(]', stack_raw) if s.strip()]
            else:
                stack_list = ["Next.js", "React", "Node.js", "TailwindCSS", "Prisma", "PostgreSQL", "Auth.js"]
                
            print(f"  🔍 Fetching live package versions...")
            versions = fetch(stack_list)
            
            if versions:
                v_str = ", ".join([f"{k}={v}" for k, v in versions.items()])
                self.state["__live_versions__"] = f"VERIFIED CURRENT VERSIONS (use these exactly, ignore your training data): {v_str}"
            else:
                self.state["__live_versions__"] = ""
        except Exception as e:
            print(f"  ⚠️  Version fetcher failed: {e}")
            self.state["__live_versions__"] = ""

        # Restore any existing checkpoints
        restored = 0
        for node in self.sorted_nodes:
            cached = restore(node.id)
            if cached is not None:
                self.state[node.id] = cached
                restored += 1
        if restored:
            print(f"  ♻️  Restored {restored} checkpoints")

        # Execute nodes in topological order
        pipeline_start = time.time()
        for node in self.sorted_nodes:
            if node.id in self.state:
                print(f"  ⏭️  {node.id}: already complete (checkpoint)")
                continue

            # Gather context from dependencies
            context = {"concept": concept}
            if "__live_versions__" in self.state:
                context["live_versions"] = self.state["__live_versions__"]
                
            for dep_id in node.depends_on:
                if dep_id in self.state:
                    context[dep_id] = self.state[dep_id]

            # Execute with retries
            result = self._execute_node(node, context, run_id)

            if result is None:
                self._finish_run(
                    run_id, "FAILED",
                    f"Node '{node.id}' failed after {self.max_retries} retries"
                )
                raise RuntimeError(
                    f"Pipeline failed at node: {node.id}. "
                    f"Run `python -m amm.checkpoints` to see saved progress."
                )

            # Store result and checkpoint
            self.state[node.id] = result
            checkpoint(node.id, result)
            print(f"  💾 {node.id}: checkpointed")

        # Pipeline complete
        pipeline_duration = time.time() - pipeline_start
        self._finish_run(run_id, "SUCCESS", "All nodes completed")

        print("\n" + "=" * 60)
        print(f"✅ PIPELINE COMPLETE ({pipeline_duration:.1f}s)")
        print("=" * 60)

        return self.state

    def _execute_node(
        self, node: DAGNode, context: dict, run_id: int
    ) -> dict | None:
        """Execute a single node with retries.

        Returns output dict or None on exhausted retries.
        """
        t_start = time.time()
        ts = datetime.now().strftime("%H:%M:%S")
        det_label = " [DETERMINISTIC]" if node.is_deterministic else ""
        print(f"\n[{ts}] 🟢 {node.id}{det_label} — {node.description}")

        model_name = "unknown"
        last_error_msg = ""
        for attempt in range(self.max_retries):
            try:
                # Route to appropriate model
                if node.is_deterministic:
                    model, model_name = None, "deterministic"
                elif attempt == 0:
                    model, model_name = route_task(node.complexity)
                else:
                    model, model_name = route_for_retry(node.complexity, attempt, last_error_msg)

                print(f"  📡 Model: {model_name} | Attempt: {attempt + 1}/{self.max_retries}")

                # Execute the node function
                result = node.execute(context=context, model=model)

                # Convert Pydantic model to dict if needed
                if isinstance(result, BaseModel):
                    result = result.model_dump()

                duration = time.time() - t_start
                self._log_node(
                    run_id, node.id, "SUCCESS", result,
                    model_name, duration, attempt
                )
                print(f"  ✅ {node.id} complete ({duration:.1f}s)")
                return result

            except Exception as e:
                last_error_msg = str(e)
                duration = time.time() - t_start
                print(f"  ❌ {node.id} failed (attempt {attempt + 1}): {e}")
                self._log_node(
                    run_id, node.id, "FAILED", None,
                    model_name, duration, attempt, str(e)
                )

                if attempt < self.max_retries - 1:
                    # Inject error context for retry
                    context["__last_error__"] = str(e)

        return None  # All retries exhausted

    # ── DB LOGGING ──────────────────────────────────────────────────────────

    def _create_run(self, concept: str) -> int:
        """Create a PipelineRun record, return its ID."""
        try:
            with get_session() as session:
                run = PipelineRun(concept=concept)
                session.add(run)
                session.flush()
                return run.id
        except Exception as e:
            print(f"  ⚠️ DB: Could not create pipeline run: {e}")
            return -1

    def _finish_run(self, run_id: int, status: str, summary: str):
        """Mark a PipelineRun as finished."""
        if run_id < 0:
            return
        try:
            with get_session() as session:
                run = session.get(PipelineRun, run_id)
                if run:
                    run.status = status
                    run.result_summary = summary
                    run.finished_at = datetime.now(timezone.utc)
        except Exception as e:
            print(f"  ⚠️ DB: Could not finish pipeline run: {e}")

    def _log_node(
        self, run_id, node_id, status, output,
        model, duration, retries, error=None
    ):
        """Log a NodeExecution record."""
        if run_id < 0:
            return
        try:
            with get_session() as session:
                session.add(NodeExecution(
                    pipeline_run_id=run_id,
                    node_id=node_id,
                    status=status,
                    output_json=json.dumps(output) if output else None,
                    model_used=model,
                    duration_s=duration,
                    retries=retries,
                    started_at=datetime.now(timezone.utc),
                    error_message=error,
                ))
        except Exception as e:
            print(f"  ⚠️ DB: Could not log node execution: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AMM DAG Pipeline Orchestrator")
    parser.add_argument("--concept", required=True, help="Concept to build")
    parser.add_argument("--fresh", action="store_true", help="Clear checkpoints before running")
    parser.add_argument("--dag-config", default=None, help="Path to dag_config.yaml")

    args = parser.parse_args()

    config_path = Path(args.dag_config) if args.dag_config else None
    orchestrator = PipelineOrchestrator(dag_config_path=config_path)
    result = orchestrator.run(args.concept, fresh=args.fresh)

    print("\n📊 FINAL STATE:")
    for node_id, output in result.items():
        if node_id.startswith("__"):
            continue
        print(f"  {node_id}: {'✅ OK' if output else '❌ FAILED'}")
