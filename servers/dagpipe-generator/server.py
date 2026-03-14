import os
from pathlib import Path
from fastmcp import FastMCP
from groq import Groq
from dagpipe.generator.pipeline_generator import run_generator

mcp = FastMCP(
    "dagpipe-generator",
    instructions="DagPipe Generator — plain English to crash-proof pipeline."
)

@mcp.tool()
def generate_pipeline(description: str) -> dict:
    """Generate a complete crash-proof DagPipe workflow from plain English."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"status": "error",
                "message": "GROQ_API_KEY missing from environment."}
    try:
        client = Groq(api_key=api_key)
        def call_groq(messages):
            resp = client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                messages=messages,
                max_tokens=3000,
                temperature=0,
            )
            return resp.choices[0].message.content
        out_dir = Path.home() / "Desktop" / "DagPipe_Pipelines"
        out_dir.mkdir(parents=True, exist_ok=True)
        clean_desc = "".join(
            c if c.isalnum() else "_" for c in description[:15]
        ).strip("_")
        out_zip = out_dir / f"pipeline_{clean_desc}.zip"
        result = run_generator(description, call_groq, output_path=out_zip)
        if "packager" not in result:
            return {"status": "error", "message": "Packaging failed."}
        zip_path_str = result["packager"]["zip_path"]
        files = result["packager"].get("files_included", [])
        return {
            "status": "success",
            "zip_path": zip_path_str,
            "files_included": files,
            "message": f"Pipeline saved to {zip_path_str}"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",
        port=8000
    )
