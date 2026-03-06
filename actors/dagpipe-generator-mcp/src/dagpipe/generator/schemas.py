"""DagPipe Generator — Pydantic Schemas

All structured output schemas for the template generator pipeline.
Each pipeline node produces output validated against one of these schemas.
"""
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: intake_parser output
# ─────────────────────────────────────────────────────────────────────────────

class IntakeOutput(BaseModel):
    """Parsed output from a user's plain English pipeline description."""
    use_case: str = Field(description="Short summary of what the pipeline does")
    steps: list[str] = Field(description="Ordered list of pipeline steps")
    domain: str = Field(description="Domain area (e.g. 'marketing', 'data')")
    estimated_nodes: int = Field(description="How many DAG nodes to create")


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: schema_designer output
# ─────────────────────────────────────────────────────────────────────────────

class NodeSpec(BaseModel):
    """Specification for a single DAG node."""
    id: str = Field(description="Unique node identifier (snake_case)")
    fn_name: str = Field(description="Python function name for this node")
    depends_on: list[str] = Field(
        default_factory=list,
        description="List of node IDs this node depends on",
    )
    complexity: float = Field(
        description="Complexity score 0.0-1.0 for model routing",
    )
    description: str = Field(description="What this node does")
    is_deterministic: bool = Field(
        default=False,
        description="True if node needs no LLM call",
    )


class DAGDesignOutput(BaseModel):
    """Complete DAG design with all node specifications."""
    nodes: list[NodeSpec] = Field(description="Ordered list of node specs")


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: yaml_writer output
# ─────────────────────────────────────────────────────────────────────────────

class YAMLOutput(BaseModel):
    """A rendered DagPipe-compatible YAML string."""
    yaml_content: str = Field(description="Valid DagPipe YAML config string")
    node_count: int = Field(description="Number of nodes in the YAML")


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: runner_writer output
# ─────────────────────────────────────────────────────────────────────────────

class RunnerOutput(BaseModel):
    """A complete Python runner script for the generated pipeline."""
    script_content: str = Field(description="Full Python script content")
    dependencies: list[str] = Field(
        description="pip packages required (e.g. ['dagpipe-core', 'groq'])",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 5: packager output
# ─────────────────────────────────────────────────────────────────────────────

class PackageOutput(BaseModel):
    """Final packaged output — a zip file with all generated files."""
    zip_path: str = Field(description="Absolute path to the generated zip file")
    files_included: list[str] = Field(
        description="List of filenames inside the zip",
    )
