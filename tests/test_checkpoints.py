"""Tests for dagpipe.checkpoints — checkpoint persistence layer."""
from pathlib import Path

from dagpipe.checkpoints import (
    checkpoint,
    checkpoint_exists,
    clear_checkpoints,
    list_checkpoints,
    restore,
)


def test_checkpoint_saves_file(tmp_path: Path) -> None:
    """checkpoint() creates a JSON file on disk."""
    data = {"result": "hello", "score": 42}
    checkpoint("node_a", data, checkpoint_dir=tmp_path)

    saved = tmp_path / "node_a.json"
    assert saved.exists()
    assert saved.suffix == ".json"


def test_restore_loads_correctly(tmp_path: Path) -> None:
    """restore() returns the exact dict that was checkpointed."""
    original = {"files": [{"filename": "main.py", "code": "print('hi')"}]}
    checkpoint("node_b", original, checkpoint_dir=tmp_path)

    loaded = restore("node_b", checkpoint_dir=tmp_path)
    assert loaded == original


def test_restore_returns_none_when_missing(tmp_path: Path) -> None:
    """restore() returns None for a node that was never checkpointed."""
    result = restore("nonexistent_node", checkpoint_dir=tmp_path)
    assert result is None


def test_checkpoint_exists_returns_true_false(tmp_path: Path) -> None:
    """checkpoint_exists() correctly reflects presence of checkpoint files."""
    assert checkpoint_exists("node_c", checkpoint_dir=tmp_path) is False

    checkpoint("node_c", {"status": "done"}, checkpoint_dir=tmp_path)
    assert checkpoint_exists("node_c", checkpoint_dir=tmp_path) is True


def test_clear_checkpoints_wipes_directory(tmp_path: Path) -> None:
    """clear_checkpoints() removes all .json files in the checkpoint dir."""
    checkpoint("x", {"a": 1}, checkpoint_dir=tmp_path)
    checkpoint("y", {"b": 2}, checkpoint_dir=tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 2

    clear_checkpoints(checkpoint_dir=tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 0


def test_list_checkpoints(tmp_path: Path) -> None:
    """list_checkpoints() returns sorted node IDs."""
    checkpoint("beta", {"v": 1}, checkpoint_dir=tmp_path)
    checkpoint("alpha", {"v": 2}, checkpoint_dir=tmp_path)

    result = list_checkpoints(checkpoint_dir=tmp_path)
    assert result == ["alpha", "beta"]


def test_list_checkpoints_empty(tmp_path: Path) -> None:
    """list_checkpoints() returns [] when dir has no checkpoints."""
    result = list_checkpoints(checkpoint_dir=tmp_path)
    assert result == []


def test_restore_handles_corrupt_json(tmp_path: Path) -> None:
    """restore() returns None (not crash) on corrupt JSON."""
    bad_file = tmp_path / "corrupt.json"
    bad_file.write_text("{this is not json", encoding="utf-8")

    result = restore("corrupt", checkpoint_dir=tmp_path)
    assert result is None
