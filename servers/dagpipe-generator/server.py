import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from groq import Groq
from dagpipe.generator.pipeline_generator import run_generator

from starlette.responses import JSONResponse

# Initialize FastMCP Server
mcp = FastMCP("dagpipe-generator", description="DagPipe Generator — Translates plain English into a robust, crash-proof DagPipe Python workflow.", stateless_http=True, json_response=True)

@mcp.tool()
async def mcp_config(request):
    return JSONResponse({
        "schema": {
            "type": "object", 
            "properties": {
                "groqApiKey": {
                    "type": "string",
                    "title": "Groq API Key",
                    "description": "Get free key at console.groq.com/keys"
                }
            },
            "required": ["groqApiKey"]
        }
    })

@mcp.tool()
def generate_pipeline(description: str) -> dict:
    """
    Generate a complete, crash-proof DagPipe automation workflow from a plain-English description.
    
    Args:
        description: A clear, plain-English description of what the pipeline should do. Example: 'I need a pipeline that reads a tech blog post URL, summarizes it, translates it to Spanish, and saves to a JSON file.'
        
    Returns:
        A dictionary containing:
        - status: 'success' or 'error'
        - zip_path: The absolute path to the generated zip file containing the pipeline.
        - files_included: A list of the files inside the generated zip archive.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "message": "GROQ_API_KEY environment variable is missing. Please set it in your MCP configuration."
        }
    
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

        # Create output path in the user's home directory or current directory
        # We place it in a generated_pipelines folder near where the server runs or a standard temp if preferred
        out_dir = Path.home() / "Desktop" / "DagPipe_Pipelines"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Name the zip file based on the description's first few words to make it recognizable
        clean_desc = "".join(c if c.isalnum() else "_" for c in description[:15]).strip("_")
        out_zip = out_dir / f"pipeline_{clean_desc}.zip"
        
        # Run generator
        result = run_generator(description, call_groq, output_path=out_zip)
        
        if "packager" not in result:
            return {
                "status": "error",
                "message": "Generation failed to complete packaging.",
                "trace": str(result)
            }
            
        zip_path_str = result["packager"]["zip_path"]
        files = result["packager"].get("files_included", [])
        
        return {
            "status": "success",
            "zip_path": zip_path_str,
            "files_included": files,
            "message": f"Successfully generated pipeline. Saved to {zip_path_str}"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == "__main__":
    # Provides stdio transport by default, which is what Cursor/Windsurf/Claude use.
    # To run on Apify, we must use the streamable-http transport
    mcp.run(transport="streamable-http")
