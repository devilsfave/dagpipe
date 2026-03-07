import os
import asyncio
import contextlib
from apify import Actor
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response, JSONResponse
from groq import Groq
from dagpipe.generator.pipeline_generator import run_generator
from pathlib import Path

HOST = '0.0.0.0'
PORT = int(os.environ.get('ACTOR_WEB_SERVER_PORT') or
           os.environ.get('APIFY_CONTAINER_PORT') or 5001)

mcp = FastMCP(
    "dagpipe-generator",
    instructions="DagPipe Generator — plain English to crash-proof pipeline."
)

@mcp.tool()
def generate_pipeline(description: str) -> dict:
    """Generate a complete crash-proof DagPipe workflow from plain English."""
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

mcp_http_app = mcp.http_app(
    path="/mcp",
    stateless_http=True,
    json_response=True
)

async def root(request):
    return Response("ok", status_code=200)

async def readiness(request):
    return Response("ok", status_code=200)

async def mcp_config_handler(request):
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

@contextlib.asynccontextmanager
async def lifespan(app):
    async with mcp_http_app.lifespan(app):
        yield

app = Starlette(
    routes=[
        Route("/", root),
        Route("/health", readiness),
        Route("/.well-known/mcp-config", mcp_config_handler),
        Mount("/", app=mcp_http_app),
    ],
    lifespan=lifespan
)

async def main():
    async with Actor:
        print(f"DagPipe MCP Server starting on {HOST}:{PORT}")
        import uvicorn
        config = uvicorn.Config(
            app,
            host=HOST,
            port=PORT,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
