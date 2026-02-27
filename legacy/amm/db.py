"""AMM Phase 5 — SQLAlchemy Database Layer

SQLite now, PostgreSQL on VPS = change AMM_DATABASE_URL env var.
All direct sqlite3 access in the project should migrate to this module.

Migration to Postgres:
  export AMM_DATABASE_URL=postgresql://user:pass@localhost/amm
  # That's it. No code changes.
"""
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Text, ForeignKey, Boolean,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from .config import AMM_DATABASE_URL


Base = declarative_base()

# ─────────────────────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRun(Base):
    """A single end-to-end pipeline execution (concept → deploy)."""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    concept = Column(Text, nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="RUNNING")  # RUNNING, SUCCESS, FAILED
    result_summary = Column(Text, nullable=True)

    nodes = relationship("NodeExecution", back_populates="pipeline_run")


class NodeExecution(Base):
    """Execution record for a single DAG node within a pipeline run."""
    __tablename__ = "node_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), nullable=False)
    node_id = Column(String(50), nullable=False)
    status = Column(String(20), default="PENDING")  # PENDING, RUNNING, SUCCESS, FAILED, SKIPPED
    output_json = Column(Text, nullable=True)
    model_used = Column(String(100), nullable=True)
    duration_s = Column(Float, nullable=True)
    retries = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    pipeline_run = relationship("PipelineRun", back_populates="nodes")


class CouncilDecision(Base):
    """Record of a council deliberation decision."""
    __tablename__ = "council_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    concept = Column(Text, nullable=False)
    outcome = Column(String(20), nullable=False)  # YES, NO, VETO, FAILED, BUILT
    deepseek_vote = Column(String(10), nullable=True)
    gemini_vote = Column(String(10), nullable=True)
    avg_confidence = Column(Float, nullable=True)
    reasoning_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class StateTransition(Base):
    """Audit log of every FSM state transition."""
    __tablename__ = "state_transitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_state = Column(String(30), nullable=False)
    to_state = Column(String(30), nullable=False)
    trigger = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE + SESSION
# ─────────────────────────────────────────────────────────────────────────────

_engine = create_engine(AMM_DATABASE_URL, echo=False, future=True)
_SessionLocal = sessionmaker(bind=_engine)


def init_db():
    """Create all tables if they don't exist. Safe to call multiple times."""
    Base.metadata.create_all(_engine)


@contextmanager
def get_session():
    """Provide a transactional scope around a series of operations.

    Usage:
        with get_session() as session:
            session.add(PipelineRun(concept="..."))
    """
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    """Return the SQLAlchemy engine for direct use if needed."""
    return _engine


# Auto-init tables on first import — safe to re-run
init_db()
