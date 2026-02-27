"""AMM Phase 5 — Constrained Generation

Wraps LLM calls with schema validation to guarantee structured output.

Path B (primary): Raw LLM call → extract JSON → Pydantic validation → retry on failure.
Path A (optional): Outlines with OpenAI-compatible backend (token-level constraints).

NO vLLM. NO Modal container changes. NO XGrammar.
"""
import json
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from .config import AMM_CONSTRAINED_MODE


T = TypeVar("T", bound=BaseModel)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def constrained_generate(
    messages: list[dict],
    schema: Type[T],
    llm_call_fn,
    max_retries: int = 2,
    **llm_kwargs,
) -> T:
    """Generate LLM output constrained to a Pydantic schema.

    Args:
        messages: Chat messages to send to LLM.
        schema: Pydantic BaseModel class for output validation.
        llm_call_fn: Callable (messages, **kwargs) → str.
        max_retries: Retries on validation failure.

    Returns:
        Validated Pydantic model instance.

    Raises:
        ValueError: If all retries exhausted and output still invalid.
    """
    if AMM_CONSTRAINED_MODE == "outlines":
        return _generate_outlines(messages, schema, llm_call_fn, **llm_kwargs)
    return _generate_pydantic_retry(messages, schema, llm_call_fn, max_retries, **llm_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# PATH B: PYDANTIC RETRY (safe default — no external deps beyond pydantic)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_pydantic_retry(
    messages: list[dict],
    schema: Type[T],
    llm_call_fn,
    max_retries: int = 2,
    **llm_kwargs,
) -> T:
    """Raw LLM call → extract JSON → validate against Pydantic schema → retry."""
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    schema_instruction = (
        "\n\nYou MUST respond with ONLY a valid JSON object matching this schema:\n"
        f"```json\n{schema_json}\n```\n"
        "Do NOT include any text before or after the JSON. "
        "Do NOT wrap in markdown code blocks. "
        "Output ONLY the raw JSON object starting with {{ and ending with }}."
    )

    enhanced_messages = _inject_schema_instruction(messages, schema_instruction)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            raw = llm_call_fn(enhanced_messages, **llm_kwargs)

            # Extract JSON from response (may be wrapped in markdown)
            json_str = _extract_json(raw)

            # Validate against schema
            result = schema.model_validate_json(json_str)
            return result

        except (ValidationError, json.JSONDecodeError, ValueError) as e:
            last_error = e
            print(
                f"[CONSTRAINED] Validation failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
            )

            if attempt < max_retries:
                # Inject error feedback for next retry
                error_feedback = (
                    f"\n\n⚠️ Your previous JSON was INVALID: {e}\n"
                    f"Fix the error and respond with ONLY the corrected JSON."
                )
                enhanced_messages = _inject_schema_instruction(
                    messages, schema_instruction + error_feedback
                )

    raise ValueError(
        f"Constrained generation failed after {max_retries + 1} attempts. "
        f"Last error: {last_error}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PATH A: OUTLINES (optional — requires `pip install outlines`)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_outlines(
    messages: list[dict],
    schema: Type[T],
    llm_call_fn,
    **llm_kwargs,
) -> T:
    """Outlines with OpenAI-compatible backend.

    Falls back to pydantic_retry if outlines is not installed or
    remote API wiring is not yet stable.
    """
    try:
        import outlines  # noqa: F401

        # Outlines remote API integration with Ollama endpoints
        # is still evolving. When stable, wire up here:
        #   from outlines import models, generate
        #   model = models.openai(api_url=MODAL_URL, model="tgi")
        #   generator = generate.json(model, schema)
        #   result = generator(prompt)
        #   return result

        # For now, fall back to pydantic retry
        raise ImportError("Outlines remote API not yet wired — falling back")

    except ImportError:
        print("[CONSTRAINED] Outlines not available — using Pydantic retry fallback")
        return _generate_pydantic_retry(messages, schema, llm_call_fn, **llm_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _inject_schema_instruction(messages: list[dict], instruction: str) -> list[dict]:
    """Clone messages and append schema instruction to the last user message."""
    cloned = [m.copy() for m in messages]
    for i in range(len(cloned) - 1, -1, -1):
        if cloned[i]["role"] == "user":
            cloned[i]["content"] += instruction
            break
    return cloned


def _extract_json(raw: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks.

    Handles:
    - Raw JSON: {"key": "value"}
    - Markdown-wrapped: ```json\n{"key": "value"}\n```
    - Text before/after JSON: "Here is the result: {"key": "value"} Done."
    """
    raw = raw.strip()

    # Remove markdown code block wrappers
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    # Find the outermost JSON object
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]

    return raw  # Return as-is — let Pydantic report the error
