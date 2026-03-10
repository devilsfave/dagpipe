"""DagPipe v0.2.1 — Constrained Generation

DROP-IN REPLACEMENT for v0.1.x constrained.py.
All v0.1.x calls work identically.

NEW IN v0.2.0:
  - 5-strategy JSON extractor (handles Llama trailing commas, Python bools,
    markdown fences, explanation text, ast.literal_eval fallback)
  - Enhanced retry prompt includes previous failed output so LLM can self-correct
  - Better error messages on exhausted retries

Usage (unchanged from v0.1.x):
    from dagpipe.constrained import constrained_generate
    result = constrained_generate(messages, MySchema, llm_call_fn)
"""
from __future__ import annotations

import ast
import json
import re
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API  (signature unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def constrained_generate(
    messages: list[dict],
    schema: Type[T],
    llm_call_fn,
    max_retries: int = 2,
    mode: str = "pydantic_retry",
    **llm_kwargs,
) -> T:
    """Generate LLM output constrained to a Pydantic schema.

    Args:
        messages:     Chat messages to send to the LLM.
        schema:       Pydantic BaseModel class for output validation.
        llm_call_fn:  Callable(messages, **kwargs) → str.
        max_retries:  Number of retry attempts on validation failure.
        mode:         "pydantic_retry" (default) or "outlines".

    Returns:
        Validated Pydantic model instance — guaranteed.

    Raises:
        ValueError: All retries exhausted and output still invalid.
    """
    if mode == "outlines":
        return _generate_outlines(messages, schema, llm_call_fn, **llm_kwargs)
    return _generate_pydantic_retry(messages, schema, llm_call_fn, max_retries, **llm_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# PATH B: PYDANTIC RETRY  (enhanced in v0.2.0)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_pydantic_retry(
    messages: list[dict],
    schema: Type[T],
    llm_call_fn,
    max_retries: int = 2,
    **llm_kwargs,
) -> T:
    """Multi-strategy extraction + enhanced retry with previous output context."""

    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    schema_instruction = (
        "\n\nYou MUST respond with ONLY a valid JSON object matching this schema:\n"
        f"```json\n{schema_json}\n```\n"
        "Rules:\n"
        "- Output ONLY the raw JSON object starting with { and ending with }\n"
        "- Do NOT include any text before or after the JSON\n"
        "- Do NOT wrap in markdown code blocks\n"
        "- Use JSON booleans (true/false), not Python (True/False)\n"
        "- No trailing commas"
    )

    # Inject schema instruction into last user message
    augmented = list(messages)
    if augmented and augmented[-1].get("role") == "user":
        augmented[-1] = {
            **augmented[-1],
            "content": augmented[-1]["content"] + schema_instruction,
        }
    else:
        augmented.append({"role": "user", "content": schema_instruction})

    last_raw: str = ""
    last_error: str = ""

    for attempt in range(max_retries + 1):
        # On retry: inject previous failure context so LLM can self-correct
        if attempt > 0:
            retry_msg = (
                f"Your previous response failed validation.\n"
                f"Validation error: {last_error}\n"
                f"Your previous output was:\n{last_raw}\n\n"
                f"Fix the issues above and return ONLY valid JSON matching the schema.\n"
                f"Remember: use true/false (not True/False), no trailing commas, "
                f"no markdown, just the raw JSON object."
            )
            augmented = list(augmented) + [{"role": "user", "content": retry_msg}]

        try:
            raw = llm_call_fn(augmented, **llm_kwargs)
            last_raw = raw

            # Multi-strategy extraction — returns JSON string
            parsed_str = _extract_json(raw)

            # Pydantic validation — model_validate accepts JSON string
            result = schema.model_validate_json(parsed_str)
            return result

        except (ValueError, ValidationError) as exc:
            last_error = str(exc)
            continue
        except Exception as exc:
            last_error = str(exc)
            continue

    raise ValueError(
        f"constrained_generate failed after {max_retries + 1} attempts.\n"
        f"Schema: {schema.__name__}\n"
        f"Last error: {last_error}\n"
        f"Last raw output: {last_raw[:500]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5-STRATEGY JSON EXTRACTOR  (the key V2 improvement)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> str:
    """Extract a JSON object from an LLM response using 5 strategies.

    Handles:
      1. Clean JSON responses (direct parse — fastest path)
      2. JSON inside markdown code fences (```json ... ```)
      3. JSON embedded in explanation text (outermost braces)
      4. Python-style booleans and None (True→true, False→false, None→null)
         and trailing commas before } or ]
      5. Python dict literals via ast.literal_eval

    Returns:
        A valid JSON string (serialized from the extracted dict).

    Raises:
        ValueError: If all 5 strategies fail.
    """
    if not raw or not raw.strip():
        raise ValueError("Empty response from LLM")

    stripped = raw.strip()

    # ── Strategy 1: Direct JSON parse ────────────────────────────────────────
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return json.dumps(result)
    except json.JSONDecodeError:
        pass

    # ── Strategy 2: Extract from markdown fence ───────────────────────────────
    fence_patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
    ]
    for pattern in fence_patterns:
        match = re.search(pattern, stripped, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, dict):
                    return json.dumps(result)
            except json.JSONDecodeError:
                pass

    # ── Strategy 3: Extract outermost {} block ────────────────────────────────
    # Find the first { and the last } to extract the JSON object
    start = stripped.find('{')
    end = stripped.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = stripped[start:end + 1]
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return json.dumps(result)
        except json.JSONDecodeError:
            pass

    # ── Strategy 4: Normalize Python-style values + trailing commas ──────────
    normalized = stripped

    # Python booleans and None
    normalized = re.sub(r'\bTrue\b', 'true', normalized)
    normalized = re.sub(r'\bFalse\b', 'false', normalized)
    normalized = re.sub(r'\bNone\b', 'null', normalized)

    # Trailing commas before } or ]
    normalized = re.sub(r',(\s*[}\]])', r'\1', normalized)

    # Try direct parse of normalized
    try:
        result = json.loads(normalized)
        if isinstance(result, dict):
            return json.dumps(result)
    except json.JSONDecodeError:
        pass

    # Try extracting from normalized
    start = normalized.find('{')
    end = normalized.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = normalized[start:end + 1]
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return json.dumps(result)
        except json.JSONDecodeError:
            pass

    # ── Strategy 5: ast.literal_eval for Python dict literals ────────────────
    try:
        # Find the outermost { } block for literal_eval
        start = stripped.find('{')
        end = stripped.rfind('}')
        if start != -1 and end != -1:
            candidate = stripped[start:end + 1]
            result = ast.literal_eval(candidate)
            if isinstance(result, dict):
                # Convert to JSON-clean dict (handles Python types)
                return json.dumps(json.loads(json.dumps(result, default=str)))
    except (ValueError, SyntaxError):
        pass

    raise ValueError(
        f"_extract_json: Could not extract valid JSON after 5 strategies.\n"
        f"Response preview: {raw[:300]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PATH A: OUTLINES  (unchanged from v0.1.x)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_outlines(
    messages: list[dict],
    schema: Type[T],
    llm_call_fn,
    **llm_kwargs,
) -> T:
    """Token-level constrained generation via Outlines library (optional path).

    Requires: pip install outlines
    Falls back to pydantic_retry if outlines is not installed.
    """
    try:
        import outlines  # type: ignore[import]
    except ImportError:
        import warnings
        warnings.warn(
            "outlines package not installed. Falling back to pydantic_retry mode. "
            "Install with: pip install outlines",
            ImportWarning,
            stacklevel=3,
        )
        return _generate_pydantic_retry(messages, schema, llm_call_fn, max_retries=2, **llm_kwargs)

    # If outlines is available, use it for token-level constraints
    # This is provider-specific and requires an outlines-compatible backend
    raise NotImplementedError(
        "Outlines mode requires an outlines-compatible LLM backend. "
        "See https://github.com/outlines-dev/outlines for setup. "
        "Use mode='pydantic_retry' (default) for a provider-agnostic approach."
    )
