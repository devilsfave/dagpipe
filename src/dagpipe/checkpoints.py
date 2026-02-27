"""DagPipe — Checkpoint Persistence

Saves validated node output to disk as JSON after each successful node.
On resume, completed nodes are skipped — never restart from scratch.

Checkpoints stored in: {checkpoint_dir}/{node_id}.json
"""
import json
from pathlib import Path

_DEFAULT_CHECKPOINT_DIR = Path(".dagpipe/checkpoints")


def _checkpoint_path(
    node_id: str,
    checkpoint_dir: Path = _DEFAULT_CHECKPOINT_DIR,
) -> Path:
    """Return the checkpoint file path for a node."""
    return checkpoint_dir / f"{node_id}.json"


def checkpoint(
    node_id: str,
    output: dict,
    checkpoint_dir: Path = _DEFAULT_CHECKPOINT_DIR,
) -> None:
    """Save validated node output to disk.

    Args:
        node_id: DAG node identifier (e.g. "pm_spec", "write_db")
        output: Validated output dict (already passed Pydantic schema)
        checkpoint_dir: Directory to store checkpoint files
    """
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    path = _checkpoint_path(node_id, checkpoint_dir)
    path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def restore(
    node_id: str,
    checkpoint_dir: Path = _DEFAULT_CHECKPOINT_DIR,
) -> dict | None:
    """Load checkpoint for a node.

    Args:
        node_id: DAG node identifier
        checkpoint_dir: Directory where checkpoint files are stored

    Returns:
        Output dict if checkpoint exists, None otherwise.
    """
    path = _checkpoint_path(node_id, checkpoint_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def checkpoint_exists(
    node_id: str,
    checkpoint_dir: Path = _DEFAULT_CHECKPOINT_DIR,
) -> bool:
    """Check if a checkpoint exists for the given node.

    Args:
        node_id: DAG node identifier
        checkpoint_dir: Directory where checkpoint files are stored
    """
    return _checkpoint_path(node_id, checkpoint_dir).exists()


def clear_checkpoints(
    checkpoint_dir: Path = _DEFAULT_CHECKPOINT_DIR,
) -> None:
    """Wipe all checkpoints for a fresh pipeline run.

    Args:
        checkpoint_dir: Directory to clear checkpoint files from
    """
    if checkpoint_dir.exists():
        for f in checkpoint_dir.glob("*.json"):
            f.unlink()


def list_checkpoints(
    checkpoint_dir: Path = _DEFAULT_CHECKPOINT_DIR,
) -> list[str]:
    """Return list of node IDs that have saved checkpoints.

    Args:
        checkpoint_dir: Directory where checkpoint files are stored
    """
    if not checkpoint_dir.exists():
        return []
    return sorted(f.stem for f in checkpoint_dir.glob("*.json"))
