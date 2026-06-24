import asyncio
import argparse
from agents.ingestion import run_ingestion_agent
from agents.triage import run_triage_agent
from agents.dispatch import run_dispatch_agent

async def main():
    parser = argparse.ArgumentParser(description="Crisis Coordinator ADK Pipeline")
    parser.add_argument("--report", type=str, 
                        default="Massive earthquake reported in Los Angeles. Buildings collapsed, many injured. Need medics and water immediately.",
                        help="Raw distress report to ingest.")
    args = parser.parse_args()

    print("\n--- [STARTING ADK PIPELINE] ---")
    
    # Step 1: Ingestion
    incident = run_ingestion_agent(args.report)
    
    # Step 2: Triage
    triaged_incident = run_triage_agent(incident)
    
    # Step 3: Dispatch (Requires MCP and HITL)
    await run_dispatch_agent(triaged_incident)
    
    print("--- [PIPELINE COMPLETE] ---\n")

if __name__ == "__main__":
    asyncio.run(main())
