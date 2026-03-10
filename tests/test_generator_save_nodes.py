"""Regression tests for generator save-node bugs.

Bug 1: Save nodes must return {"file_saved": True} — not json_saved, txt_saved, etc.
Bug 2: Save node context.get() calls must use `or ''` + str() to guard against None.
Bug 3: Packager zip filename must be slugified from the pipeline use_case.

These tests verify the system prompt contains the correct contracts so that any
future LLM completion will follow them, and that the deterministic helpers are correct.
"""
import re
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from dagpipe.generator.pipeline_generator import (
    _fallback_runner,
    _slugify_use_case,
    packager,
    runner_writer,
    schema_designer,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_runner_writer_prompt() -> str:
    """Extract the system prompt text from runner_writer by inspecting what
    it passes to the model.  We use a capture mock instead of reading the
    source so the test stays honest even if the string is refactored."""
    captured = {}

    def capture_model(messages):
        captured["messages"] = messages
        # Return a minimal valid save-node script
        return (
            "import os\n"
            "from pathlib import Path\n"
            "def save_results(context: dict, model=None) -> dict:\n"
            "    data = str(context.get('prev', {}).get('output') or '')\n"
            "    Path('out.json').write_text(data, encoding='utf-8')\n"
            "    return {'file_saved': True}\n"
        )

    context = {
        "schema_designer": {
            "nodes": [
                {
                    "id": "save_results",
                    "fn_name": "save_results",
                    "depends_on": ["process"],
                    "complexity": 0.0,
                    "description": "Save results to disk",
                    "is_deterministic": True,
                }
            ]
        },
        "yaml_writer": {"yaml_content": "nodes: []", "node_count": 1},
        "intake_parser": {
            "use_case": "test save pipeline",
            "steps": ["save"],
            "domain": "test",
            "estimated_nodes": 1,
        },
    }
    runner_writer(context=context, model=capture_model)
    # Retrieve the system message content
    system_msgs = [m for m in captured["messages"] if m.get("role") == "system"]
    return "\n".join(m["content"] for m in system_msgs)


def _get_schema_designer_prompt() -> str:
    """Extract the system prompt text from schema_designer."""
    captured = {}

    def capture_model(messages):
        captured["messages"] = messages
        # Return a minimal valid DAG design JSON
        return (
            '{"nodes": [{"id": "save", "fn_name": "save", "depends_on": [], '
            '"complexity": 0.0, "description": "save", "is_deterministic": true}]}'
        )

    schema_designer(
        context={
            "intake_parser": {
                "use_case": "save",
                "steps": ["save"],
                "domain": "test",
                "estimated_nodes": 1,
            }
        },
        model=capture_model,
    )
    system_msgs = [m for m in captured["messages"] if m.get("role") == "system"]
    return "\n".join(m["content"] for m in system_msgs)


# ─────────────────────────────────────────────────────────────────────────────
# Bug 1: runner_writer prompt mandates file_saved return key for save nodes
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_writer_prompt_contains_file_saved_contract() -> None:
    """The runner_writer system prompt must explicitly require file_saved for save nodes."""
    prompt = _get_runner_writer_prompt()
    assert "file_saved" in prompt, (
        "runner_writer system prompt must contain 'file_saved' as the required "
        "return key for save/write nodes. Without this, the LLM invents its own "
        "keys (json_saved, txt_saved, etc.) that break YAML assertions."
    )


def test_runner_writer_prompt_forbids_invented_save_keys() -> None:
    """The runner_writer prompt must define a clear return key table so LLM
    does NOT invent alternative keys like json_saved or txt_saved."""
    prompt = _get_runner_writer_prompt()
    # The prompt must list the canonical key table
    assert "Save / write node" in prompt or "save" in prompt.lower(), (
        "System prompt must explicitly call out the save node return key contract."
    )
    # The bad patterns must NOT appear as instructions
    assert "json_saved" not in prompt, "Prompt must not teach 'json_saved' as a return key."
    assert "txt_saved" not in prompt, "Prompt must not teach 'txt_saved' as a return key."


# ─────────────────────────────────────────────────────────────────────────────
# Bug 2: runner_writer prompt mandates None guard for context.get() in saves
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_writer_prompt_contains_none_guard() -> None:
    """The runner_writer system prompt must show the 'or \"\"' guard pattern."""
    prompt = _get_runner_writer_prompt()
    assert "or ''" in prompt or 'or ""' in prompt, (
        "System prompt must show 'or \"\"' (or equivalent) guard on context.get() calls "
        "inside save nodes to prevent 'write() argument must be str, not None' crashes."
    )


def test_runner_writer_prompt_contains_str_cast() -> None:
    """The runner_writer system prompt must show str() cast before writing."""
    prompt = _get_runner_writer_prompt()
    assert "str(" in prompt, (
        "System prompt save node example must use str() cast before writing to disk."
    )


# ─────────────────────────────────────────────────────────────────────────────
# schema_designer: assert_logic uses file_saved for save nodes
# ─────────────────────────────────────────────────────────────────────────────

def test_schema_designer_prompt_contains_file_saved_assert() -> None:
    """schema_designer prompt must instruct the LLM to use file_saved in assert_logic."""
    prompt = _get_schema_designer_prompt()
    assert "file_saved" in prompt, (
        "schema_designer system prompt must specify that save node assert_logic "
        "checks 'file_saved', matching the key that runner.py returns."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Return key contracts for ALL node types in runner_writer prompt
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_writer_prompt_has_all_node_type_contracts() -> None:
    """runner_writer system prompt must define return key contracts for all node types."""
    prompt = _get_runner_writer_prompt()
    # Every node type in the contract table
    expected_contracts = [
        ("LLM / process node", "output"),
        ("Save / write node", "file_saved"),
        ("Load / read node", "loaded_data"),
        ("Fetch / HTTP node", "fetched_data"),
        ("Transform node", "transformed"),
        ("Status / done node", "status"),
    ]
    for node_type_hint, expected_key in expected_contracts:
        assert expected_key in prompt, (
            f"runner_writer prompt must specify '{expected_key}' as the return key "
            f"for node type matching '{node_type_hint}'."
        )


def test_schema_designer_prompt_has_all_assert_logic_contracts() -> None:
    """schema_designer prompt must list assert_logic patterns for all node types."""
    prompt = _get_schema_designer_prompt()
    required_keys = ["output", "file_saved", "loaded_data", "fetched_data", "transformed", "status"]
    for key in required_keys:
        assert key in prompt, (
            f"schema_designer prompt must reference '{key}' so LLM generates "
            f"correct assert_logic for each node type."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bug 3: ZIP slug naming
# ─────────────────────────────────────────────────────────────────────────────

class TestSlugifyUseCase:
    def test_basic_slugify(self) -> None:
        assert _slugify_use_case("Summarize news articles") == "summarize_news_articles"

    def test_truncates_to_five_words(self) -> None:
        slug = _slugify_use_case("I want a pipeline that summarizes news articles daily")
        parts = slug.split("_")
        assert len(parts) <= 5, f"Expected max 5 words, got {len(parts)}: {slug}"

    def test_strips_special_chars(self) -> None:
        slug = _slugify_use_case("Save output to JSON & TXT!")
        assert "&" not in slug
        assert "!" not in slug

    def test_empty_string_fallback(self) -> None:
        assert _slugify_use_case("") == "pipeline"

    def test_whitespace_only_fallback(self) -> None:
        assert _slugify_use_case("   ") == "pipeline"

    def test_lowercase(self) -> None:
        slug = _slugify_use_case("Summarize News Articles")
        assert slug == slug.lower()


def test_packager_creates_slugified_zip_name() -> None:
    """packager() must produce a zip file whose name reflects the use_case."""
    context = {
        "yaml_writer": {
            "yaml_content": "nodes:\n  - id: save\n    fn: save\n",
            "node_count": 1,
        },
        "runner_writer": {
            "script_content": "print('hello')\n",
            "dependencies": ["dagpipe-core", "groq"],
        },
        "intake_parser": {
            "use_case": "Research and summarize news articles",
            "steps": ["research", "summarize"],
            "domain": "news",
            "estimated_nodes": 2,
        },
    }

    result = packager(context=context, model=None)

    assert "zip_path" in result
    assert "zip_filename" in result

    zip_filename = result["zip_filename"]
    # Must end with _pipeline.zip
    assert zip_filename.endswith("_pipeline.zip"), (
        f"Expected filename to end with '_pipeline.zip', got: {zip_filename}"
    )
    # Must NOT be the old hardcoded name
    assert zip_filename != "pipeline.zip", "ZIP must not use old hardcoded 'pipeline.zip' name."
    # Must contain a recognisable word from the use_case
    assert "research" in zip_filename or "summarize" in zip_filename or "news" in zip_filename, (
        f"ZIP filename should be derived from use_case, got: {zip_filename}"
    )

    # The file on disk must actually exist with the slugified name
    zip_path = Path(result["zip_path"])
    assert zip_path.exists()
    assert zip_path.name == zip_filename


def test_packager_zip_contents_unchanged() -> None:
    """slug naming must not break the zip contents (3 files still present)."""
    context = {
        "yaml_writer": {"yaml_content": "nodes: []\n", "node_count": 0},
        "runner_writer": {
            "script_content": "# runner\n",
            "dependencies": ["dagpipe-core"],
        },
        "intake_parser": {
            "use_case": "Test pipeline",
            "steps": ["test"],
            "domain": "test",
            "estimated_nodes": 1,
        },
    }
    result = packager(context=context, model=None)
    with zipfile.ZipFile(result["zip_path"], "r") as zf:
        names = zf.namelist()
    assert "pipeline.yaml" in names
    assert "runner.py" in names
    assert "README.md" in names
