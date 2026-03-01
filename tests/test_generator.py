"""Tests for dagpipe.generator — Template Generator Pipeline.

All tests use mocked LLM calls — no real Groq API hits.
We mock the llm_call_fn callable, NOT the module.
"""
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from dagpipe.dag import load_dag
from dagpipe.generator.schemas import (
    DAGDesignOutput,
    IntakeOutput,
    NodeSpec,
    PackageOutput,
    RunnerOutput,
    YAMLOutput,
)
from dagpipe.generator.pipeline_generator import (
    get_generator_nodes,
    get_generator_registry,
    intake_parser,
    schema_designer,
    yaml_writer,
    runner_writer,
    packager,
    run_generator,
)


# ─────────────────────────────────────────────────────────────────────────────
# MOCK LLM — returns valid JSON for each schema type
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_INTAKE = IntakeOutput(
    use_case="Scrape job listings and send daily summaries",
    steps=["scrape_listings", "filter_relevant", "summarize", "send_email"],
    domain="recruitment",
    estimated_nodes=5,
)

_MOCK_DESIGN = DAGDesignOutput(
    nodes=[
        NodeSpec(
            id="scrape",
            fn_name="scrape",
            depends_on=[],
            complexity=0.4,
            description="Scrape job listings from target sites",
        ),
        NodeSpec(
            id="filter",
            fn_name="filter",
            depends_on=["scrape"],
            complexity=0.5,
            description="Filter listings by relevance criteria",
        ),
        NodeSpec(
            id="summarize",
            fn_name="summarize",
            depends_on=["filter"],
            complexity=0.8,
            description="Generate concise summaries of filtered listings",
        ),
        NodeSpec(
            id="deliver",
            fn_name="deliver",
            depends_on=["summarize"],
            complexity=0.0,
            description="Package and deliver the final summary",
            is_deterministic=True,
        ),
    ]
)


def _make_mock_llm(schema_response: dict[str, Any]) -> MagicMock:
    """Create a mock LLM callable that returns a specific JSON response.

    The mock returns valid JSON matching the expected schema, simulating
    what a real LLM would produce through constrained_generate.
    """
    mock = MagicMock()
    mock.return_value = json.dumps(schema_response)
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: intake_parser extracts correct fields
# ─────────────────────────────────────────────────────────────────────────────

def test_intake_parser_extracts_fields() -> None:
    """intake_parser uses constrained_generate to extract structured fields."""
    mock_llm = _make_mock_llm(_MOCK_INTAKE.model_dump())

    context = {"request": "I want to scrape job listings and summarize them daily"}
    result = intake_parser(context=context, model=mock_llm)

    # Verify the mock LLM was called (constrained_generate invokes it)
    assert mock_llm.called

    # Verify output matches expected schema fields
    assert result["use_case"] == "Scrape job listings and send daily summaries"
    assert len(result["steps"]) == 4
    assert result["domain"] == "recruitment"
    assert result["estimated_nodes"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: schema_designer produces valid node structure
# ─────────────────────────────────────────────────────────────────────────────

def test_schema_designer_produces_valid_nodes() -> None:
    """schema_designer returns a list of node specs with valid structure."""
    mock_llm = _make_mock_llm(_MOCK_DESIGN.model_dump())

    context = {
        "intake_parser": _MOCK_INTAKE.model_dump(),
    }
    result = schema_designer(context=context, model=mock_llm)

    assert "nodes" in result
    nodes = result["nodes"]
    assert len(nodes) == 4

    # Verify node structure
    for node in nodes:
        assert "id" in node
        assert "fn_name" in node
        assert "depends_on" in node
        assert "complexity" in node
        assert "description" in node

    # Verify dependency chain
    assert nodes[0]["depends_on"] == []
    assert nodes[1]["depends_on"] == ["scrape"]
    assert nodes[3]["is_deterministic"] is True


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: yaml_writer output loads with load_dag()
# ─────────────────────────────────────────────────────────────────────────────

def test_yaml_writer_output_loads_with_dagpipe(tmp_path: Path) -> None:
    """yaml_writer produces YAML that load_dag() can parse correctly."""
    # yaml_writer is deterministic — model=None
    context = {
        "schema_designer": _MOCK_DESIGN.model_dump(),
    }
    result = yaml_writer(context=context, model=None)

    assert result["node_count"] == 4
    assert len(result["yaml_content"]) > 0

    # Write YAML to disk and verify load_dag() can parse it
    yaml_path = tmp_path / "test_pipeline.yaml"
    yaml_path.write_text(result["yaml_content"], encoding="utf-8")

    loaded_nodes = load_dag(yaml_path)
    assert len(loaded_nodes) == 4
    assert loaded_nodes[0].id == "scrape"
    assert loaded_nodes[0].fn_name == "scrape"
    assert loaded_nodes[1].depends_on == ["scrape"]
    assert loaded_nodes[3].is_deterministic is True


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: runner_writer generates a script
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_writer_generates_script() -> None:
    """runner_writer produces a non-empty Python script with dependencies."""
    mock_llm = MagicMock()
    mock_llm.return_value = (
        '"""Auto-generated runner"""\n'
        'import os\nfrom dagpipe.dag import PipelineOrchestrator\n'
        'def main(): pass\n'
    )

    context = {
        "schema_designer": _MOCK_DESIGN.model_dump(),
        "yaml_writer": {"yaml_content": "nodes: []", "node_count": 4},
        "intake_parser": _MOCK_INTAKE.model_dump(),
    }
    result = runner_writer(context=context, model=mock_llm)

    assert "script_content" in result
    assert len(result["script_content"]) > 0
    assert "dependencies" in result
    assert "dagpipe-core" in result["dependencies"]


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: runner_writer fallback works without LLM
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_writer_fallback_without_llm() -> None:
    """runner_writer uses deterministic fallback when model is None."""
    context = {
        "schema_designer": _MOCK_DESIGN.model_dump(),
        "yaml_writer": {"yaml_content": "nodes: []", "node_count": 4},
        "intake_parser": _MOCK_INTAKE.model_dump(),
    }
    result = runner_writer(context=context, model=None)

    assert "script_content" in result
    assert "dagpipe-core" in result["dependencies"]
    # Fallback should contain function definitions
    assert "def scrape" in result["script_content"]
    assert "def filter" in result["script_content"]


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: packager creates a valid zip with 3 files
# ─────────────────────────────────────────────────────────────────────────────

def test_packager_creates_valid_zip() -> None:
    """packager writes 3 files to a zip archive in a temp directory."""
    context = {
        "yaml_writer": {
            "yaml_content": "nodes:\n  - id: test\n    fn: test\n",
            "node_count": 1,
        },
        "runner_writer": {
            "script_content": "print('hello')\n",
            "dependencies": ["dagpipe-core", "groq"],
        },
        "intake_parser": {
            "use_case": "Test Pipeline",
            "steps": ["test"],
            "domain": "testing",
            "estimated_nodes": 1,
        },
    }

    # packager is deterministic — model=None
    result = packager(context=context, model=None)

    assert "zip_path" in result
    assert "files_included" in result
    assert len(result["files_included"]) == 3

    # Verify the zip actually exists and contains the right files
    zip_path = Path(result["zip_path"])
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "pipeline.yaml" in names
        assert "runner.py" in names
        assert "README.md" in names

        # Verify YAML content was written correctly
        yaml_in_zip = zf.read("pipeline.yaml").decode("utf-8")
        assert "test" in yaml_in_zip


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: Pydantic schemas validate correctly
# ─────────────────────────────────────────────────────────────────────────────

def test_schemas_validate_correctly() -> None:
    """All Pydantic schemas accept valid data and reject invalid data."""
    # IntakeOutput
    intake = IntakeOutput(
        use_case="test",
        steps=["a", "b"],
        domain="test",
        estimated_nodes=2,
    )
    assert intake.use_case == "test"

    # NodeSpec
    node = NodeSpec(
        id="test",
        fn_name="test",
        complexity=0.5,
        description="Test node",
    )
    assert node.depends_on == []
    assert node.is_deterministic is False

    # YAMLOutput
    yaml_out = YAMLOutput(yaml_content="nodes: []", node_count=0)
    assert yaml_out.node_count == 0

    # RunnerOutput
    runner = RunnerOutput(
        script_content="print('hi')",
        dependencies=["dagpipe-core"],
    )
    assert len(runner.dependencies) == 1

    # PackageOutput
    pkg = PackageOutput(
        zip_path="/tmp/test.zip",
        files_included=["a.yaml", "b.py", "c.md"],
    )
    assert len(pkg.files_included) == 3


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: Generator pipeline nodes are valid DAGNodes
# ─────────────────────────────────────────────────────────────────────────────

def test_generator_nodes_structure() -> None:
    """get_generator_nodes() returns valid DAGNodes with correct wiring."""
    nodes = get_generator_nodes()

    assert len(nodes) == 5
    ids = [n.id for n in nodes]
    assert ids == [
        "intake_parser",
        "schema_designer",
        "yaml_writer",
        "runner_writer",
        "packager",
    ]

    # Check dependencies
    assert nodes[0].depends_on == []
    assert nodes[1].depends_on == ["intake_parser"]
    assert nodes[2].depends_on == ["schema_designer"]
    assert nodes[3].depends_on == ["schema_designer", "yaml_writer"]
    assert nodes[4].depends_on == ["yaml_writer", "runner_writer"]

    # Check deterministic flags
    assert nodes[2].is_deterministic is True  # yaml_writer
    assert nodes[4].is_deterministic is True  # packager
    assert nodes[0].is_deterministic is False  # intake_parser


# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: Registry matches nodes
# ─────────────────────────────────────────────────────────────────────────────

def test_generator_registry_matches_nodes() -> None:
    """get_generator_registry() has entries for every node fn_name."""
    nodes = get_generator_nodes()
    registry = get_generator_registry()

    for node in nodes:
        assert node.fn_name in registry, f"Missing registry entry for {node.fn_name}"
        assert callable(registry[node.fn_name])


# ─────────────────────────────────────────────────────────────────────────────
# TEST 10: Full pipeline end to end with mocks
# ─────────────────────────────────────────────────────────────────────────────

def test_full_pipeline_e2e_with_mocks(tmp_path: Path) -> None:
    """Full generator pipeline runs end to end with mocked LLM calls."""

    # Track which call number we're on — return appropriate schema
    call_count = {"n": 0}

    # Mock responses for each constrained_generate call in order:
    # 1. intake_parser → IntakeOutput
    # 2. schema_designer → DAGDesignOutput
    # 3. runner_writer → plain script text (not constrained)
    mock_responses = [
        json.dumps(_MOCK_INTAKE.model_dump()),       # intake_parser
        json.dumps(_MOCK_DESIGN.model_dump()),        # schema_designer
        # runner_writer gets a plain text response (not JSON schema)
        '"""Generated runner"""\nimport os\ndef main(): pass\n',
    ]

    def mock_llm(messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Mock LLM that returns different responses per call."""
        idx = min(call_count["n"], len(mock_responses) - 1)
        call_count["n"] += 1
        return mock_responses[idx]

    result = run_generator(
        request="I want to scrape job listings and summarize them daily",
        llm_call_fn=mock_llm,
        output_path=tmp_path / "test_output.zip",
    )

    # Verify all 5 nodes produced output
    assert "intake_parser" in result
    assert "schema_designer" in result
    assert "yaml_writer" in result
    assert "runner_writer" in result
    assert "packager" in result

    # Verify final zip was created at the specified output path
    output_zip = tmp_path / "test_output.zip"
    assert output_zip.exists()

    # Verify zip contents
    with zipfile.ZipFile(output_zip, "r") as zf:
        names = zf.namelist()
        assert "pipeline.yaml" in names
        assert "runner.py" in names
        assert "README.md" in names
