import os
import asyncio
from apify import Actor
from fastmcp import FastMCP
from starlette.responses import Response, JSONResponse
from starlette.routing import Route
from starlette.types import Scope, Receive, Send
from groq import Groq
from dagpipe.generator.pipeline_generator import run_generator
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────
# Apify Standby settings
HOST = '0.0.0.0'
PORT = int(os.environ.get('ACTOR_WEB_SERVER_PORT') or os.environ.get('APIFY_CONTAINER_PORT') or 5001)
SESSION_TIMEOUT_SECS = 300

# ── MCP Logic ────────────────────────────────────────────────────────────────
mcp = FastMCP(
    "dagpipe-generator", 
    description="DagPipe Generator — Translates plain English into a robust, crash-proof DagPipe Python workflow.",
    stateless_http=True,
    json_response=True
)

@mcp.tool()
def generate_pipeline(description: str) -> dict:
    """Generate a complete, crash-proof DagPipe automation workflow from a plain-English description."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"status": "error", "message": "GROQ_API_KEY missing."}
    
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

        # Output to /tmp in the container
        out_dir = Path("/tmp/generated_pipelines")
        out_dir.mkdir(parents=True, exist_ok=True)
        clean_desc = "".join(c if c.isalnum() else "_" for c in description[:15]).strip("_")
        out_zip = out_dir / f"pipeline_{clean_desc}.zip"
        
        result = run_generator(description, call_groq, output_path=out_zip)
        
        if "packager" not in result:
            return {"status": "error", "message": "Packaging failed."}
            
        return {
            "status": "success",
            "zip_path": str(result["packager"]["zip_path"]),
            "files_included": result["packager"].get("files_included", []),
            "message": f"Successfully generated pipeline."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ── Smithery / Glama Config Endpoint ─────────────────────────────────────────
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

# ── Apify Standby & Readiness Probe Handler ──────────────────────────────────
async def standby_handler(scope: Scope, receive: Receive, send: Send):
    # Detect readiness probe
    headers = dict(scope.get('headers', []))
    if b'x-apify-container-server-readiness-probe' in headers:
        response = Response(content="ok", status_code=200)
        await response(scope, receive, send)
        return

    # Handle /.well-known/mcp-config
    if scope['path'] == '/.well-known/mcp-config':
        response = await mcp_config(None)
        await response(scope, receive, send)
        return

    # Forward other traffic to FastMCP (Starlette app)
    await mcp.as_asgi()(scope, receive, send)

# ── Main Entry ─────────────────────────────────────────────────────────────
async def main():
    async with Actor:
        print(f"Starting DagPipe MCP Server on {HOST}:{PORT}")
        # Note: In a production Standby actor, you'd typically use a proper 
        # ASGI server like uvicorn to handle the traffic persistent.
        import uvicorn
        config = uvicorn.Config(
            standby_handler, 
            host=HOST, 
            port=PORT, 
            log_level="info",
            timeout_keep_alive=SESSION_TIMEOUT_SECS
        )
        server = uvicorn.Server(config)
        await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
