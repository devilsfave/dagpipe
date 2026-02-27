"""AMM Phase 5 — Central Configuration

All paths and settings resolved from environment variables with sane defaults.
Portable across Windows (current dev) and Linux (target VPS).

To migrate to Linux VPS:
  export AMM_WORKSPACE=/opt/amm/workspace/skills
  export AMM_DATABASE_URL=postgresql://user:pass@localhost/amm
"""
from pathlib import Path
import os

# ─────────────────────────────────────────────────────────────────────────────
# PATHS — all derived from AMM_WORKSPACE, never hardcoded
# ─────────────────────────────────────────────────────────────────────────────

AMM_WORKSPACE = Path(os.environ.get(
    "AMM_WORKSPACE",
    str(Path.home() / ".nanobot" / "workspace" / "skills")
))

# Checkpoint directory — node-level save/restore
AMM_CHECKPOINT_DIR = AMM_WORKSPACE / "checkpoints"

# SOUL files directory — machine-readable agent job descriptions
AMM_SOULS_DIR = Path(__file__).parent / "souls"

# DAG config — explicit task dependency graph
AMM_DAG_CONFIG = Path(__file__).parent / "dag_config.yaml"

# Output directory for MVP builds
AMM_BUILD_OUTPUT_DIR = AMM_WORKSPACE.parent / "mvps" / "current_build"

# State file — backward compat with council_state.json
AMM_STATE_FILE = AMM_WORKSPACE / "council_state.json"

# CrewAI memory storage (used by legacy --legacy flag)
AMM_CREWAI_MEMORY_DIR = AMM_WORKSPACE.parent / "crewai_memory"

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE — SQLite now, Postgres on VPS = one env var change
# ─────────────────────────────────────────────────────────────────────────────

AMM_DATABASE_URL = os.environ.get(
    "AMM_DATABASE_URL",
    f"sqlite:///{AMM_WORKSPACE / 'amm.db'}"
)

# ─────────────────────────────────────────────────────────────────────────────
# FEATURE FLAGS
# ─────────────────────────────────────────────────────────────────────────────

# Memory backend: "chroma" (current), future: "qdrant", "pgvector"
AMM_MEMORY_BACKEND = os.environ.get("AMM_MEMORY_BACKEND", "chroma")

# Constrained generation: "pydantic_retry" (safe default), "outlines" (token-level)
AMM_CONSTRAINED_MODE = os.environ.get("AMM_CONSTRAINED_MODE", "pydantic_retry")
