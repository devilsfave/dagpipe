import os
import sys
from pathlib import Path
from typing import Any

# Add src to sys.path
sys.path.append(str(Path(__file__).parent / "src"))

from dagpipe.generator.pipeline_generator import run_generator

def mock_llm(messages: list) -> str:
    # Very basic mock that returns a V2-style runner script when asked
    content = str(messages)
    if "runner_writer" in str(messages) or "runner script" in str(messages).lower():
        return """
import os
from pathlib import Path
from groq import Groq
from dagpipe.dag import PipelineOrchestrator, DAGNode
from dagpipe.registry import ModelRegistry
from dagpipe.router import ModelRouter

def summarize(context: dict, model=None) -> dict:
    return {"summary": "news summary"}

def classify(context: dict, model=None) -> dict:
    return {"sentiment": "positive"}

def main():
    registry = {"summarize": summarize, "classify": classify}
    model_reg = ModelRegistry(groq_api_key=os.environ.get("GROQ_API_KEY"))
    router = ModelRouter(
        low_complexity_fn=lambda x: "low",
        high_complexity_fn=lambda x: "high",
        fallback_fn=lambda x: "fallback",
        rpm_limit=30
    )
    orch = PipelineOrchestrator(
        nodes=Path(__file__).parent / "pipeline.yaml",
        node_registry=registry,
        router=router,
        model_registry=model_reg,
    )
    state, run = orch.run(initial_state={"input": "news text"})
    print(f"Status: {run.status}")

if __name__ == "__main__":
    main()
"""
    # Fallback for other nodes if needed (though we mostly care about runner_writer)
    return "{}"

def test_gen():
    request = "summarize news articles and classify sentiment"
    # We use the fallback_runner logic if model=None in run_generator
    # But run_generator expects a callable.
    # Let's use a very simple mock that returns what we expect from schema_designer etc.
    
    # Actually, the simplest way to test the TEMPLATE logic in runner_writer and _fallback_runner
    # is to call them directly or via run_generator with our mock.
    
    output_zip = Path("test_output.zip")
    if output_zip.exists():
        output_zip.unlink()

    print(f"Running generator for: {request}")
    # run_generator uses the same llm_call_fn for all nodes.
    # We need it to return valid JSON for the first few nodes.
    
    def multi_mock(messages: list) -> str:
        msg_str = str(messages)
        if "IntakeOutput" in msg_str:
            return '{"use_case": "summarize and classify", "steps": ["summarize", "classify"], "domain": "news", "estimated_nodes": 2}'
        if "DAGDesignOutput" in msg_str:
            return '{"nodes": [{"id": "summarize", "fn_name": "summarize", "depends_on": [], "complexity": 0.5, "description": "sum", "is_deterministic": false, "assert_logic": "lambda x: True", "assert_message": "err"}, {"id": "classify", "fn_name": "classify", "depends_on": ["summarize"], "complexity": 0.3, "description": "class", "is_deterministic": false}]}'
        if "runner_writer" in msg_str or "runner script" in msg_str.lower():
            # Return a string that SHOULD be what our prompt generates
            return mock_llm(messages)
        return "{}"

    result = run_generator(request, multi_mock, output_path=output_zip)
    
    print("Generator finished.")
    if output_zip.exists():
        print(f"Zip created at {output_zip}")
        # Unzip and check runner.py
        import zipfile
        with zipfile.ZipFile(output_zip, 'r') as zip_ref:
            zip_ref.extractall("test_extracted")
        
        runner_path = Path("test_extracted/runner.py")
        if runner_path.exists():
            content = runner_path.read_text()
            print("--- runner.py content snippet ---")
            print("\n".join(content.splitlines()[:15]))
            
            # Check for V2 patterns
            checks = [
                "from dagpipe.registry import ModelRegistry",
                "ModelRegistry(",
                "state, run = orch.run"
            ]
            for check in checks:
                if check in content:
                    print(f"✅ Found: {check}")
                else:
                    print(f"❌ NOT FOUND: {check}")
            
            # Check syntax
            try:
                compile(content, "runner.py", "exec")
                print("✅ Syntax is valid.")
            except Exception as e:
                print(f"❌ Syntax error: {e}")
        else:
            print("❌ runner.py not found in zip")
    else:
        print("❌ Zip file was not created")

if __name__ == "__main__":
    test_gen()
