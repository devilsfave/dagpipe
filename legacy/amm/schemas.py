"""AMM Phase 5 — Pydantic Output Schemas

Every LLM call in the DAG gets a typed schema. The `reasoning` field is
always first — this forces the 7B model to chain-of-thought before producing
the answer (critical for small models that generate tokens sequentially).

Used by: nodes.py, constrained.py, dag.py
"""
from pydantic import BaseModel, Field
from typing import Literal


# ─────────────────────────────────────────────────────────────────────────────
# NODE OUTPUT SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class SpecOutput(BaseModel):
    """PM node: council concept → technical specification."""
    reasoning: str = Field(..., description="Your thought process — write this FIRST")
    app_name: str = Field(..., description="Kebab-case application name")
    tech_stack: list[str] = Field(..., description="Exact technology names with versions")
    files_to_create: list[str] = Field(..., description="Relative file paths to create")
    database_schema: dict = Field(default_factory=dict, description="Table definitions")
    revenue_model: str = Field(..., description="How this app makes money")
    confidence: float = Field(..., ge=0.0, le=1.0)
    next_action: Literal["proceed", "abort", "clarify"] = Field(...)


class ScaffoldOutput(BaseModel):
    """Scaffold node: deterministic — no LLM, just file listing after npx."""
    files_created: list[str] = Field(..., description="Files created by scaffolding")
    project_root: str = Field(..., description="Root directory of the project")
    success: bool = Field(...)


class CodeFile(BaseModel):
    filename: str = Field(..., description="Target file path relative to project root")
    code: str = Field(..., description="Complete file contents — no placeholders, no TODOs")


class CodeOutput(BaseModel):
    """Code-writing nodes (write_db, write_auth_ui): spec → code files."""
    reasoning: str = Field(..., description="Analysis of requirements — write this FIRST")
    files: list[CodeFile] = Field(..., description="List of files to create/overwrite (max 3)")
    dependencies: list[str] = Field(default_factory=list, description="npm/pip packages needed")
    confidence: float = Field(..., ge=0.0, le=1.0)
    next_action: Literal["proceed", "abort", "clarify"] = Field(...)


class DesignOutput(BaseModel):
    """Design polish node: UI context → styled components."""
    reasoning: str = Field(..., description="Design rationale — write this FIRST")
    filename: str = Field(..., description="Target CSS/component file path")
    css_changes: str = Field(..., description="CSS/styling code")
    component_updates: list[str] = Field(default_factory=list, description="Components modified")
    confidence: float = Field(..., ge=0.0, le=1.0)
    next_action: Literal["proceed", "abort", "clarify"] = Field(...)


class DeployOutput(BaseModel):
    """Deploy node: deterministic — no LLM, CLI output from wrangler."""
    live_url: str = Field(default="", description="Production URL")
    deploy_log: str = Field(default="", description="CLI output from deployment")
    success: bool = Field(...)


class DebugOutput(BaseModel):
    """Repair node: error context → fixed code (used on validation failure)."""
    reasoning: str = Field(..., description="Error diagnosis — write this FIRST")
    fixed_code: str = Field(..., description="Corrected code")
    explanation: str = Field(..., description="What was wrong and how it was fixed")
    confidence: float = Field(..., ge=0.0, le=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA REGISTRY — node_id → schema class (used by dag.py)
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "pm_spec": SpecOutput,
    "scaffold": ScaffoldOutput,
    "write_db": CodeOutput,
    "write_auth_ui": CodeOutput,
    "design_polish": DesignOutput,
    "deploy": DeployOutput,
    "debug": DebugOutput,
}
