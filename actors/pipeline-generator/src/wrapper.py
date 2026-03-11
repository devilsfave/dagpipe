import sys
import os
import json
from pathlib import Path

# Add the src/ directory (parent of the dagpipe package) to sys.path
# so that `from dagpipe.generator.pipeline_generator import run_generator` resolves correctly.
# Directory structure: src/dagpipe/__init__.py, src/dagpipe/generator/pipeline_generator.py
sys.path.insert(0, os.path.dirname(__file__))  # inserts src/ into path

from groq import Groq
from dagpipe.generator.pipeline_generator import run_generator

def main():
    try:
        # Read Apify inputs provided via Node process stdin
        input_data = sys.stdin.read()
        if not input_data:
            raise ValueError("No input data provided")
        
        parsed = json.loads(input_data)
        request_desc = parsed.get("description", "")
        api_key = parsed.get("groq_api_key", "")
        
        if not request_desc:
            raise ValueError("Missing 'description'")
        if not api_key:
            raise ValueError("Missing 'groq_api_key'")
            
        os.environ['GROQ_API_KEY'] = api_key
        
        # Resolve model name once at startup
        from dagpipe.registry import ModelRegistry
        model_reg = ModelRegistry(groq_api_key=api_key)
        # Use the exact same string from registry.py _FALLBACK_MODELS
        resolved_model = model_reg.validate_model("llama-3.3-70b-versatile", provider="groq")
        
        client = Groq(api_key=api_key)
        
        def call_groq(messages):
            resp = client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                max_tokens=3000,
                temperature=0,
            )
            return resp.choices[0].message.content

        # Create output path in a temp dir
        out_dir = Path(os.environ.get("APIFY_DEV_STORAGE", "/tmp")) / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_zip = out_dir / "pipeline_generated.zip"
        
        # Run generator
        result = run_generator(request_desc, call_groq, output_path=out_zip)
        
        # Check if packager succeeded
        if "packager" not in result:
            raise RuntimeError("Generator failed to complete packaging. Check trace: " + str(result))
            
        # Write output to stdout so Node.js can parse it
        zip_path_str = result["packager"]["zip_path"]
        files = result["packager"].get("files_included", [])
        zip_filename = result["packager"].get("zip_filename", "latest_pipeline.zip")
        
        output = {
            "status": "success",
            "zip_path": zip_path_str,
            "files_included": files,
            "zip_filename": zip_filename
        }
        print(json.dumps(output))
        sys.exit(0)
    except Exception as e:
        error_out = {
            "status": "error",
            "message": str(e)
        }
        print(json.dumps(error_out))
        sys.exit(1)

if __name__ == "__main__":
    main()
