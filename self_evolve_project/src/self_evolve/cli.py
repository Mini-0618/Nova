from __future__ import annotations

import argparse

from self_evolve.loop import SelfEvolutionLoop


def main() -> int:
    parser = argparse.ArgumentParser(description="Self Evolution Multi-file System")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p_cycle = sub.add_parser("cycle")
    p_cycle.add_argument("--config", default="configs/default.json")

    p_loop = sub.add_parser("loop")
    p_loop.add_argument("--config", default="configs/default.json")
    p_loop.add_argument("--cycles", type=int, default=3)

    args = parser.parse_args()

    if args.cmd == "init":
        print("project already initialized by generator")
        return 0

    if args.cmd == "cycle":
        loop = SelfEvolutionLoop(args.config)
        loop.run_once(1)
        return 0

    if args.cmd == "loop":
        loop = SelfEvolutionLoop(args.config)
        loop.run_loop(args.cycles)
        return 0

    return 2
