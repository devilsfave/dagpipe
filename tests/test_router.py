"""Tests for dagpipe.router — deterministic model routing."""
from dagpipe.router import ModelRouter, classify_complexity


# ── Dummy provider callables ─────────────────────────────────────────────────

def _low_fn() -> str:
    return "low"


def _high_fn() -> str:
    return "high"


def _fallback_fn() -> str:
    return "fallback"


def _make_router(**kwargs: object) -> ModelRouter:
    """Helper to build a router with dummy callables."""
    defaults: dict = dict(
        low_complexity_fn=_low_fn,
        high_complexity_fn=_high_fn,
        fallback_fn=_fallback_fn,
        low_label="modal_7b",
        high_label="groq_70b",
        fallback_label="gemini_flash",
    )
    defaults.update(kwargs)
    return ModelRouter(**defaults)


# ── Route tests ──────────────────────────────────────────────────────────────

def test_low_complexity_routes_to_low_fn() -> None:
    """Low complexity routes to low_complexity_fn."""
    router = _make_router()
    fn, label = router.route(0.3)
    assert fn is _low_fn
    assert label == "modal_7b"


def test_high_complexity_routes_to_high_fn() -> None:
    """High complexity routes to high_complexity_fn."""
    router = _make_router()
    fn, label = router.route(0.8)
    assert fn is _high_fn
    assert label == "groq_70b"


def test_high_complexity_falls_back_when_budget_zero() -> None:
    """High complexity routes to fallback when Groq budget is 0."""
    router = _make_router(groq_rpm_limit=0)
    fn, label = router.route(0.9)
    assert fn is _fallback_fn
    assert label == "gemini_flash"


def test_budget_depletes_then_falls_back() -> None:
    """After consuming all budget, high complexity falls back."""
    router = _make_router(groq_rpm_limit=2)

    fn1, _ = router.route(0.8)
    assert fn1 is _high_fn
    fn2, _ = router.route(0.8)
    assert fn2 is _high_fn
    fn3, label3 = router.route(0.8)
    assert fn3 is _fallback_fn
    assert label3 == "gemini_flash"


# ── classify_complexity tests ────────────────────────────────────────────────

def test_classify_complexity_high_keywords() -> None:
    """classify_complexity() returns higher score for complex keywords."""
    score = classify_complexity("Refactor authentication across files")
    assert score > 0.6


def test_classify_complexity_low_keywords() -> None:
    """classify_complexity() returns lower score for simple keywords."""
    score = classify_complexity("Simple readme typo fix")
    assert score < 0.4


def test_classify_complexity_token_boost() -> None:
    """Large token counts boost complexity score."""
    base = classify_complexity("Some task")
    boosted = classify_complexity("Some task", token_count=5000)
    assert boosted > base


def test_classify_complexity_clamped() -> None:
    """Score is always clamped between 0.0 and 1.0."""
    low = classify_complexity("simple basic single one file style css readme deploy config env rename typo comment")
    high = classify_complexity("integrate refactor across files multi-file authentication payment real-time websocket complex full-stack oauth stripe database migration", token_count=5000)
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0


# ── Retry escalation tests ──────────────────────────────────────────────────

def test_retry_escalation_bumps_complexity() -> None:
    """Retry escalation pushes low-complexity task to high-complexity provider."""
    router = _make_router()

    # Base complexity 0.5 → routes to low
    fn0, _ = router.route(0.5)
    assert fn0 is _low_fn

    # After 1 retry (attempt=1): 0.5 + 0.2 = 0.7 → routes to high
    fn1, label1 = router.route_for_retry(0.5, attempt=1)
    assert fn1 is _high_fn
    assert label1 == "groq_70b"


def test_network_error_bypasses_high_to_fallback() -> None:
    """Network error in last_error bypasses high_complexity → fallback."""
    router = _make_router()

    fn, label = router.route_for_retry(0.8, attempt=1, last_error="APIError: connection refused")
    assert fn is _fallback_fn
    assert label == "gemini_flash"


def test_access_denied_bypasses_high_to_fallback() -> None:
    """Access denied error routes directly to fallback."""
    router = _make_router()

    fn, label = router.route_for_retry(0.8, attempt=1, last_error="Access denied for this key")
    assert fn is _fallback_fn
    assert label == "gemini_flash"


def test_rate_limit_error_bypasses_high_to_fallback() -> None:
    """Rate limit error routes directly to fallback."""
    router = _make_router()

    fn, label = router.route_for_retry(0.5, attempt=0, last_error="rate limit exceeded")
    assert fn is _fallback_fn
    assert label == "gemini_flash"
