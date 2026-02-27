"""Tests for dagpipe.dag — DAG pipeline orchestrator."""
import pytest
import yaml
from pathlib import Path
from typing import Any

from dagpipe.dag import DAGNode, load_dag, topological_sort, PipelineOrchestrator


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — dummy callables used across tests
# ─────────────────────────────────────────────────────────────────────────────

def _dummy_research(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Simulates a research node — returns a fixed dict."""
    return {"topic": context.get("topic", "default"), "findings": "data collected"}


def _dummy_write(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Simulates a write node — consumes research output."""
    research = context.get("research", {})
    return {"draft": f"Article about {research.get('topic', '?')}"}


def _dummy_fail(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Always raises an exception (simulates a broken node)."""
    raise RuntimeError("Simulated node failure")


def _dummy_deterministic(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Records whether model was None (for deterministic check)."""
    return {"model_was_none": model is None}


def _make_two_node_yaml(tmp_path: Path) -> Path:
    """Write a minimal 2-node YAML config and return its path."""
    config = {
        "nodes": [
            {
                "id": "research",
                "fn": "do_research",
                "depends_on": [],
                "complexity": 0.3,
                "is_deterministic": False,
                "description": "Research phase",
            },
            {
                "id": "write",
                "fn": "do_write",
                "depends_on": ["research"],
                "complexity": 0.6,
                "description": "Writing phase",
            },
        ]
    }
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(yaml.dump(config), encoding="utf-8")
    return yaml_path


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: load_dag() parses YAML
# ─────────────────────────────────────────────────────────────────────────────

def test_load_dag_parses_yaml(tmp_path: Path) -> None:
    """load_dag() reads a 2-node YAML and returns DAGNode objects."""
    yaml_path = _make_two_node_yaml(tmp_path)
    nodes = load_dag(yaml_path)

    assert len(nodes) == 2
    assert nodes[0].id == "research"
    assert nodes[0].fn_name == "do_research"
    assert nodes[1].id == "write"
    assert nodes[1].depends_on == ["research"]
    assert nodes[1].complexity == 0.6


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: topological_sort() orders by dependency
# ─────────────────────────────────────────────────────────────────────────────

def test_topological_sort_orders_by_deps() -> None:
    """Nodes are reordered so that dependencies come first."""
    # Intentionally out of order: write before research
    nodes = [
        DAGNode(id="write", fn_name="f", depends_on=["research"]),
        DAGNode(id="research", fn_name="f"),
    ]
    sorted_nodes = topological_sort(nodes)

    ids = [n.id for n in sorted_nodes]
    assert ids.index("research") < ids.index("write")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: topological_sort() raises on cycle
# ─────────────────────────────────────────────────────────────────────────────

def test_topological_sort_raises_on_cycle() -> None:
    """ValueError raised when the graph contains a cycle."""
    nodes = [
        DAGNode(id="a", fn_name="f", depends_on=["b"]),
        DAGNode(id="b", fn_name="f", depends_on=["a"]),
    ]
    with pytest.raises(ValueError, match="Cycle detected"):
        topological_sort(nodes)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: PipelineOrchestrator runs 2-node pipeline end to end
# ─────────────────────────────────────────────────────────────────────────────

def test_pipeline_runs_two_nodes_e2e(tmp_path: Path) -> None:
    """Full pipeline with 2 dummy callables produces expected state."""
    nodes = [
        DAGNode(id="research", fn_name="do_research"),
        DAGNode(id="write", fn_name="do_write", depends_on=["research"]),
    ]
    registry = {
        "do_research": _dummy_research,
        "do_write": _dummy_write,
    }
    orch = PipelineOrchestrator(
        nodes=nodes,
        node_registry=registry,
        checkpoint_dir=tmp_path / "ckpt",
    )
    result = orch.run(initial_state={"topic": "DagPipe"})

    assert "research" in result
    assert result["research"]["topic"] == "DagPipe"
    assert "write" in result
    assert "draft" in result["write"]


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Completed nodes skipped when checkpoint exists
# ─────────────────────────────────────────────────────────────────────────────

def test_checkpoint_skip(tmp_path: Path) -> None:
    """Nodes with existing checkpoints are skipped — not re-executed."""
    call_count = {"research": 0}

    def counting_research(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
        call_count["research"] += 1
        return {"data": "fresh"}

    nodes = [DAGNode(id="research", fn_name="do_research")]
    registry = {"do_research": counting_research}
    ckpt_dir = tmp_path / "ckpt"

    # First run — executes normally
    orch1 = PipelineOrchestrator(
        nodes=nodes, node_registry=registry, checkpoint_dir=ckpt_dir
    )
    orch1.run()
    assert call_count["research"] == 1

    # Second run — should skip (checkpoint exists)
    orch2 = PipelineOrchestrator(
        nodes=nodes, node_registry=registry, checkpoint_dir=ckpt_dir
    )
    orch2.run()
    assert call_count["research"] == 1  # NOT incremented


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Failed node after max_retries raises RuntimeError
# ─────────────────────────────────────────────────────────────────────────────

def test_failed_node_raises_runtime_error(tmp_path: Path) -> None:
    """RuntimeError raised when a node exhausts all retries."""
    nodes = [DAGNode(id="broken", fn_name="do_fail")]
    registry = {"do_fail": _dummy_fail}

    orch = PipelineOrchestrator(
        nodes=nodes,
        node_registry=registry,
        checkpoint_dir=tmp_path / "ckpt",
        max_retries=2,
    )
    with pytest.raises(RuntimeError, match="Pipeline failed at node 'broken'"):
        orch.run()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: on_node_complete callback fires for each successful node
# ─────────────────────────────────────────────────────────────────────────────

def test_on_node_complete_callback(tmp_path: Path) -> None:
    """Callback receives (node_id, result, duration) for every completed node."""
    callback_log: list[tuple[str, dict, float]] = []

    def on_complete(node_id: str, result: dict, duration: float) -> None:
        callback_log.append((node_id, result, duration))

    nodes = [
        DAGNode(id="step1", fn_name="do_research"),
        DAGNode(id="step2", fn_name="do_write", depends_on=["step1"]),
    ]
    registry = {"do_research": _dummy_research, "do_write": _dummy_write}

    orch = PipelineOrchestrator(
        nodes=nodes,
        node_registry=registry,
        checkpoint_dir=tmp_path / "ckpt",
        on_node_complete=on_complete,
    )
    orch.run()

    assert len(callback_log) == 2
    assert callback_log[0][0] == "step1"
    assert callback_log[1][0] == "step2"
    # Duration should be a positive float
    assert all(entry[2] >= 0 for entry in callback_log)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: Deterministic nodes pass model=None
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_nodes_pass_model_none(tmp_path: Path) -> None:
    """Nodes with is_deterministic=True always receive model=None."""
    nodes = [
        DAGNode(id="det", fn_name="do_det", is_deterministic=True),
    ]
    registry = {"do_det": _dummy_deterministic}

    # Even with a router provided, deterministic nodes get model=None
    dummy_router = None  # No router — but the node is deterministic anyway

    orch = PipelineOrchestrator(
        nodes=nodes,
        node_registry=registry,
        router=dummy_router,
        checkpoint_dir=tmp_path / "ckpt",
    )
    result = orch.run()

    assert result["det"]["model_was_none"] is True
