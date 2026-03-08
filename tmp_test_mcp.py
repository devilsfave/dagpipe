import asyncio
import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import Response

mcp = FastMCP("test-server", host="127.0.0.1", port=8001)

@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return Response("ok", status_code=200)

async def test_server():
    # Run the server in the background
    server_task = asyncio.create_task(mcp.run_streamable_http_async())
    
    # Wait for server to start
    await asyncio.sleep(2)
    
    try:
        async with httpx.AsyncClient() as client:
            # Test custom route
            resp = await client.get("http://127.0.0.1:8001/health")
            print(f"Health check status: {resp.status_code}, body: {resp.text}")
            
            # Test MCP endpoint (default is /mcp)
            resp = await client.get("http://127.0.0.1:8001/mcp")
            print(f"MCP endpoint status: {resp.status_code}")
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
    print("Test finished.")

if __name__ == "__main__":
    asyncio.run(test_server())
