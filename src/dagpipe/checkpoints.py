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
    directory: Path = _DEFAULT_CHECKPOINT_DIR,
) -> Path:
    """Return the checkpoint file path for a node."""
    return directory / f"{node_id}.json"


def checkpoint(
    node_id: str,
    output: dict,
    directory: Path = _DEFAULT_CHECKPOINT_DIR,
) -> None:
    """Save validated node output to disk.

    Args:
        node_id: DAG node identifier (e.g. "pm_spec", "write_db")
        output: Validated output dict (already passed Pydantic schema)
        directory: Directory to store checkpoint files
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = _checkpoint_path(node_id, directory)
    path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def restore(
    node_id: str,
    directory: Path = _DEFAULT_CHECKPOINT_DIR,
) -> dict | None:
    """Load checkpoint for a node.

    Args:
        node_id: DAG node identifier
        directory: Directory where checkpoint files are stored

    Returns:
        Output dict if checkpoint exists, None otherwise.
    """
    path = _checkpoint_path(node_id, directory)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def checkpoint_exists(
    node_id: str,
    directory: Path = _DEFAULT_CHECKPOINT_DIR,
) -> bool:
    """Check if a checkpoint exists for the given node.

    Args:
        node_id: DAG node identifier
        directory: Directory where checkpoint files are stored
    """
    return _checkpoint_path(node_id, directory).exists()


def clear_checkpoints(
    directory: Path = _DEFAULT_CHECKPOINT_DIR,
) -> None:
    """Wipe all checkpoints for a fresh pipeline run.

    Args:
        directory: Directory to clear checkpoint files from
    """
    if directory.exists():
        for f in directory.glob("*.json"):
            f.unlink()


def list_checkpoints(
    directory: Path = _DEFAULT_CHECKPOINT_DIR,
) -> list[str]:
    """Return list of node IDs that have saved checkpoints.

    Args:
        directory: Directory where checkpoint files are stored
    """
    if not directory.exists():
        return []
    return sorted(f.stem for f in directory.glob("*.json"))
