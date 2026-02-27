"""Tests for dagpipe.constrained — constrained LLM generation."""
from pydantic import BaseModel

from dagpipe.constrained import _extract_json, constrained_generate


# ── Test schema ──────────────────────────────────────────────────────────────

class ProductSpec(BaseModel):
    name: str
    tagline: str
    features: list[str]


VALID_JSON = '{"name": "HabitFlow", "tagline": "Track daily habits", "features": ["streaks", "reminders"]}'


# ── Tests ────────────────────────────────────────────────────────────────────

def test_valid_json_returns_model() -> None:
    """Valid JSON response → correct Pydantic model instance."""
    def mock_llm(messages: list[dict], **kwargs: object) -> str:
        return VALID_JSON

    result = constrained_generate(
        messages=[{"role": "user", "content": "Create a spec"}],
        schema=ProductSpec,
        llm_call_fn=mock_llm,
    )
    assert isinstance(result, ProductSpec)
    assert result.name == "HabitFlow"
    assert result.tagline == "Track daily habits"
    assert result.features == ["streaks", "reminders"]


def test_markdown_wrapped_json_parses() -> None:
    """Markdown-wrapped JSON response → still parses correctly."""
    wrapped = f"```json\n{VALID_JSON}\n```"

    def mock_llm(messages: list[dict], **kwargs: object) -> str:
        return wrapped

    result = constrained_generate(
        messages=[{"role": "user", "content": "Create a spec"}],
        schema=ProductSpec,
        llm_call_fn=mock_llm,
    )
    assert isinstance(result, ProductSpec)
    assert result.name == "HabitFlow"


def test_invalid_then_valid_on_retry() -> None:
    """Invalid JSON on first attempt, valid on retry → succeeds."""
    call_count = 0

    def mock_llm(messages: list[dict], **kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return '{"name": "HabitFlow"}'  # Missing required fields
        return VALID_JSON

    result = constrained_generate(
        messages=[{"role": "user", "content": "Create a spec"}],
        schema=ProductSpec,
        llm_call_fn=mock_llm,
        max_retries=2,
    )
    assert isinstance(result, ProductSpec)
    assert call_count == 2  # First attempt failed, second succeeded


def test_exhausted_retries_raises() -> None:
    """Exhausted retries → raises ValueError."""
    def mock_llm(messages: list[dict], **kwargs: object) -> str:
        return "not json at all"

    try:
        constrained_generate(
            messages=[{"role": "user", "content": "Create a spec"}],
            schema=ProductSpec,
            llm_call_fn=mock_llm,
            max_retries=1,
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "failed after 2 attempts" in str(e)


def test_extract_json_raw() -> None:
    """_extract_json handles raw JSON."""
    result = _extract_json('{"key": "value"}')
    assert result == '{"key": "value"}'


def test_extract_json_markdown_wrapped() -> None:
    """_extract_json handles ```json ... ``` wrapping."""
    result = _extract_json('```json\n{"key": "value"}\n```')
    assert result == '{"key": "value"}'


def test_extract_json_plain_code_block() -> None:
    """_extract_json handles ``` ... ``` wrapping (no json tag)."""
    result = _extract_json('```\n{"key": "value"}\n```')
    assert result == '{"key": "value"}'


def test_extract_json_text_wrapped() -> None:
    """_extract_json handles text before/after JSON."""
    result = _extract_json('Here is the result: {"key": "value"} Done.')
    assert result == '{"key": "value"}'


def test_mode_defaults_to_pydantic_retry() -> None:
    """Default mode is pydantic_retry (no outlines needed)."""
    def mock_llm(messages: list[dict], **kwargs: object) -> str:
        return VALID_JSON

    result = constrained_generate(
        messages=[{"role": "user", "content": "Create a spec"}],
        schema=ProductSpec,
        llm_call_fn=mock_llm,
    )
    assert isinstance(result, ProductSpec)
