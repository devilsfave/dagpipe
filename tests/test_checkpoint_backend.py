"""Tests for CheckpointStorage Protocol and FilesystemCheckpoint.

Covers:
- Protocol structural compliance (CheckpointStorage is a runtime_checkable
  Protocol — any object with the right methods satisfies it)
- FilesystemCheckpoint behaves identically to the old checkpoint_dir parameter
- PipelineOrchestrator propagates errors from a broken backend correctly
- Deprecated checkpoint_dir kwarg still works (with DeprecationWarning)
- New checkpoint_backend kwarg works correctly
"""
import warnings
from pathlib import Path
from typing import Any, Optional

import pytest

from dagpipe.dag import (
    CheckpointStorage,
    DAGNode,
    FilesystemCheckpoint,
    PipelineOrchestrator,
)
from dagpipe.checkpoints import checkpoint, restore, checkpoint_exists


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _dummy_research(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    return {"topic": context.get("topic", "default"), "findings": "data"}


def _dummy_write(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    research = context.get("research", {})
    return {"draft": f"Article about {research.get('topic', '?')}"}


class InMemoryCheckpoint:
    """Minimal in-memory CheckpointStorage for testing — no disk I/O."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def save(self, node_id: str, data: dict) -> None:
        self._store[node_id] = data

    def load(self, node_id: str) -> Optional[dict]:
        return self._store.get(node_id)

    def exists(self, node_id: str) -> bool:
        return node_id in self._store

    def clear(self) -> None:
        self._store.clear()


class BrokenCheckpoint:
    """Checkpoint backend that always raises — tests error propagation."""

    def save(self, node_id: str, data: dict) -> None:
        raise OSError("Storage unavailable")

    def load(self, node_id: str) -> Optional[dict]:
        return None  # Don't raise on load — node will execute and then fail on save

    def exists(self, node_id: str) -> bool:
        return False

    def clear(self) -> None:
        raise OSError("Storage unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# TEST: Protocol structural compliance
# ─────────────────────────────────────────────────────────────────────────────

def test_in_memory_checkpoint_satisfies_protocol() -> None:
    """InMemoryCheckpoint must satisfy the CheckpointStorage Protocol."""
    backend = InMemoryCheckpoint()
    assert isinstance(backend, CheckpointStorage)


def test_filesystem_checkpoint_satisfies_protocol(tmp_path: Path) -> None:
    """FilesystemCheckpoint must satisfy the CheckpointStorage Protocol."""
    backend = FilesystemCheckpoint(tmp_path)
    assert isinstance(backend, CheckpointStorage)


# ─────────────────────────────────────────────────────────────────────────────
# TEST: FilesystemCheckpoint behaves identically to old checkpoint_dir behaviour
# ─────────────────────────────────────────────────────────────────────────────

def test_filesystem_checkpoint_save_and_load(tmp_path: Path) -> None:
    """FilesystemCheckpoint.save/load round-trips data correctly."""
    backend = FilesystemCheckpoint(tmp_path)
    data = {"result": "hello", "score": 42}

    backend.save("node_a", data)
    loaded = backend.load("node_a")

    assert loaded == data


def test_filesystem_checkpoint_exists(tmp_path: Path) -> None:
    """FilesystemCheckpoint.exists reflects what was saved."""
    backend = FilesystemCheckpoint(tmp_path)

    assert backend.exists("node_b") is False
    backend.save("node_b", {"v": 1})
    assert backend.exists("node_b") is True


def test_filesystem_checkpoint_clear(tmp_path: Path) -> None:
    """FilesystemCheckpoint.clear removes all saved checkpoints."""
    backend = FilesystemCheckpoint(tmp_path)
    backend.save("x", {"a": 1})
    backend.save("y", {"b": 2})

    backend.clear()

    assert backend.exists("x") is False
    assert backend.exists("y") is False


def test_filesystem_checkpoint_load_missing_returns_none(tmp_path: Path) -> None:
    """FilesystemCheckpoint.load returns None for unsaved nodes."""
    backend = FilesystemCheckpoint(tmp_path)
    assert backend.load("nonexistent") is None


# ─────────────────────────────────────────────────────────────────────────────
# TEST: PipelineOrchestrator with custom checkpoint_backend
# ─────────────────────────────────────────────────────────────────────────────

def test_orchestrator_uses_custom_backend() -> None:
    """Orchestrator persists results in the provided custom backend."""
    backend = InMemoryCheckpoint()
    nodes = [DAGNode(id="research", fn_name="do_research")]
    registry = {"do_research": _dummy_research}

    orch = PipelineOrchestrator(
        nodes=nodes,
        node_registry=registry,
        checkpoint_backend=backend,
    )
    orch.run(initial_state={"topic": "DagPipe"})

    assert backend.exists("research")
    saved = backend.load("research")
    assert saved is not None
    assert saved["topic"] == "DagPipe"


def test_orchestrator_restores_from_custom_backend() -> None:
    """Orchestrator skips nodes that already exist in the custom backend."""
    call_count: dict[str, int] = {"research": 0}

    def counting_research(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
        call_count["research"] += 1
        return {"data": "fresh"}

    backend = InMemoryCheckpoint()
    nodes = [DAGNode(id="research", fn_name="do_research")]
    registry = {"do_research": counting_research}

    # First run — executes and saves
    orch1 = PipelineOrchestrator(
        nodes=nodes, node_registry=registry, checkpoint_backend=backend
    )
    orch1.run()
    assert call_count["research"] == 1

    # Second run — restores from backend, should not call the function
    orch2 = PipelineOrchestrator(
        nodes=nodes, node_registry=registry, checkpoint_backend=backend
    )
    orch2.run()
    assert call_count["research"] == 1  # NOT incremented


def test_orchestrator_propagates_backend_error() -> None:
    """RuntimeError raised when checkpoint backend raises on save."""
    backend = BrokenCheckpoint()
    nodes = [DAGNode(id="node1", fn_name="do_research")]
    registry = {"do_research": _dummy_research}

    orch = PipelineOrchestrator(
        nodes=nodes,
        node_registry=registry,
        checkpoint_backend=backend,
    )
    with pytest.raises(OSError, match="Storage unavailable"):
        orch.run()


def test_orchestrator_fresh_run_clears_backend() -> None:
    """fresh=True calls backend.clear() before executing nodes."""
    backend = InMemoryCheckpoint()
    # Pre-populate the backend
    backend.save("research", {"data": "old"})

    call_count: dict[str, int] = {"research": 0}

    def counting_research(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
        call_count["research"] += 1
        return {"data": "fresh"}

    nodes = [DAGNode(id="research", fn_name="do_research")]
    registry = {"do_research": counting_research}

    orch = PipelineOrchestrator(
        nodes=nodes, node_registry=registry, checkpoint_backend=backend
    )
    orch.run(fresh=True)

    # Node must have been re-executed (backend was cleared before run)
    assert call_count["research"] == 1
    assert backend.load("research") == {"data": "fresh"}


# ─────────────────────────────────────────────────────────────────────────────
# TEST: Deprecated checkpoint_dir still works with DeprecationWarning
# ─────────────────────────────────────────────────────────────────────────────

def test_deprecated_checkpoint_dir_emits_warning(tmp_path: Path) -> None:
    """Passing checkpoint_dir raises DeprecationWarning."""
    nodes = [DAGNode(id="research", fn_name="do_research")]
    registry = {"do_research": _dummy_research}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PipelineOrchestrator(
            nodes=nodes,
            node_registry=registry,
            directory=tmp_path / "ckpt",
        )

    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep_warnings) == 1
    assert "checkpoint_dir is deprecated" in str(dep_warnings[0].message)


def test_deprecated_checkpoint_dir_still_persists(tmp_path: Path) -> None:
    """Deprecated checkpoint_dir path still stores checkpoints on disk."""
    ckpt_dir = tmp_path / "ckpt"
    nodes = [DAGNode(id="research", fn_name="do_research")]
    registry = {"do_research": _dummy_research}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry=registry,
            directory=ckpt_dir,
        )
    orch.run()

    # File must exist on disk — backward compat is preserved
    assert checkpoint_exists("research", directory=ckpt_dir)
