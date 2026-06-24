import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from apis import get_usgs_earthquakes, get_gdacs_alerts
import json

app = Server("crisis_mcp_server")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_usgs_earthquakes",
            description="Get recent earthquakes globally.",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_magnitude": {
                        "type": "number",
                        "description": "Minimum magnitude to filter"
                    }
                }
            }
        ),
        Tool(
            name="query_gdacs_alerts",
            description="Get current global disaster alerts (Red/Orange).",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "query_usgs_earthquakes":
        min_mag = arguments.get("min_magnitude", 4.0)
        result = get_usgs_earthquakes(min_mag)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    elif name == "query_gdacs_alerts":
        result = get_gdacs_alerts()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    else:
        raise ValueError(f"Unknown tool: {name}")

async def run_server():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(run_server())
