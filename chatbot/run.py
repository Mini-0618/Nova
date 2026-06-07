"""
RootCode Chatbot Launcher
Easy way to start the chatbot server.
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from chatbot.api import run_chatbot


def main():
    parser = argparse.ArgumentParser(description="RootCode Chatbot Launcher")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5001, help="Port (default: 5001)")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    parser.add_argument("--public", action="store_true", help="Bind to 0.0.0.0")

    args = parser.parse_args()
    host = "0.0.0.0" if args.public else args.host

    print("=" * 50)
    print("  RootCode AI Chatbot")
    print("=" * 50)
    print(f"  Local:  http://localhost:{args.port}")
    if args.public:
        print(f"  All:    http://0.0.0.0:{args.port}")
    print("=" * 50)
    print("  Ctrl+C to stop")
    print()

    run_chatbot(host=host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
