"""AMM Phase 5 — Deterministic Model Router

Routes tasks to the appropriate LLM based on complexity heuristics.
Python decides — LLM never sees the routing logic.

Routing priority:
  complexity < 0.7  → Modal qwen2.5-coder:7b (free, no rate limits)
  complexity >= 0.7 → Groq llama-3.3-70b (check budget first), else Gemini

Reuses factory functions from crewai_llm_config_hybrid.py.
No RouteLLM dependency — pure Python heuristics (RouteLLM = Phase 7).
"""
import sys
import time
from pathlib import Path

# Import LLM factories from existing config
sys.path.insert(0, str(Path(__file__).parent.parent))
from crewai_llm_config_hybrid import _make_modal_llm, _make_groq_llm, _make_gemini_llm


# ─────────────────────────────────────────────────────────────────────────────
# GROQ RATE LIMIT BUDGET TRACKER
# ─────────────────────────────────────────────────────────────────────────────

_groq_calls_remaining = 30  # Conservative estimate per Groq free-tier window
_groq_last_reset = time.time()
_GROQ_WINDOW_S = 60


def _check_groq_budget() -> bool:
    """Check if Groq rate limit budget allows a call."""
    global _groq_calls_remaining, _groq_last_reset
    now = time.time()
    if now - _groq_last_reset > _GROQ_WINDOW_S:
        _groq_calls_remaining = 30
        _groq_last_reset = now
    return _groq_calls_remaining > 0


def _consume_groq_budget():
    """Decrement Groq call budget."""
    global _groq_calls_remaining
    _groq_calls_remaining -= 1


# ─────────────────────────────────────────────────────────────────────────────
# COMPLEXITY HEURISTICS — no LLM call, pure keyword + token count
# ─────────────────────────────────────────────────────────────────────────────

_COMPLEXITY_KEYWORDS_HIGH = frozenset({
    "integrate", "refactor", "across files", "multi-file", "authentication",
    "payment", "real-time", "websocket", "complex", "full-stack",
    "oauth", "stripe", "database migration",
})

_COMPLEXITY_KEYWORDS_LOW = frozenset({
    "simple", "basic", "single", "one file", "style", "css", "readme",
    "deploy", "config", "env", "rename", "typo", "comment",
})


def classify_complexity(task_description: str, token_count: int = 0) -> float:
    """Estimate task complexity without an LLM call.

    Args:
        task_description: Human-readable task text.
        token_count: Estimated token count (len(text) // 4).

    Returns:
        Float between 0.0 and 1.0.
    """
    desc_lower = task_description.lower()
    score = 0.5  # baseline
    
    # Correcting logic from read
    for kw in _COMPLEXITY_KEYWORDS_HIGH:
        if kw in desc_lower:
            score += 0.1
    for kw in _COMPLEXITY_KEYWORDS_LOW:
        if kw in desc_lower:
            score -= 0.1

    # Token count factor (more context = likely more complex)
    if token_count > 4000:
        score += 0.15
    elif token_count > 2000:
        score += 0.05

    return max(0.0, min(1.0, score))


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER — returns (llm_instance, model_label)
# ─────────────────────────────────────────────────────────────────────────────

def route_task(complexity: float):
    """Select LLM based on complexity score.

    Args:
        complexity: Float 0.0-1.0 from classify_complexity() or dag_config.yaml.

    Returns:
        Tuple of (llm_instance, model_label_str).
    """
    if complexity < 0.7:
        print(f"[ROUTER] complexity={complexity:.2f} → Modal qwen2.5-coder:7b")
        return _make_modal_llm(), "modal_7b"

    if _check_groq_budget():
        _consume_groq_budget()
        print(f"[ROUTER] complexity={complexity:.2f} → Groq llama-3.3-70b")
        return _make_groq_llm(), "groq_70b"

    print(f"[ROUTER] complexity={complexity:.2f} → Gemini 2.0 Flash (Groq budget exhausted)")
    return _make_gemini_llm(), "gemini_flash"


def route_for_retry(original_complexity: float, attempt: int, last_error_msg: str = ""):
    """Escalate model on retry — each attempt bumps complexity by 0.2.
    Bypasses Groq completely if previous error was network/access related.

    Args:
        original_complexity: The node's base complexity.
        attempt: Current retry attempt (0-indexed).
        last_error_msg: Error message from the previous failed attempt.

    Returns:
        Tuple of (llm_instance, model_label_str).
    """
    if "Access denied" in last_error_msg or "GroqException" in last_error_msg or "APIError" in last_error_msg:
        print(f"[ROUTER] Network/API error detected. Bypassing Groq → Gemini 2.0 Flash")
        return _make_gemini_llm(), "gemini_flash"

    escalated = min(1.0, original_complexity + (attempt * 0.2))
    print(f"[ROUTER] Retry escalation: {original_complexity:.2f} → {escalated:.2f}")
    return route_task(escalated)
