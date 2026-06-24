"""Launch the UNDAC Crisis Coordinator web platform.

    python run.py            # serves http://127.0.0.1:8000
    python run.py --port 9000

Set ANTHROPIC_API_KEY in the environment to enable Claude-powered reasoning;
without it, the agents run on deterministic heuristics (still fully functional).
"""
import argparse
import uvicorn


def main():
    p = argparse.ArgumentParser(description="UNDAC Crisis Coordinator")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()
    print(f"\n  UNDAC Crisis Coordinator -> http://{args.host}:{args.port}\n")
    uvicorn.run("backend.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
