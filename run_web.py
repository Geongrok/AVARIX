"""Launch the web interface for Intellex.

Usage:  python run_web.py [--port 8000] [--host 0.0.0.0]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MPLBACKEND", "Agg")

import uvicorn  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Run the Intellex web UI")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()

    print("=" * 60)
    print("  Intellex - Web Interface")
    print(f"  Open: http://127.0.0.1:{args.port}")
    print("=" * 60)
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()

