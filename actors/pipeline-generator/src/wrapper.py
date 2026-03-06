import sys
import os
import json
from pathlib import Path

# Add the local copy of the dagpipe library to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'dagpipe_lib')))

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
        client = Groq(api_key=api_key)
        
        def call_groq(messages):
            resp = client.chat.completions.create(
                model='llama-3.3-70b-versatile',
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
        
        output = {
            "status": "success",
            "zip_path": zip_path_str,
            "files_included": files
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
