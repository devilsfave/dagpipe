import os
import asyncio
import contextlib
from apify import Actor
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.responses import Response, JSONResponse
from groq import Groq
from dagpipe.generator.pipeline_generator import run_generator
from pathlib import Path
HOST = '0.0.0.0'
PORT = int(os.environ.get('ACTOR_WEB_SERVER_PORT') or
           os.environ.get('APIFY_CONTAINER_PORT') or 5001)

mcp = FastMCP(
    "dagpipe-generator",
    instructions="DagPipe Generator — plain English to crash-proof pipeline.",
    host=HOST,
    port=PORT
)

@mcp.prompt(
    name="generate-pipeline-example",
    description="Example prompt showing how to generate a crash-proof DagPipe pipeline from plain English."
)
def example_pipeline_prompt() -> str:
    return (
        "Generate a pipeline that fetches a blog post URL, "
        "summarizes it using an LLM, translates the summary "
        "to Spanish, and saves the result to a JSON file."
    )

@mcp.tool(
    annotations=ToolAnnotations(
        title="Generate DagPipe Pipeline",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True
    )
)
def generate_pipeline(description: str) -> dict:
    """Generate a complete crash-proof DagPipe workflow from plain English."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"status": "error", "message": "GROQ_API_KEY missing."}
    
    model = os.environ.get("GROQ_MODEL")
    if not model:
        from dagpipe.registry import ModelRegistry
        model_reg = ModelRegistry(groq_api_key=api_key)
        # Use the exact same string from registry.py _FALLBACK_MODELS
        model = model_reg.validate_model("llama-3.3-70b-versatile", provider="groq")
    
    try:
        client = Groq(api_key=api_key)
        def call_groq(messages):
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=3000,
                temperature=0,
            )
            return resp.choices[0].message.content
        out_dir = Path("/tmp/generated_pipelines")
        out_dir.mkdir(parents=True, exist_ok=True)
        clean_desc = "".join(
            c if c.isalnum() else "_" for c in description[:15]
        ).strip("_")
        out_zip = out_dir / f"pipeline_{clean_desc}.zip"
        result = run_generator(description, call_groq, output_path=out_zip)
        if "packager" not in result:
            return {"status": "error", "message": "Packaging failed."}
        return {
            "status": "success",
            "zip_path": str(result["packager"]["zip_path"]),
            "files_included": result["packager"].get("files_included", []),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.custom_route("/", methods=["GET"])
async def root(request):
    return Response("ok", status_code=200)

@mcp.custom_route("/health", methods=["GET"])
async def readiness(request):
    return Response("ok", status_code=200)

@mcp.custom_route("/.well-known/mcp-config", methods=["GET"])
async def mcp_config_handler(request):
    return JSONResponse({
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://gastronomic-desk--dagpipe-generator-mcp.apify.actor/.well-known/mcp-config",
        "title": "DagPipe Generator Configuration",
        "description": "Configuration for connecting to the DagPipe Generator MCP server",
        "x-query-style": "dot+bracket",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "groqApiKey": {
                "type": "string",
                "title": "Groq API Key",
                "description": "Your free Groq API key from console.groq.com/keys"
            },
            "groqModel": {
                "type": "string",
                "title": "Groq Model",
                "description": "Groq model to use for generation",
                "default": "llama-3.3-70b-versatile",
                "enum": [
                    "llama-3.3-70b-versatile",
                    "llama-3.1-8b-instant",
                    "mixtral-8x7b-32768",
                    "gemma2-9b-it"
                ]
            },
            "debugMode": {
                "type": "boolean",
                "title": "Debug Mode",
                "description": "Enable verbose logging",
                "default": False
            }
        },
        "required": ["groqApiKey"]
    })

async def main():
    async with Actor:
        print(f"DagPipe MCP Server starting on {HOST}:{PORT}")
        await mcp.run_http_async(
            transport="streamable-http",
            stateless_http=True,
            json_response=True
        )

if __name__ == "__main__":
    asyncio.run(main())
