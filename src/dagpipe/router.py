"""DagPipe — Deterministic Model Router

Routes tasks to the appropriate LLM provider based on complexity heuristics.
Python decides — LLM never sees the routing logic.

The router does NOT own LLM clients. Users pass provider callables at init.
The router only decides WHICH callable to invoke based on complexity score.
"""
import time
from typing import Callable


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
# MODEL ROUTER — returns (callable, label_string)
# ─────────────────────────────────────────────────────────────────────────────

class ModelRouter:
    """Routes LLM calls to user-provided provider functions based on complexity.

    The router does not own LLM clients. Users supply callables for each
    provider tier and the router selects which to invoke.

    Args:
        low_complexity_fn: Called when complexity < threshold.
        high_complexity_fn: Called when complexity >= threshold and budget allows.
        fallback_fn: Called when high_complexity_fn is rate-limited.
        low_label: Human-readable label for the low-complexity provider.
        high_label: Human-readable label for the high-complexity provider.
        fallback_label: Human-readable label for the fallback provider.
        complexity_threshold: Score at which to escalate from low to high.
        groq_rpm_limit: Max calls per minute for high_complexity_fn.
    """

    def __init__(
        self,
        low_complexity_fn: Callable,
        high_complexity_fn: Callable,
        fallback_fn: Callable,
        low_label: str = "low",
        high_label: str = "high",
        fallback_label: str = "fallback",
        complexity_threshold: float = 0.7,
        groq_rpm_limit: int = 30,
    ) -> None:
        self._low_fn = low_complexity_fn
        self._high_fn = high_complexity_fn
        self._fallback_fn = fallback_fn
        self._low_label = low_label
        self._high_label = high_label
        self._fallback_label = fallback_label
        self._threshold = complexity_threshold
        self._rpm_limit = groq_rpm_limit

        # Rate limit budget tracker
        self._calls_remaining = groq_rpm_limit
        self._last_reset = time.time()
        self._window_s = 60

    # ── Rate limit budget ────────────────────────────────────────────────

    def _check_budget(self) -> bool:
        """Check if the high-complexity provider budget allows a call."""
        now = time.time()
        if now - self._last_reset > self._window_s:
            self._calls_remaining = self._rpm_limit
            self._last_reset = now
        return self._calls_remaining > 0

    def _consume_budget(self) -> None:
        """Decrement the high-complexity provider call budget."""
        self._calls_remaining -= 1

    # ── Routing ──────────────────────────────────────────────────────────

    def route(self, complexity: float) -> tuple[Callable, str]:
        """Select provider based on complexity score.

        Args:
            complexity: Float 0.0–1.0 from classify_complexity() or config.

        Returns:
            Tuple of (callable, label_string).
        """
        if complexity < self._threshold:
            return self._low_fn, self._low_label

        if self._check_budget():
            self._consume_budget()
            return self._high_fn, self._high_label

        return self._fallback_fn, self._fallback_label

    def route_for_retry(
        self,
        complexity: float,
        attempt: int,
        last_error: str = "",
    ) -> tuple[Callable, str]:
        """Escalate provider on retry — each attempt bumps complexity by 0.2.

        Bypasses high_complexity_fn entirely if previous error was
        network/access related.

        Args:
            complexity: The node's base complexity.
            attempt: Current retry attempt (0-indexed).
            last_error: Error message from the previous failed attempt.

        Returns:
            Tuple of (callable, label_string).
        """
        if any(kw in last_error for kw in ("Access denied", "APIError", "rate limit")):
            return self._fallback_fn, self._fallback_label

        escalated = min(1.0, complexity + (attempt * 0.2))
        return self.route(escalated)
