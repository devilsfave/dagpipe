"""DagPipe Generator — Pipeline Generator

A 5-node DagPipe pipeline that runs ON DagPipe to generate custom
pipeline templates from a user's plain English description.

Nodes:
  intake_parser → schema_designer → yaml_writer → runner_writer → packager
"""
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

import yaml

from dagpipe.constrained import constrained_generate
from dagpipe.dag import DAGNode, FilesystemCheckpoint, PipelineOrchestrator
from dagpipe.router import ModelRouter

from .schemas import (
    DAGDesignOutput,
    IntakeOutput,
    NodeSpec,
    PackageOutput,
    RunnerOutput,
    YAMLOutput,
)


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1: intake_parser
# ─────────────────────────────────────────────────────────────────────────────

def intake_parser(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Parse a user's plain English request into structured fields.

    Reads 'request' from context (injected via initial_state).
    Uses constrained_generate to produce validated IntakeOutput.
    """
    request = context.get("request", "")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a pipeline design assistant. Analyze the user's "
                "request and extract: the use case summary, ordered list of "
                "steps, the domain, and how many DAG nodes are needed. "
                "Be precise and concise."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Parse this automation request into structured fields:\n\n"
                f"\"{request}\"\n\n"
                f"Identify the use case, break it into sequential steps, "
                f"determine the domain, and estimate how many pipeline "
                f"nodes are needed (typically 3-7)."
            ),
        },
    ]

    result = constrained_generate(
        messages=messages,
        schema=IntakeOutput,
        llm_call_fn=model,
        max_retries=2,
    )
    return result.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2: schema_designer
# ─────────────────────────────────────────────────────────────────────────────

def schema_designer(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Design the DAG structure from parsed intake output.

    Decides node IDs, dependency chain, complexity scores, and descriptions.
    """
    intake = context.get("intake_parser", {})
    use_case = intake.get("use_case", "")
    steps = intake.get("steps", [])
    domain = intake.get("domain", "")

    steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))

    messages = [
        {
            "role": "system",
            "content": (
                "You are a DAG architect. Design a pipeline DAG from the "
                "given steps. Each node needs: id (snake_case), fn_name "
                "id (snake_case), fn_name (same as id), depends_on (list of "
                "upstream node IDs), complexity (0.0-1.0 where higher = "
                "harder), description, and is_deterministic (true only "
                "for final packaging steps that need no LLM). "
                "Additionally, provide assert_logic (a Python lambda string "
                "to validate the node's output) and assert_message for "
                "critical nodes. The last node should typically be "
                "deterministic. Chain nodes linearly unless parallel "
                "execution makes sense.\n\n"
                "RETURN KEY CONTRACTS — assert_logic MUST use these exact keys "
                "(they match what runner.py actually returns):\n"
                "  LLM / process node:  lambda out: bool(out.get('output'))\n"
                "  Save / write node:   lambda out: out.get('file_saved') is True\n"
                "  Load / read node:    lambda out: bool(out.get('loaded_data'))\n"
                "  Fetch / HTTP node:   lambda out: bool(out.get('fetched_data'))\n"
                "  Transform node:      lambda out: bool(out.get('transformed'))\n"
                "  Status / done node:  lambda out: out.get('status') == 'complete'\n"
                "Use ONLY these keys in assert_logic. Do NOT invent other key names."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Design a DAG for this pipeline:\n"
                f"Use case: {use_case}\n"
                f"Domain: {domain}\n"
                f"Steps:\n{steps_text}\n\n"
                f"Return a list of node specifications."
            ),
        },
    ]

    result = constrained_generate(
        messages=messages,
        schema=DAGDesignOutput,
        llm_call_fn=model,
        max_retries=2,
    )
    return result.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3: yaml_writer
# ─────────────────────────────────────────────────────────────────────────────

def yaml_writer(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Render a valid DagPipe YAML config from the DAG design.

    This is deterministic — no LLM call needed. Transforms the
    DAGDesignOutput into the exact YAML format load_dag() expects.
    """
    design = context.get("schema_designer", {})
    nodes = design.get("nodes", [])

    # Build YAML structure matching load_dag() format exactly
    yaml_nodes = []
    for node in nodes:
        yaml_node: dict[str, Any] = {
            "id": node["id"],
            "fn": node["fn_name"],
            "depends_on": node.get("depends_on", []),
            "complexity": node.get("complexity", 0.5),
            "is_deterministic": node.get("is_deterministic", False),
            "description": node.get("description", ""),
            "assert_logic": node.get("assert_logic"),
            "assert_message": node.get("assert_message"),
        }
        yaml_nodes.append(yaml_node)

    yaml_content = yaml.dump(
        {"nodes": yaml_nodes},
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    return {
        "yaml_content": yaml_content,
        "node_count": len(yaml_nodes),
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4: runner_writer
# ─────────────────────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences that LLMs sometimes wrap around code.

    Handles: ```python\n...\n``` and ```\n...\n``` variants.
    Returns the raw code inside, or the original string if no fences found.
    """
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]  # Drop opening fence
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]  # Drop closing fence
    return "\n".join(lines).strip()


def runner_writer(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Generate a complete Python runner script for the pipeline.

    Uses the LLM to write real prompts tailored to each node's purpose.
    Post-processes to strip any markdown code fences from LLM output.
    """
    design = context.get("schema_designer", {})
    yaml_out = context.get("yaml_writer", {})
    nodes = design.get("nodes", [])
    intake = context.get("intake_parser", {})
    use_case = intake.get("use_case", "generated pipeline")

    nodes_desc = "\n".join(
        f"  - {n['id']}: {n.get('description', '')} "
        f"(complexity={n.get('complexity', 0.5)}, "
        f"deterministic={n.get('is_deterministic', False)})"
        for n in nodes
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Python code generator for DagPipe pipelines. "
                "Write a COMPLETE, RUNNABLE Python script. "
                "Output ONLY raw Python — NO markdown, NO code fences, NO backticks.\n\n"
                "You MUST follow this EXACT pattern for V2 DagPipe usage:\n\n"
                "--- EXACT IMPORTS ---\n"
                "import os\n"
                "from pathlib import Path\n"
                "from groq import Groq\n"
                "from dagpipe.dag import PipelineOrchestrator, DAGNode\n"
                "from dagpipe.registry import ModelRegistry\n"
                "from dagpipe.router import ModelRouter\n\n"
                "--- EXACT GROQ CLIENT ---\n"
                "client = Groq(api_key=os.environ.get('GROQ_API_KEY'))\n\n"
                "--- EXACT LLM WRAPPER FUNCTIONS ---\n"
                "def call_groq_8b(messages: list) -> str:\n"
                "    resp = client.chat.completions.create(\n"
                "        model='llama-3.1-8b-instant',\n"
                "        messages=messages,\n"
                "        max_tokens=2048,\n"
                "    )\n"
                "    return resp.choices[0].message.content\n\n"
                "def call_groq_70b(messages: list) -> str:\n"
                "    resp = client.chat.completions.create(\n"
                "        model='llama-3.3-70b-versatile',\n"
                "        messages=messages,\n"
                "        max_tokens=2048,\n"
                "    )\n"
                "    return resp.choices[0].message.content\n\n"
                "--- RETURN KEY CONTRACTS (CRITICAL — follow exactly) ---\n"
                "Every node type has a FIXED return key. Use these EXACTLY. Do NOT invent new keys.\n"
                "The pipeline.yaml assert_logic checks these same keys — mismatches crash the pipeline.\n\n"
                "  LLM / process node:  return {'output': result}\n"
                "  Save / write node:  return {'file_saved': True}\n"
                "    (data = str(context.get('DEPENDENCY_NODE_ID', {}).get('output') or '') before writing)\n"
                "  Load / read node:    return {'loaded_data': data}\n"
                "  Fetch / HTTP node:   return {'fetched_data': data}\n"
                "  Transform node:      return {'transformed': data}\n"
                "  Status / done node:  return {'status': 'complete'}\n\n"
                "--- EXACT ORCHESTRATOR ---\n"
                "router = ModelRouter(\n"
                "    low_complexity_fn=call_groq_8b,\n"
                "    high_complexity_fn=call_groq_70b,\n"
                "    fallback_fn=call_groq_8b,\n"
                "    low_label='llama-3.1-8b-instant',\n"
                "    high_label='llama-3.3-70b-versatile',\n"
                "    fallback_label='llama-3.1-8b-instant',\n"
                "    rpm_limit=30,\n"
                ")\n"
                "orch = PipelineOrchestrator(\n"
                "    nodes=Path(__file__).parent / 'pipeline.yaml',\n"
                "    node_registry=registry,  # 'registry' dict mapped to your functions\n"
                "    router=router,\n"
                "    model_registry=model_reg,\n"
                ")\n"
                "state, run = orch.run(initial_state={'input': '...'})  # V2 returns (state, run)\n\n"
                "For nodes with assertions, use 'assert_fn=eval(node_cfg[\"assert_logic\"])' or a direct lambda.\n"
                "Use these patterns EXACTLY. Do not invent alternative APIs."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a runner script for this pipeline:\n"
                f"Use case: {use_case}\n"
                f"Nodes:\n{nodes_desc}\n\n"
                f"YAML file is named 'pipeline.yaml' in the same directory.\n"
                f"Write REAL prompts for each LLM node tailored to its description.\n"
                f"Output ONLY raw Python code. No markdown. No backticks."
            ),
        },
    ]

    # Use the LLM to generate the script, then strip any markdown fences
    raw = model(messages) if model else _fallback_runner(nodes, use_case)
    script_content = _strip_code_fences(raw)

    return {
        "script_content": script_content,
        "dependencies": ["dagpipe-core", "groq"],
    }


def _fallback_runner(nodes: list[dict[str, Any]], use_case: str) -> str:
    """Generate a basic runner script without an LLM (fallback)."""
    funcs = []
    for n in nodes:
        nid = n.get("id", "unknown")
        desc = n.get("description", "Process data")
        det = n.get("is_deterministic", False)
        if det:
            funcs.append(
                f'def {nid}(context: dict, model=None) -> dict:\n'
                f'    """{desc}"""\n'
                f'    return {{"status": "complete"}}\n'
            )
        else:
            funcs.append(
                f'def {nid}(context: dict, model=None) -> dict:\n'
                f'    """{desc}"""\n'
                f'    result = model([{{"role": "user", "content": '
                f'"{desc}"}}]) if model else "No model"\n'
                f'    return {{"output": result}}\n'
            )

    func_block = "\n\n".join(funcs)
    registry_items = ", ".join(f'"{n["id"]}": {n["id"]}' for n in nodes)

    return (
        f'"""Runner for {use_case}"""\n'
        f'import os, sys\n'
        f'from pathlib import Path\n'
        f'from groq import Groq\n'
        f'from dagpipe.dag import PipelineOrchestrator, load_dag\n'
        f'from dagpipe.registry import ModelRegistry\n'
        f'from dagpipe.router import ModelRouter\n\n'
        f'{func_block}\n\n'
        f'def main():\n'
        f'    registry = {{{registry_items}}}\n'
        f'    model_reg = ModelRegistry(groq_api_key=os.environ.get("GROQ_API_KEY"))\n'
        f'    # V2 load_dag expects a Path\n'
        f'    nodes = load_dag(Path(__file__).parent / "pipeline.yaml")\n'
        f'    orch = PipelineOrchestrator(\n'
        f'        nodes=nodes,\n'
        f'        node_registry=registry,\n'
        f'        model_registry=model_reg,\n'
        f'    )\n'
        f'    state, run = orch.run()\n'
        f'    print(f"Status: {{run.status}}")\n'
        f'    print(f"Cost: ${{run.estimated_total_cost_usd:.4f}}")\n\n'
        f'if __name__ == "__main__":\n'
        f'    main()\n'
    )


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5: packager
# ─────────────────────────────────────────────────────────────────────────────

def _detect_models(script_content: str) -> dict[str, list[str]]:
    """Detect which LLM providers and model names are referenced in runner.py."""
    import re
    groq_models = re.findall(r'model=["\']([^"\']*(llama|mixtral|gemma|whisper)[^"\']*)["\']', script_content, re.IGNORECASE)
    gemini_models = re.findall(r'model=["\']([^"\']*(gemini)[^"\']*)["\']', script_content, re.IGNORECASE)
    return {
        "groq": list(dict.fromkeys(m[0] for m in groq_models)),
        "gemini": list(dict.fromkeys(m[0] for m in gemini_models)),
    }


def _detect_pip_packages(script_content: str) -> list[str]:
    """Parse top-level imports from runner.py and map to pip packages."""
    import re
    packages = ["dagpipe-core"]
    import_map = {
        "groq": "groq", "google.generativeai": "google-generativeai",
        "google.genai": "google-generativeai", "anthropic": "anthropic",
        "openai": "openai", "requests": "requests", "httpx": "httpx",
        "bs4": "beautifulsoup4", "pandas": "pandas", "numpy": "numpy",
    }
    for module, pkg in import_map.items():
        if re.search(rf"^import {re.escape(module)}|^from {re.escape(module)}", script_content, re.MULTILINE):
            if pkg not in packages:
                packages.append(pkg)
    return packages


def _detect_save_files(script_content: str) -> list[str]:
    """Detect output file paths written to disk in runner.py."""
    import re
    found = []
    for m in re.findall(r'Path\([\'"](.*?)[\'"]\)\.write_text', script_content):
        found.append(m)
    for m in re.findall(r'open\([\'"](.*?)[\'"].*?,.*?[\'"]w', script_content):
        found.append(m)
    return list(dict.fromkeys(found))


def _detect_initial_state_keys(script_content: str) -> dict[str, str]:
    """Extract initial_state keys and example values from runner.py."""
    import re
    m = re.search(r'initial_state\s*=\s*\{([^}]+)\}', script_content)
    if not m:
        return {"input": "your input here"}
    pairs = {}
    for kv in re.findall(r'[\'"](\w+)[\'"]\s*:\s*[\'"](.*?)[\'"]', m.group(1)):
        pairs[kv[0]] = kv[1]
    return pairs or {"input": "your input here"}


def _title_from_use_case(use_case: str) -> str:
    """Convert use_case to a title-cased pipeline name."""
    return use_case.strip().rstrip(".").title()


def _slugify_use_case(use_case: str, max_words: int = 5) -> str:
    """Slugify a use_case string into a safe filename component."""
    import re
    words = use_case.strip().split()[:max_words]
    slug = "_".join(re.sub(r"[^a-z0-9]", "", w.lower()) for w in words)
    return slug or "pipeline"


def _generate_readme(
    use_case: str,
    script_content: str,
    yaml_content: str,
    nodes_design: list[dict],
) -> str:
    """Generate a fully dynamic, per-pipeline README with 10 sections."""
    import re
    import yaml as _yaml

    try:
        loaded_yaml = _yaml.safe_load(yaml_content) or {}
        yaml_nodes = loaded_yaml.get("nodes", [])
        node_ids = [n.get("id", "unknown") for n in yaml_nodes]
    except Exception:
        yaml_nodes = []
        node_ids = [n.get("id", "unknown") for n in nodes_design]

    models = _detect_models(script_content)
    uses_groq = bool(models["groq"]) or (not models["gemini"] and "groq" in script_content.lower())
    uses_gemini = bool(models["gemini"])

    packages = _detect_pip_packages(script_content)
    pip_install_cmd = "pip install " + " ".join(packages)
    save_files = _detect_save_files(script_content)
    init_keys = _detect_initial_state_keys(script_content)
    title = _title_from_use_case(use_case)

    def _node_sentence(node: dict, idx: int, total: int) -> str:
        nid = node.get("id", "unknown")
        desc = node.get("description") or nid.replace("_", " ")
        det = node.get("is_deterministic", False)
        prefix = "First" if idx == 0 else ("Finally" if idx == total - 1 else "Then")
        if any(k in nid for k in ("save", "write", "export", "output")):
            return f"{prefix}, it saves the result to disk ({desc})."
        elif any(k in nid for k in ("fetch", "load", "read", "scrape", "collect")):
            return f"{prefix}, it fetches or loads data ({desc})."
        elif det:
            return f"{prefix}, it packages and finalizes everything ({desc})."
        else:
            return f"{prefix}, it runs the '{nid.replace('_', ' ')}' step: {desc}."

    walkthrough_sentences = [
        _node_sentence(n, i, len(yaml_nodes)) for i, n in enumerate(yaml_nodes)
    ] if yaml_nodes else [f"The pipeline executes {len(nodes_design)} steps to {use_case.lower()}. "]
    walkthrough = " ".join(walkthrough_sentences)

    api_key_sections = []
    if uses_groq:
        api_key_sections.append(
            "**Get your free Groq API key:**\n\n"
            "1. Go to https://console.groq.com\n"
            "2. Sign up for a free account (no credit card required)\n"
            "3. Click **API Keys** in the left sidebar\n"
            "4. Click **Create API Key**\n"
            "5. Copy the key — it starts with `gsk_`\n"
            "6. Keep it somewhere safe. You will need it in the next step."
        )
    if uses_gemini:
        api_key_sections.append(
            "**Get your free Google AI Studio API key:**\n\n"
            "1. Go to https://aistudio.google.com/app/apikey\n"
            "2. Sign in with your Google account\n"
            "3. Click **Create API key**\n"
            "4. Copy the key\n"
            "5. Keep it somewhere safe. You will need it in the next step."
        )
    api_key_content = "\n\n".join(api_key_sections) or (
        "This pipeline requires at least one LLM API key. See runner.py imports for details."
    )

    env_vars = []
    if uses_groq:
        env_vars.append(("GROQ_API_KEY", "your-groq-key-here"))
    if uses_gemini:
        env_vars.append(("GOOGLE_API_KEY", "your-gemini-key-here"))
    if not env_vars:
        env_vars.append(("GROQ_API_KEY", "your-key-here"))

    set_env_blocks = []
    for var, placeholder in env_vars:
        set_env_blocks.append(
            f"**{var}**\n\n"
            f"Windows PowerShell:\n"
            f"```powershell\n$env:{var}=\"{placeholder}\"\n```\n\n"
            f"Windows Command Prompt:\n"
            f"```cmd\nset {var}={placeholder}\n```\n\n"
            f"Mac/Linux:\n"
            f"```bash\nexport {var}=\"{placeholder}\"\n```\n"
            f"\n> Replace `{placeholder}` with your actual key.  \n"
            f"> Note: This only lasts for the current terminal session."
        )
    set_env_section = "\n\n---\n\n".join(set_env_blocks)

    slug = _slugify_use_case(use_case)
    node_output_lines = [f"[DagPipe] Starting pipeline: {slug}"]
    for nid in node_ids:
        node_output_lines.append(f"[DagPipe] Node '{nid}' -> running...")
        node_output_lines.append(f"[DagPipe] Node '{nid}' -> complete (checkpointed)")
    node_output_lines.append("[DagPipe] Pipeline complete.")
    expected_output = "\n".join(node_output_lines)

    if save_files:
        out_lines = ["When the pipeline finishes successfully, you will find:"]
        for f in save_files:
            ext = f.rsplit(".", 1)[-1].upper() if "." in f else "file"
            out_lines.append(f"- `{f}` — the output in {ext} format")
        out_lines.append("- `.dagpipe/checkpoints/` — automatic recovery files (do not delete these)")
        output_section = "\n".join(out_lines)
    else:
        output_section = (
            "When the pipeline finishes, the final state dictionary contains results from all nodes.\n"
            "Checkpoint files are written to `.dagpipe/checkpoints/` (do not delete these)."
        )

    dead_letter_lines = [f"  .dagpipe/checkpoints/{nid}.failed.json" for nid in node_ids]
    dead_letter_str = "\n".join(dead_letter_lines) or "  .dagpipe/checkpoints/[node-name].failed.json"

    custom_tips = []
    if init_keys:
        first_key, first_val = next(iter(init_keys.items()))
        custom_tips.append(
            f"To change the input, open `runner.py` and find `initial_state={{'{first_key}': '{first_val}'}}`. "
            f"Replace `{first_val!r}` with any value you want."
        )
    if save_files:
        custom_tips.append(
            f"To change the output filename, find `Path('{save_files[0]}')` in `runner.py` and update the path."
        )
    if len(node_ids) >= 2:
        last_node = node_ids[-1] if not any(k in node_ids[-1] for k in ("save", "write")) else node_ids[-2]
        custom_tips.append(
            f"To add a new step, add a node entry in `pipeline.yaml` after `{last_node}`, "
            f"implement the matching function in `runner.py`, and add it to the `registry` dict."
        )
    if not custom_tips:
        custom_tips.append("Open `runner.py` to adjust prompts, node logic, or output format.")
    customization_section = "\n\n".join(f"{i+1}. {tip}" for i, tip in enumerate(custom_tips[:3]))

    readme = f"""# {title}

{use_case.strip().rstrip('.')}.

---

## What this pipeline does

{walkthrough}

---

## Before you start: what you need

### A. Get your API key

{api_key_content}

### B. Install Python (if not already installed)

```
Check if you have Python: open a terminal and run: python --version
If you see Python 3.12 or higher, you're ready.
If not, go to https://python.org/downloads and install Python 3.12 or higher.
```

### C. Install DagPipe and dependencies

```bash
{pip_install_cmd}
```

---

## Setup: extract and prepare your pipeline

1. Extract the ZIP file to wherever you keep your projects
   - **Windows:** right-click the ZIP > "Extract All" > choose a location
   - **Mac:** double-click the ZIP
   - **Linux:** `unzip {slug}_pipeline.zip -d {slug}`
2. Open a terminal in that folder:
   - **Windows:** click address bar in File Explorer, type `powershell`, press Enter
   - **Mac:** right-click the folder > "New Terminal at Folder"
   - **Linux:** `cd {slug}`

---

## Set your API key

{set_env_section}

---

## Run your pipeline

```bash
python runner.py
```

You will see output like this:

```
{expected_output}
```

---

## Your output

{output_section}

---

## If something goes wrong

**If the pipeline crashes mid-run:** Don't worry — your progress is saved.
Fix the problem and run `python runner.py` again. DagPipe resumes from the last successful step.

**Common errors:**

- **API key error** (`AuthenticationError` / `401`): re-run the "Set your API key" step, then retry.
- **Rate limit error** (`RateLimitError` / `429`): wait 60 seconds, then run `python runner.py` again.
- **Module not found** (`ModuleNotFoundError`): rerun the install command from Section 3.

**If a node fails after 3 retries, failure details are saved to:**

```
{dead_letter_str}
```

Fix the issue and run `python runner.py` — it retries only the failed node.

---

## Customizing this pipeline

{customization_section}

---

## Built with DagPipe

This pipeline was generated by the DagPipe Pipeline Generator.

- **DagPipe library:** https://github.com/devilsfave/dagpipe
- **Pipeline Generator (Apify):** https://apify.com/gastronomic_desk/pipeline-generator
- **MCP Server (use in your IDE):** https://smithery.ai/server/gastronomic-desk/dagpipe-generator

```bash
pip install dagpipe-core
```
"""
    return readme


def packager(context: dict[str, Any], model: Any = None) -> dict[str, Any]:
    """Package generated files into a zip archive.

    Deterministic — no LLM call. Writes YAML, runner script, and a
    dynamically generated README to a temp directory, then zips them.
    """
    yaml_out = context.get("yaml_writer", {})
    runner_out = context.get("runner_writer", {})
    intake = context.get("intake_parser", {})
    design = context.get("schema_designer", {})
    use_case = intake.get("use_case", "generated_pipeline")

    yaml_content = yaml_out.get("yaml_content", "")
    script_content = runner_out.get("script_content", "")
    dependencies = runner_out.get("dependencies", [])
    nodes_design = design.get("nodes", [])

    # Generate a dynamic, per-pipeline README from the finalized code
    readme = _generate_readme(
        use_case=use_case,
        script_content=script_content,
        yaml_content=yaml_content,
        nodes_design=nodes_design,
    )

    # Write to a temp directory and zip — never hardcode paths
    tmp_dir = Path(tempfile.mkdtemp(prefix="dagpipe_gen_"))
    (tmp_dir / "pipeline.yaml").write_text(yaml_content, encoding="utf-8")
    (tmp_dir / "runner.py").write_text(script_content, encoding="utf-8")
    (tmp_dir / "README.md").write_text(readme, encoding="utf-8")

    # Create zip with a slugified name derived from the pipeline use_case
    slug = _slugify_use_case(use_case)
    zip_filename = f"{slug}_pipeline.zip"
    zip_path = tmp_dir / zip_filename
    files_to_zip = ["pipeline.yaml", "runner.py", "README.md"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in files_to_zip:
            zf.write(tmp_dir / fname, arcname=fname)

    return {
        "zip_path": str(zip_path),
        "files_included": files_to_zip,
        "zip_filename": zip_filename,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def get_generator_nodes() -> list[DAGNode]:
    """Return the 5 DAGNode objects for the generator pipeline."""
    return [
        DAGNode(
            id="intake_parser",
            fn_name="intake_parser",
            depends_on=[],
            complexity=0.5,
            description="Parse user request into structured fields",
        ),
        DAGNode(
            id="schema_designer",
            fn_name="schema_designer",
            depends_on=["intake_parser"],
            complexity=0.7,
            description="Design the DAG node structure",
        ),
        DAGNode(
            id="yaml_writer",
            fn_name="yaml_writer",
            depends_on=["schema_designer"],
            complexity=0.0,
            is_deterministic=True,
            description="Render DagPipe YAML config",
        ),
        DAGNode(
            id="runner_writer",
            fn_name="runner_writer",
            depends_on=["schema_designer", "yaml_writer"],
            complexity=0.8,
            description="Generate Python runner script",
        ),
        DAGNode(
            id="packager",
            fn_name="packager",
            depends_on=["yaml_writer", "runner_writer"],
            complexity=0.0,
            is_deterministic=True,
            description="Package files into a zip archive",
        ),
    ]


def get_generator_registry() -> dict[str, Callable[..., Any]]:
    """Return the node function registry for the generator pipeline."""
    return {
        "intake_parser": intake_parser,
        "schema_designer": schema_designer,
        "yaml_writer": yaml_writer,
        "runner_writer": runner_writer,
        "packager": packager,
    }


def run_generator(
    request: str,
    llm_call_fn: Callable[..., str],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the full generator pipeline end to end.

    Args:
        request: User's plain English pipeline description.
        llm_call_fn: LLM callable for constrained generation.
        output_path: Optional path to copy the zip file to.

    Returns:
        Pipeline state dict with all node outputs.
    """
    # Use the same LLM for all tiers (user can customize later)
    router = ModelRouter(
        low_complexity_fn=llm_call_fn,
        high_complexity_fn=llm_call_fn,
        fallback_fn=llm_call_fn,
        low_label="generator-llm",
        high_label="generator-llm",
        fallback_label="generator-llm",
    )

    orch = PipelineOrchestrator(
        nodes=get_generator_nodes(),
        node_registry=get_generator_registry(),
        router=router,
        checkpoint_backend=FilesystemCheckpoint(
            Path(tempfile.mkdtemp(prefix="dagpipe_ckpt_"))
        ),
        max_retries=3,
    )

    result = orch.run(initial_state={"request": request})

    # Copy zip to user-specified output path if given
    if output_path and "packager" in result:
        zip_src = Path(result["packager"]["zip_path"])
        if zip_src.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(zip_src, output_path)
            result["packager"]["zip_path"] = str(output_path)

    return result
