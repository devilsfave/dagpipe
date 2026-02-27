"""AMM Phase 5 — Checkpoint Persistence

Saves validated node output to disk as JSON after each successful node.
On resume, completed nodes are skipped — never restart from scratch.
Replaces the --reset --force workaround in phase4d_watcher.py.

Checkpoints stored in: $AMM_WORKSPACE/checkpoints/{node_id}.json
"""
import json
from pathlib import Path

from .config import AMM_CHECKPOINT_DIR


def _checkpoint_path(node_id: str) -> Path:
    """Return the checkpoint file path for a node."""
    return AMM_CHECKPOINT_DIR / f"{node_id}.json"


def checkpoint(node_id: str, output: dict) -> None:
    """Save validated node output to disk.

    Args:
        node_id: DAG node identifier (e.g. "pm_spec", "write_db")
        output: Validated output dict (already passed Pydantic schema)
    """
    AMM_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = _checkpoint_path(node_id)
    path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def restore(node_id: str) -> dict | None:
    """Load checkpoint for a node.

    Returns:
        Output dict if checkpoint exists, None otherwise.
    """
    path = _checkpoint_path(node_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Phase 5 Checkpoint formatting compatibility
        if "filename" in data and "code" in data:
            data["files"] = [{"filename": data.pop("filename"), "code": data.pop("code")}]
        return data
    except (json.JSONDecodeError, OSError):
        return None


def checkpoint_exists(node_id: str) -> bool:
    """Check if a checkpoint exists for the given node."""
    return _checkpoint_path(node_id).exists()


def clear_checkpoints() -> None:
    """Wipe all checkpoints for a fresh pipeline run."""
    if AMM_CHECKPOINT_DIR.exists():
        for f in AMM_CHECKPOINT_DIR.glob("*.json"):
            f.unlink()
        print(f"   ✓ Cleared {AMM_CHECKPOINT_DIR}")


def list_checkpoints() -> list[str]:
    """Return list of node IDs that have saved checkpoints."""
    if not AMM_CHECKPOINT_DIR.exists():
        return []
    return sorted(f.stem for f in AMM_CHECKPOINT_DIR.glob("*.json"))


if __name__ == "__main__":
    # Quick inspection tool
    cps = list_checkpoints()
    if cps:
        print(f"Checkpoints ({len(cps)}):")
        for cp in cps:
            print(f"  ✓ {cp}")
    else:
        print("No checkpoints found.")
