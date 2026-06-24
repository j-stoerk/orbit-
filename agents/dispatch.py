from .triage import TriagedIncident
from skills.geocoder import get_coordinates
from skills.resource_matcher import allocate_resources
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
import asyncio
import os
import sys

async def query_mcp_server(tool_name: str, args: dict) -> str:
    # Path to the MCP server script
    server_script = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "server.py")
    
    # We use the stdio client to connect to our own MCP server
    # Need to run it using the venv python
    python_exe = sys.executable
    server_params = StdioServerParameters(command=python_exe, args=[server_script])
    
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=args)
            return result.content[0].text

async def run_dispatch_agent(triaged: TriagedIncident):
    """
    Dispatch Agent: Gathers live context via MCP, matches resources via Skills,
    and requires HITL approval before dispatching.
    """
    print(f"\n[Dispatch Agent] Formulating plan for {triaged.incident.disaster_type} in {triaged.incident.location}")
    
    # 1. Geocode the location (Agent Skill)
    coords = get_coordinates(triaged.incident.location)
    print(f"[Dispatch Agent] Geocoded location: {coords}")
    
    # 2. Query MCP for live data
    live_context = ""
    if triaged.incident.disaster_type == "Earthquake":
        print("[Dispatch Agent] Querying USGS via MCP for recent earthquakes...")
        live_data = await query_mcp_server("query_usgs_earthquakes", {"min_magnitude": 3.0})
        live_context = f"USGS Live Data: {live_data}"
    elif triaged.incident.disaster_type == "Flood":
        print("[Dispatch Agent] Querying GDACS via MCP for flood alerts...")
        live_data = await query_mcp_server("query_gdacs_alerts", {})
        live_context = f"GDACS Live Data: {live_data}"

    print(f"[Dispatch Agent] Retrieved Live Context (length={len(live_context)})")
    
    # 3. Match Resources (Agent Skill)
    needed = {}
    for need in triaged.incident.specific_needs:
        needed[need] = needed.get(need, 0) + (2 if triaged.severity_score == "Critical" else 1)
        
    print(f"[Dispatch Agent] Requesting resources: {needed}")
    success, allocated, msg = allocate_resources(needed)
    print(f"[Dispatch Agent] Resource allocation: {msg} -> {allocated}")
    
    # 4. Human-In-The-Loop Approval (Security Feature)
    print("\n" + "="*50)
    print("!!! PROPOSED DISPATCH PLAN !!!")
    print(f"Incident:   {triaged.incident.disaster_type} at {triaged.incident.location}")
    print(f"Severity:   {triaged.severity_score} ({triaged.urgency_reasoning})")
    print(f"Resources:  {allocated}")
    print("="*50)
    
    # For automated demonstration purposes, we will mock the human input if running non-interactively
    # but the code handles standard input for HITL.
    if sys.stdin.isatty():
        approval = input("APPROVE DISPATCH? (yes/no): ")
    else:
        print("APPROVE DISPATCH? (yes/no): [Auto-approved for demo]")
        approval = "yes"
        
    if approval.lower() in ["y", "yes"]:
        print("[Dispatch Agent] [OK] Plan APPROVED. Teams are being deployed.")
    else:
        print("[Dispatch Agent] [X] Plan REJECTED. Aborting deployment.")
