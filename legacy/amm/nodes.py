"""AMM Phase 5 — DAG Node Functions

One function per DAG node. Each function:
1. Loads its SOUL.md (YAML frontmatter + markdown body)
2. Builds context within the 16K token budget
3. Calls the LLM via constrained generation
4. Returns a validated Pydantic model

Deterministic nodes (scaffold, deploy) run shell commands directly.

These functions are resolved by name from dag_config.yaml via dag.py.
"""
import json
import subprocess
import sys
import os
from pathlib import Path
from typing import Any

import yaml

from .config import AMM_SOULS_DIR, AMM_BUILD_OUTPUT_DIR
from .schemas import SpecOutput, ScaffoldOutput, CodeOutput, DesignOutput, DeployOutput
from .context import build_context
from .constrained import constrained_generate


# ─────────────────────────────────────────────────────────────────────────────
# SOUL LOADER — parses YAML frontmatter + markdown body
# ─────────────────────────────────────────────────────────────────────────────

def load_soul(node_id: str) -> tuple[dict, str]:
    """Load a SOUL.md file for a DAG node.

    Args:
        node_id: Matches filename in amm/souls/ (e.g. "pm_spec" → "pm_spec.md")

    Returns:
        Tuple of (frontmatter_dict, system_prompt_markdown)
    """
    soul_path = AMM_SOULS_DIR / f"{node_id}.md"
    if not soul_path.exists():
        return {}, f"You are an AI assistant executing node: {node_id}"

    raw = soul_path.read_text(encoding="utf-8")

    # Split YAML frontmatter from markdown body
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw  # No frontmatter — entire file is the prompt

    frontmatter_raw = parts[1]
    body = parts[2].strip()
    meta = yaml.safe_load(frontmatter_raw) or {}
    return meta, body


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — build context from upstream dependencies
# ─────────────────────────────────────────────────────────────────────────────

def _format_upstream_context(context: dict) -> str:
    """Format upstream node outputs into a readable context string."""
    parts = []
    for key, value in context.items():
        if key.startswith("__"):
            continue  # Skip internal keys
        if isinstance(value, dict):
            parts.append(f"### Output from {key}:\n```json\n{json.dumps(value, indent=2)}\n```")
        elif isinstance(value, str):
            parts.append(f"### {key}:\n{value}")
    return "\n\n".join(parts)


def _make_llm_call_fn(model):
    """Create a callable that wraps a crewai.LLM.call() as (messages) → str."""
    def call_fn(messages, **kwargs):
        return model.call(messages, **kwargs)
    return call_fn


# ─────────────────────────────────────────────────────────────────────────────
# NODE FUNCTIONS — one per DAG node
# ─────────────────────────────────────────────────────────────────────────────

def pm_generate_spec(context: dict, model=None) -> dict:
    """PM node: council concept → technical specification.

    Args:
        context: Must contain 'concept' key.
        model: LLM instance from router.
    """
    meta, system_prompt = load_soul("pm_spec")
    concept = context.get("concept", "Unknown concept")

    task_description = (
        f"## Task: Generate Technical Specification\n\n"
        f"Council-approved concept:\n{concept}\n\n"
    )
    if "live_versions" in context and context["live_versions"]:
        task_description += f"{context['live_versions']}\n\n"
        
    task_description += "Produce a complete technical specification. Output as JSON matching SpecOutput."

    messages = build_context(
        system_prompt=system_prompt,
        task_description=task_description,
    )

    result = constrained_generate(
        messages=messages,
        schema=SpecOutput,
        llm_call_fn=_make_llm_call_fn(model),
    )

    # Write spec to disk for inspection
    spec_path = AMM_BUILD_OUTPUT_DIR / "01_specification.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    return result.model_dump()


def scaffold_project(context: dict, model=None) -> dict:
    """Scaffold node: deterministic — no LLM.

    Creates the project directory structure. Uses npx create-next-app
    or equivalent based on the spec's tech_stack.
    """
    spec = context.get("pm_spec", {})
    app_name = spec.get("app_name", "amm-mvp")
    tech_stack = spec.get("tech_stack", [])

    project_dir = AMM_BUILD_OUTPUT_DIR / app_name
    # FIX 3: Skip if directory exists and contains package.json
    if project_dir.exists() and (project_dir / "package.json").exists():
        print(f"  ⏭️ Scaffold skipped: {app_name} already exists with package.json")
        files_created = ["package.json"]
        
        output = ScaffoldOutput(
            files_created=files_created,
            project_root=str(project_dir),
            success=True,
        )
        report_path = AMM_BUILD_OUTPUT_DIR / "02a_scaffold.json"
        report_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")
        return output.model_dump()

    # FIX: Forcefully wipe project directory to prevent create-next-app conflicts
    # This handles partially deleted folders left behind by shutil.rmtree during a --fresh run
    if project_dir.exists():
        import shutil
        import stat
        
        def remove_readonly(func, path, excinfo):
            import os
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass
                
        shutil.rmtree(project_dir, onerror=remove_readonly)
        
        # Fallback for ultra-stubborn Windows node_modules
        if project_dir.exists() and sys.platform == "win32":
            subprocess.run(["cmd.exe", "/c", "rmdir", "/s", "/q", str(project_dir)], capture_output=True)

    project_dir.mkdir(parents=True, exist_ok=True)

    files_created = []

    # Check if Next.js is in the stack
    is_nextjs = any("next" in t.lower() for t in tech_stack)

    if is_nextjs:
        # Try to scaffold with create-next-app
        # FIX 2: Verify cwd exists before running
        target_cwd = Path(AMM_BUILD_OUTPUT_DIR)
        target_cwd.mkdir(parents=True, exist_ok=True)
        
        # supervisor-idempotent-patch: Start
        def patch_next_config(project_dir: Path):
            config_path = project_dir / "next.config.ts"
            if not config_path.exists():
                config_path = project_dir / "next.config.js"
                if not config_path.exists():
                    return
            
            content = config_path.read_text(encoding="utf-8")
            if "output: 'export'" in content:
                print("  ⏭️ next.config patch skipped: already present")
                return
                
            print(f"  🔧 Patching {config_path.name} for static export + unoptimized images")
            # Injects Supervisor-mandated fixes together
            patch = "\n  output: 'export',\n  images: { unoptimized: true },"
            
            new_content = content
            # Bug 2 Fix: Handle multiple common patterns and verify injection
            if "const nextConfig: NextConfig = {" in content:
                new_content = content.replace("const nextConfig: NextConfig = {", f"const nextConfig: NextConfig = {{{patch}")
            elif "const nextConfig = {" in content:
                new_content = content.replace("const nextConfig = {", f"const nextConfig = {{{patch}")
            elif "export default {" in content:
                new_content = content.replace("export default {", f"export default {{{patch}")
            
            if "output: 'export'" not in new_content:
                raise RuntimeError(
                    f"patch_next_config failed: could not locate config object in {config_path}. "
                    "Next.js template may have changed. Manual inspection required."
                )
                
            config_path.write_text(new_content, encoding="utf-8")

        # supervisor-idempotent-patch: End

        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
        try:
            result = subprocess.run(
                [
                    npx_cmd, "-y", "create-next-app@latest",
                    str(project_dir),
                    "--ts", "--tailwind", "--eslint",
                    "--app", "--no-git", "--use-npm",
                    "--import-alias", "@/*", "--yes",
                ],
                # FIX 1: Merge stderr into stdout instead of capture_output=True
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, 
                timeout=300,  # FIX 1: Increased timeout to 300s for large node_modules
                cwd=str(target_cwd)
            )
            if result.returncode == 0:
                # Patch config for static export (Windows fallback)
                patch_next_config(project_dir)
                # List created files
                for f in project_dir.rglob("*"):
                    if f.is_file():
                        files_created.append(str(f.relative_to(project_dir)))
            else:
                # FIX 3: Log the full output and exit code on failure
                raise RuntimeError(f"create-next-app failed (exit code {result.returncode}): {result.stdout}")
        except Exception as e:
            raise RuntimeError(f"Scaffold execution failed: {e}")

    if not files_created:
        if is_nextjs:
            raise RuntimeError("Scaffold failed: No files were created by create-next-app.")
        # Fallback: create minimal structure
        for d in ["app", "public", "prisma"]:
            (project_dir / d).mkdir(parents=True, exist_ok=True)
        (project_dir / "package.json").write_text(
            json.dumps({"name": app_name, "version": "0.1.0", "private": True}, indent=2),
            encoding="utf-8",
        )
        files_created = ["package.json"]

    output = ScaffoldOutput(
        files_created=files_created[:50],  # Cap list size
        project_root=str(project_dir),
        success=len(files_created) > 0,
    )

    # Write scaffold report
    report_path = AMM_BUILD_OUTPUT_DIR / "02a_scaffold.json"
    report_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    return output.model_dump()


def write_db_schema(context: dict, model=None) -> dict:
    """Write database schema and data access layer.

    Args:
        context: Must contain 'pm_spec' and 'scaffold' outputs.
        model: LLM instance from router.
    """
    meta, system_prompt = load_soul("write_db")
    upstream = _format_upstream_context(context)

    task_description = (
        f"## Task: Implement Database Schema\n\n"
        f"Using the PM specification and scaffold output below, create the "
        f"database schema and data access layer.\n\n"
        f"Output as JSON matching CodeOutput schema."
    )

    messages = build_context(
        system_prompt=system_prompt,
        task_description=task_description,
        immediate_context=upstream,
    )

    result = constrained_generate(
        messages=messages,
        schema=CodeOutput,
        llm_call_fn=_make_llm_call_fn(model),
    )

    # Write code to disk
    _write_code_to_project(context, result)

    # Write report
    report_path = AMM_BUILD_OUTPUT_DIR / "02b_database.json"
    report_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    return result.model_dump()


def write_auth_ui(context: dict, model=None) -> dict:
    """Build authentication logic and core UI components.

    Args:
        context: Must contain 'pm_spec' and 'write_db' outputs.
        model: LLM instance from router.
    """
    meta, system_prompt = load_soul("write_auth_ui")
    upstream = _format_upstream_context(context)

    task_description = (
        f"## Task: Build Auth + UI\n\n"
        f"Using the PM specification and database schema, build the "
        f"authentication and core UI components.\n\n"
        f"Output as JSON matching CodeOutput schema."
    )

    messages = build_context(
        system_prompt=system_prompt,
        task_description=task_description,
        immediate_context=upstream,
    )

    result = constrained_generate(
        messages=messages,
        schema=CodeOutput,
        llm_call_fn=_make_llm_call_fn(model),
    )

    _write_code_to_project(context, result)

    report_path = AMM_BUILD_OUTPUT_DIR / "02c_ui.json"
    report_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    return result.model_dump()


def design_polish(context: dict, model=None) -> dict:
    """Apply design system polish — colors, typography, spacing.

    Args:
        context: Must contain 'pm_spec' and 'write_auth_ui' outputs.
        model: LLM instance from router.
    """
    meta, system_prompt = load_soul("design_polish")
    upstream = _format_upstream_context(context)

    task_description = (
        f"## Task: Apply Design Polish\n\n"
        f"Using the specification and current UI code, apply professional "
        f"design polish — cohesive colors, typography, spacing.\n\n"
        f"Output as JSON matching DesignOutput schema."
    )

    messages = build_context(
        system_prompt=system_prompt,
        task_description=task_description,
        immediate_context=upstream,
    )

    result = constrained_generate(
        messages=messages,
        schema=DesignOutput,
        llm_call_fn=_make_llm_call_fn(model),
    )

    # Write CSS to disk
    spec = context.get("pm_spec", {})
    app_name = spec.get("app_name", "amm-mvp")
    project_dir = AMM_BUILD_OUTPUT_DIR / app_name
    if result.filename:
        css_path = project_dir / result.filename
        css_path.parent.mkdir(parents=True, exist_ok=True)
        css_path.write_text(result.css_changes, encoding="utf-8")

    return result.model_dump()


def install_dependencies(context: dict, model=None) -> dict:
    """Deterministic node: Runs npm install in the project directory."""
    # Bug 1 Fix: Pull project_dir from scaffold output for DAG consistency
    scaffold = context.get("scaffold", {})
    project_root = scaffold.get("project_root")
    if not project_root:
        # Fallback to config path if scaffold is missing (e.g. testing)
        spec = context.get("pm_spec", {})
        app_name = spec.get("app_name", "amm-mvp")
        project_root = str(AMM_BUILD_OUTPUT_DIR / app_name)
    
    project_dir = Path(project_root)
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    print(f"  📦 Running 'npm install' in {project_dir.name}...")
    
    try:
        # Bug 2 Fix: Wrap validation to prevent raw traceback for Herbert
        subprocess.run([npm_cmd, "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        error_msg = f"FATAL: '{npm_cmd}' not found on PATH. Node.js is required. Error: {e}"
        print(f"  ❌ {error_msg}")
        return {"success": False, "error": error_msg}

    try:
        env = os.environ.copy()
        env["CI"] = "true"
        result = subprocess.run(
            [npm_cmd, "install"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
            cwd=str(project_dir),
            env=env
        )
        
        if result.returncode != 0:
            error_msg = f"npm install failed (exit {result.returncode}):\n{result.stderr}"
            print(f"  ❌ {error_msg}")
            return {"success": False, "error": error_msg, "log": result.stdout}
        
        print(f"  ✅ Dependencies installed successfully.")
        return {"success": True, "log": result.stdout}
    except Exception as e:
        return {"success": False, "error": str(e)}


def deploy_cloudflare(context: dict, model=None) -> dict:
    """Deploy to Cloudflare Pages via wrangler CLI. Deterministic — no LLM.

    Args:
        context: Must contain 'pm_spec' and 'design_polish' outputs.
        model: Not used (deterministic node).
    """
    spec = context.get("pm_spec", {})
    app_name = spec.get("app_name", "amm-mvp")
    project_dir = AMM_BUILD_OUTPUT_DIR / app_name

    deploy_log = ""
    live_url = ""
    success = False

    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"

    try:
        env = os.environ.copy()
        env["CI"] = "true"
        
        # Build the project first
        build_result = subprocess.run(
            [npm_cmd, "run", "build"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            cwd=str(project_dir),
            env=env
        )
        deploy_log += f"BUILD:\n{build_result.stdout}\n{build_result.stderr}\n"

        if build_result.returncode == 0:
            # Explicitly create project to prevent interactive prompt on first deploy
            create_result = subprocess.run(
                [npx_cmd, "wrangler", "pages", "project", "create", app_name, "--production-branch", "main"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                cwd=str(project_dir),
                env=env
            )
            deploy_log += f"CREATE PROJECT:\n{create_result.stdout}\n{create_result.stderr}\n"

            # Deploy with wrangler
            # If 'out' exists, it's a static export
            deploy_dir = ".next"
            if (project_dir / "out").exists():
                deploy_dir = "out"
                print(f"  📂 Detected static export 'out/' directory. Using for deployment.")

            deploy_result = subprocess.run(
                [npx_cmd, "wrangler", "pages", "deploy", deploy_dir, "--project-name", app_name],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                cwd=str(project_dir),
                env=env
            )
            deploy_log += f"DEPLOY:\n{deploy_result.stdout}\n{deploy_result.stderr}\n"

            if deploy_result.returncode == 0:
                # Extract URL from wrangler output
                for line in deploy_result.stdout.split("\n"):
                    if ".pages.dev" in line or "https://" in line:
                        # Clean up URL (Wrangler sometimes adds decorative prefixes)
                        live_url = line.strip().split(" ")[-1]
                        success = True
                        break
                
                if not live_url:
                    raise RuntimeError(
                        f"Wrangler exited 0 but no live URL found in output:\n{deploy_result.stdout}"
                    )
            else:
                deploy_log += f"DEPLOY FAILED (exit {deploy_result.returncode}):\n{deploy_result.stderr}"
        else:
            deploy_log += "BUILD FAILED — skipping deploy\n"

    except subprocess.TimeoutExpired:
        deploy_log += "TIMEOUT during build/deploy\n"
    except Exception as e:
        deploy_log += f"ERROR: {e}\n"

    output = DeployOutput(
        live_url=live_url,
        deploy_log=deploy_log[-2000:],  # Cap log size
        success=success,
    )

    report_path = AMM_BUILD_OUTPUT_DIR / "04_deployment.json"
    report_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    if not success:
        raise RuntimeError(f"Deploy failed:\n{deploy_log}")

    return output.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — write generated code to project directory
# ─────────────────────────────────────────────────────────────────────────────

def _write_code_to_project(context: dict, result: CodeOutput) -> None:
    """Write a CodeOutput's code to the project directory."""
    spec = context.get("pm_spec", {})
    app_name = spec.get("app_name", "amm-mvp")
    project_dir = AMM_BUILD_OUTPUT_DIR / app_name

    if not hasattr(result, "files") or not result.files:
        raise ValueError("CodeOutput must contain a non-empty 'files' list. Found none.")

    for code_file in result.files:
        if code_file.filename and code_file.code:
            target = project_dir / code_file.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code_file.code, encoding="utf-8")
            print(f"  📝 Wrote: {code_file.filename}")
        else:
            print(f"  ⚠️ Skipped empty file entry in CodeOutput")
