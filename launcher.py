"""
Codex-Local Launcher
Starts all services: API bridge + Web Console + optionally the loop.
"""

import os
import sys
import argparse
import threading
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from bridge import run_server as run_bridge_server
from ui.console import run_console
from runtime.loop import CodexLoop, LoopConfig
from runtime.session import get_manager


def start_bridge(port: int = 8787):
    print(f"[launcher] Bridge starting on port {port}...")
    run_bridge_server(port=port)


def start_console(port: int = 5000):
    print(f"[launcher] Console starting on port {port}...")
    run_console(port=port)


def start_loop(task: str, model: str, provider: str, max_iter: int):
    import asyncio
    config = LoopConfig(
        model=model,
        provider=provider,
        max_iterations=max_iter,
        trust_code_execution=True,
        trust_file_writes=True,
        trust_shell_commands=False,
    )
    loop = CodexLoop(config)

    async def run():
        result = await loop.run_task(task)
        print(f"\n[launcher] Loop complete: {result[:200]}...")

    asyncio.run(run())


def main():
    parser = argparse.ArgumentParser(description="Codex-Local Launcher")
    parser.add_argument("--bridge", action="store_true", help="Start API bridge")
    parser.add_argument("--console", action="store_true", help="Start web console")
    parser.add_argument("--port", type=int, default=8787, help="Bridge port")
    parser.add_argument("--console-port", type=int, default=5000, help="Console port")
    parser.add_argument("--task", "-t", help="Task to run (starts loop immediately)")
    parser.add_argument("--model", "-m", default=os.environ.get("CODEX_MODEL", "deepseek-chat"))
    parser.add_argument("--provider", default=os.environ.get("CODEX_PROVIDER", "deepseek"))
    parser.add_argument("--max-iter", type=int, default=100)
    parser.add_argument("--all", action="store_true", help="Start bridge + console")

    args = parser.parse_args()

    threads = []

    if args.bridge or args.all:
        t = threading.Thread(target=start_bridge, args=(args.port,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.5)

    if args.console or args.all:
        t = threading.Thread(target=start_console, args=(args.console_port,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.5)

    if args.task:
        start_loop(args.task, args.model, args.provider, args.max_iter)
    elif threads:
        print("[launcher] Services running. Press Ctrl+C to stop.")
        for t in threads:
            t.join()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()