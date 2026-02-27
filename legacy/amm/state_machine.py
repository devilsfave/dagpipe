"""AMM Phase 5 — Hierarchical State Machine

Replaces manual JSON manipulation in council_state.py with a proper FSM.
Critical rule: LLM cannot trigger transitions directly — Python drives the machine.

The FSM persists to council_state.json for backward compatibility with
gemini_bot.py and phase4d_watcher.py. Those callers do NOT need to change.
"""
import json
from enum import Enum, auto
from datetime import datetime, timezone

from .config import AMM_STATE_FILE
from .db import get_session, StateTransition


# ─────────────────────────────────────────────────────────────────────────────
# STATE ENUM
# ─────────────────────────────────────────────────────────────────────────────

class AMMState(Enum):
    IDLE                = auto()  # Waiting for 8am cron
    MONITORING          = auto()  # Monitors running
    SCORING             = auto()  # Scorer running
    COUNCIL_DELIBERATING = auto() # Multi-LLM council active
    AWAITING_HERBERT    = auto()  # Confidence < 85% → Herbert notified
    BUILDING            = auto()  # DAG executor running
    VALIDATING          = auto()  # Tests + linting
    REPAIRING           = auto()  # Retry with error context
    DEPLOYING           = auto()  # Cloudflare Wrangler
    LIVE                = auto()  # URL sent to Herbert
    FAILED              = auto()  # Max retries exhausted
    KILLED              = auto()  # Herbert sent "Kill" / VETO


# ─────────────────────────────────────────────────────────────────────────────
# VALID TRANSITIONS — the LLM can never bypass this
# ─────────────────────────────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[AMMState, list[AMMState]] = {
    AMMState.IDLE:                  [AMMState.MONITORING],
    AMMState.MONITORING:            [AMMState.SCORING],
    AMMState.SCORING:               [AMMState.COUNCIL_DELIBERATING],
    AMMState.COUNCIL_DELIBERATING:  [AMMState.BUILDING, AMMState.AWAITING_HERBERT, AMMState.IDLE],
    AMMState.AWAITING_HERBERT:      [AMMState.BUILDING, AMMState.KILLED],
    AMMState.BUILDING:              [AMMState.VALIDATING, AMMState.FAILED],
    AMMState.VALIDATING:            [AMMState.DEPLOYING, AMMState.REPAIRING],
    AMMState.REPAIRING:             [AMMState.VALIDATING, AMMState.FAILED],
    AMMState.DEPLOYING:             [AMMState.LIVE, AMMState.FAILED],
    AMMState.LIVE:                  [AMMState.IDLE],
    AMMState.FAILED:                [AMMState.IDLE, AMMState.BUILDING],  # IDLE=reset, BUILDING=retry
    AMMState.KILLED:                [AMMState.IDLE],
}


# ─────────────────────────────────────────────────────────────────────────────
# LEGACY STATUS MAPPING — backward compat with council_state.json consumers
# ─────────────────────────────────────────────────────────────────────────────

_LEGACY_TO_AMM: dict[str, str] = {
    "DELIBERATING":   "COUNCIL_DELIBERATING",
    "AWAITING_HUMAN": "AWAITING_HERBERT",
    "PROCEED":        "BUILDING",
    "VETOED":         "KILLED",
    "BUILT":          "LIVE",
}

_AMM_TO_LEGACY: dict[AMMState, str] = {
    AMMState.COUNCIL_DELIBERATING: "DELIBERATING",
    AMMState.AWAITING_HERBERT:     "AWAITING_HUMAN",
    AMMState.KILLED:               "VETOED",
    AMMState.LIVE:                 "BUILT",
}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def transition(current: AMMState, new: AMMState, trigger: str = "") -> None:
    """Validate and execute a state transition.

    Raises AssertionError if the transition is illegal.
    Logs to SQLAlchemy and persists to council_state.json.

    Args:
        current: The state we are transitioning FROM.
        new: The state we are transitioning TO.
        trigger: Human-readable description of what caused the transition.
    """
    valid_targets = VALID_TRANSITIONS.get(current, [])
    assert new in valid_targets, (
        f"Illegal transition: {current.name} → {new.name}. "
        f"Valid targets from {current.name}: {[s.name for s in valid_targets]}. "
        f"This is a bug in YOUR code, not the LLM's."
    )

    # Log to database
    try:
        with get_session() as session:
            session.add(StateTransition(
                from_state=current.name,
                to_state=new.name,
                trigger=trigger,
            ))
    except Exception as e:
        # DB logging failure must not block state transition
        print(f"   ⚠️ DB log failed: {e}")

    # Persist to council_state.json for backward compat
    _persist_state(new, trigger)
    print(f"   ✓ State: {current.name} → {new.name} ({trigger})")


def get_current_state() -> AMMState:
    """Read current state from council_state.json."""
    state_data = _load_state_file()
    status = state_data.get("status", "IDLE").upper()

    # Map legacy status names to AMMState
    mapped = _LEGACY_TO_AMM.get(status, status)

    try:
        return AMMState[mapped]
    except KeyError:
        return AMMState.IDLE


def force_state(new: AMMState, trigger: str = "force_override") -> None:
    """Force a state without transition validation.

    USE WITH CAUTION — this skips the guard. Only for:
    - Manual recovery (Herbert's --reset)
    - Initial system boot
    """
    _persist_state(new, trigger)
    try:
        with get_session() as session:
            session.add(StateTransition(
                from_state="FORCED",
                to_state=new.name,
                trigger=trigger,
            ))
    except Exception:
        pass
    print(f"   ⚠️ State FORCED → {new.name} ({trigger})")


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL
# ─────────────────────────────────────────────────────────────────────────────

def _load_state_file() -> dict:
    """Read council_state.json."""
    if not AMM_STATE_FILE.exists():
        return {"status": "IDLE"}
    try:
        return json.loads(AMM_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "IDLE"}


def _persist_state(state: AMMState, trigger: str) -> None:
    """Write to council_state.json for backward compat."""
    legacy_status = _AMM_TO_LEGACY.get(state, state.name)

    data = _load_state_file()
    data["status"] = legacy_status
    data["status_updated_at"] = datetime.now(timezone.utc).isoformat() + "Z"

    AMM_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    AMM_STATE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
