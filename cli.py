"""
Codex-Local CLI
Usage:
    python cli.py run "task description"
    python cli.py bridge
    python cli.py console
    python cli.py session <session_id>
    python cli.py status
    python cli.py loop "task" --model deepseek-chat --max-iter 100
    python cli.py parallel "task1" "task2" --max-workers 4
    python cli.py enhanced "task" --reasoning-rounds 3
    python cli.py plan example                          # Create example plan
    python cli.py plan run data/plans/example-plan.json # Execute a plan
    python cli.py plan loop data/plans/example-plan.json --max-cycles 5  # Auto-loop
    python cli.py plan status                           # Show plan status
"""

import os
import sys
import asyncio
import argparse
import json
import time
from pathlib import Path

# Ensure local packages are importable
sys.path.insert(0, str(Path(__file__).parent))

from runtime.loop import CodexLoop, LoopConfig, run_automated, run_enhanced, EnhancedCodexLoop
from runtime.parallel_loop import ParallelCodexLoop, ParallelConfig, EnhancedParallelLoop, run_parallel
from runtime.session import get_manager
from runtime.sandbox import get_sandbox
from bridge import run_server as run_bridge
from ui.console import run_console


def cmd_bridge(args):
    port = args.port or int(os.environ.get("CODEX_BRIDGE_PORT", "8787"))
    print(f"[codex-local] Starting API Bridge on port {port}...")
    run_bridge(port=port)


def cmd_console(args):
    port = args.port or 5000
    print(f"[codex-local] Starting Web Console on port {port}...")
    run_console(port=port)


def cmd_status(args):
    mgr = get_manager()
    stats = mgr.get_stats()
    print(json.dumps(stats, indent=2))


def cmd_sessions(args):
    mgr = get_manager()
    sessions = mgr.list_sessions(limit=args.limit or 50)
    for s in sessions:
        print(f"[{s.id}] {s.model} | {s.status} | cost=${s.total_cost:.4f} | {s.updated_at}")


def cmd_session(args):
    mgr = get_manager()
    s = mgr.get_session(args.session_id)
    if not s:
        print(f"Session {args.session_id} not found")
        return
    print(json.dumps(s.to_dict(), indent=2, default=str))


def cmd_loop(args):
    """Run an automated task."""
    task = args.task
    if not task:
        print("Error: --task required")
        return

    config = LoopConfig(
        model=args.model or os.environ.get("CODEX_MODEL", "deepseek-chat"),
        provider=args.provider or os.environ.get("CODEX_PROVIDER", "deepseek"),
        max_iterations=args.max_iter or 100,
        trust_code_execution=not args.no_trust_code,
        trust_file_writes=not args.no_trust_write,
        trust_shell_commands=args.trust_shell,
        max_output_tokens=args.max_tokens or 4096,
        temperature=args.temperature or 0.7,
        # Smart routing settings
        enable_smart_routing=args.smart_routing or False,
        monthly_budget=args.budget or 50.0,
        prefer_local=args.prefer_local or False,
        quality_threshold=args.quality_threshold or 0.0,
    )

    loop = CodexLoop(config)

    # Add routing listener
    def on_routing(event, data):
        if event == "routing":
            print(f"[codex-local] Smart routing: complexity={data['complexity']}, model={data['model']}, reason={data['reason']}")

    loop.add_listener(on_routing)

    async def run():
        print(f"[codex-local] Starting loop | model={config.model} | provider={config.provider}")
        if config.enable_smart_routing:
            print(f"[codex-local] Smart routing enabled | budget=${config.monthly_budget}/month | prefer_local={config.prefer_local}")
        print(f"[codex-local] Task: {task[:100]}...")
        start = time.time()
        result = await loop.run_task(task)
        elapsed = time.time() - start
        print(f"\n[codex-local] Done in {elapsed:.1f}s | iterations={loop.iteration_count}")
        print(f"[codex-local] Tokens used: {loop.total_tokens_used}")
        print(f"\nFinal result:\n{result}")

    asyncio.run(run())


def cmd_sandbox_test(args):
    """Test sandbox execution."""
    code = args.code or 'print("Hello from sandbox!")'
    language = args.language or "python"
    sb = get_sandbox()
    result = sb.execute(code, language)
    print(f"Exit: {result.exit_code}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")
    print(f"Duration: {result.duration_ms}ms")


def cmd_recover(args):
    """Recover from checkpoint."""
    mgr = get_manager()
    session = mgr.recover_from_checkpoint()
    if session:
        print(f"[codex-local] Recovered session: {session.id}")
        print(json.dumps(session.to_dict(), indent=2, default=str))
    else:
        print("[codex-local] No checkpoint found")


def cmd_parallel(args):
    """Run multiple tasks in parallel."""
    tasks = args.tasks
    if not tasks:
        print("Error: at least one task required")
        return

    config = ParallelConfig(
        max_workers=args.max_workers or 4,
        timeout_per_task=args.timeout or 600.0,
        default_loop_config=LoopConfig(
            model=args.model or os.environ.get("CODEX_MODEL", "deepseek-chat"),
            provider=args.provider or os.environ.get("CODEX_PROVIDER", "deepseek"),
        ),
    )

    if args.enhanced:
        engine = EnhancedParallelLoop(config, reasoning_rounds=args.reasoning_rounds or 3)
    else:
        engine = ParallelCodexLoop(config)

    # Add progress listener
    def on_event(event, data):
        if event == "task_completed":
            print(f"✓ Task completed: {data.get('task_id')}")
        elif event == "task_error":
            print(f"✗ Task failed: {data.get('task_id')} - {data.get('error')}")
        elif event == "task_started":
            print(f"→ Task started: {data.get('task_id')}")
        elif event == "reasoning_round":
            print(f"  Reasoning round {data.get('round')}/{data.get('total')}...")

    engine.add_listener(on_event)

    async def run():
        print(f"[codex-local] Starting parallel execution with {config.max_workers} workers...")
        print(f"[codex-local] Tasks: {len(tasks)}")
        print("-" * 50)

        await engine.submit_tasks(tasks)
        await engine.run(wait_for_completion=True)

        # Print results
        print("\n" + "=" * 50)
        print("RESULTS")
        print("=" * 50)

        stats = engine.get_stats()
        print(f"Total submitted: {stats['total_submitted']}")
        print(f"Total completed: {stats['total_completed']}")
        print(f"Total failed: {stats['total_failed']}")
        print(f"Total tokens used: {stats['total_tokens_used']}")
        print(f"Duration: {stats['duration']:.1f}s")

        print("\nTask Details:")
        for task in engine.get_tasks():
            status_icon = "✓" if task.status.value == "completed" else "✗"
            print(f"  {status_icon} [{task.id}] {task.task_description[:50]}...")
            print(f"    Status: {task.status.value}")
            print(f"    Duration: {task.duration:.1f}s")
            if task.error:
                print(f"    Error: {task.error}")

    asyncio.run(run())


def cmd_enhanced(args):
    """Run a task with multi-round reasoning."""
    task = args.task
    if not task:
        print("Error: --task required")
        return

    config = LoopConfig(
        model=args.model or os.environ.get("CODEX_MODEL", "deepseek-chat"),
        provider=args.provider or os.environ.get("CODEX_PROVIDER", "deepseek"),
        max_iterations=args.max_iter or 100,
        enable_multi_round_reasoning=True,
        reasoning_rounds=args.reasoning_rounds or 3,
        chain_of_thought=True,
    )

    loop = EnhancedCodexLoop(config)

    # Add listener for reasoning progress
    def on_event(event, data):
        if event == "reasoning_start":
            print(f"🧠 Starting multi-round reasoning ({data.get('rounds')} rounds)...")
        elif event == "reasoning_round":
            print(f"  Round {data.get('round')}/{data.get('total')}...")
        elif event == "reasoning_complete":
            print(f"✓ Reasoning complete ({data.get('thoughts')} thoughts)")
        elif event == "iteration":
            if data.get("action") == "calling_llm":
                print(f"  Iteration {data.get('iteration')}: Calling LLM...")
            elif data.get("action") == "executing_tool":
                print(f"  Iteration {data.get('iteration')}: Executing {data.get('tool')}...")

    loop.add_listener(on_event)

    async def run():
        print(f"[codex-local] Starting enhanced loop with {config.reasoning_rounds} reasoning rounds...")
        print(f"[codex-local] Task: {task[:100]}...")
        start = time.time()
        result = await loop.run_task(task)
        elapsed = time.time() - start
        print(f"\n[codex-local] Done in {elapsed:.1f}s | iterations={loop.iteration_count}")
        print(f"[codex-local] Tokens used: {loop.total_tokens_used}")
        print(f"\nReasoning History:")
        for i, thought in enumerate(loop.get_reasoning_history(), 1):
            print(f"  Round {i}: {thought['result'][:100]}...")
        print(f"\nFinal result:\n{result}")

    asyncio.run(run())


def cmd_smart_route(args):
    """Test smart model routing."""
    task = args.task
    if not task:
        print("Error: --task required")
        return

    from runtime.smart_router import SmartRouter

    router = SmartRouter(
        monthly_budget=args.budget or 50.0,
        prefer_local=args.prefer_local or False,
        quality_threshold=args.quality_threshold or 0.0,
    )

    print("=" * 60)
    print("SMART ROUTER TEST")
    print("=" * 60)
    print(f"Task: {task}")
    print(f"Budget: ${args.budget}/month")
    print(f"Prefer Local: {args.prefer_local}")
    print(f"Quality Threshold: {args.quality_threshold}")
    print("-" * 60)

    result = router.route(task)

    print(f"\nRouting Result:")
    print(f"  Complexity: {result['complexity'].value}")
    print(f"  Confidence: {result['confidence']:.2%}")
    print(f"  Model: {result['model_key']}")
    print(f"  Provider: {result['model_config'].provider}")
    print(f"  Tier: {result['model_config'].tier.value}")
    print(f"  Reason: {result['reason']}")
    print(f"  Estimated Cost: ${result['estimated_cost']:.4f}")
    print(f"  Quality Score: {result['model_config'].quality_score}")
    print(f"  Avg Latency: {result['model_config'].avg_latency_ms}ms")
    print(f"  Offline Capable: {result['model_config'].offline_capable}")

    print(f"\nBudget Status:")
    budget = result['budget_status']
    print(f"  Monthly Budget: ${budget['monthly_budget']:.2f}")
    print(f"  Spent: ${budget['spent_this_month']:.2f}")
    print(f"  Remaining: ${budget['remaining']:.2f}")
    print(f"  Used: {budget['percent_used']:.1f}%")

    print(f"\nAnalysis Details:")
    analysis = result['analysis']
    print(f"  Task Length: {analysis['task_length']} chars")
    print(f"  Code Blocks: {analysis['code_blocks']}")
    print(f"  Scores: {analysis['scores']}")

    if analysis['keywords_found']:
        print(f"  Keywords Found:")
        for category, keywords in analysis['keywords_found'].items():
            if keywords:
                print(f"    {category}: {', '.join(keywords)}")


def main():
    parser = argparse.ArgumentParser(description="Codex-Local: Autonomous AI coding assistant")
    sub = parser.add_subparsers(dest="cmd")

    # bridge
    p = sub.add_parser("bridge", help="Run the API bridge server")
    p.add_argument("--port", type=int, default=8787)
    p.set_defaults(func=cmd_bridge)

    # console
    p = sub.add_parser("console", help="Run the web console")
    p.add_argument("--port", type=int, default=5000)
    p.set_defaults(func=cmd_console)

    # status
    p = sub.add_parser("status", help="Show global stats")
    p.set_defaults(func=cmd_status)

    # sessions
    p = sub.add_parser("sessions", help="List sessions")
    p.add_argument("--limit", type=int)
    p.set_defaults(func=cmd_sessions)

    # session
    p = sub.add_parser("session", help="Show session details")
    p.add_argument("session_id")
    p.set_defaults(func=cmd_session)

    # loop
    p = sub.add_parser("loop", help="Run an automated task")
    p.add_argument("--task", "-t", required=True)
    p.add_argument("--model", "-m")
    p.add_argument("--provider")
    p.add_argument("--max-iter", type=int, default=100)
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--temperature", type=float)
    p.add_argument("--trust-shell", action="store_true")
    p.add_argument("--no-trust-code", action="store_true")
    p.add_argument("--no-trust-write", action="store_true")
    # Smart routing options
    p.add_argument("--smart-routing", "-sr", action="store_true", help="Enable intelligent model selection")
    p.add_argument("--budget", type=float, default=50.0, help="Monthly budget in dollars (default: $50)")
    p.add_argument("--prefer-local", action="store_true", help="Prefer local models (Ollama)")
    p.add_argument("--quality-threshold", type=float, default=0.0, help="Minimum model quality score (0-1)")
    p.set_defaults(func=cmd_loop)

    # sandbox-test
    p = sub.add_parser("sandbox-test", help="Test sandbox execution")
    p.add_argument("--code", "-c")
    p.add_argument("--language", "-l", default="python")
    p.set_defaults(func=cmd_sandbox_test)

    # recover
    p = sub.add_parser("recover", help="Recover from checkpoint")
    p.set_defaults(func=cmd_recover)

    # parallel
    p = sub.add_parser("parallel", help="Run multiple tasks in parallel")
    p.add_argument("tasks", nargs="+", help="Tasks to execute")
    p.add_argument("--max-workers", type=int, default=4, help="Max concurrent workers")
    p.add_argument("--timeout", type=float, default=600.0, help="Timeout per task in seconds")
    p.add_argument("--model", "-m")
    p.add_argument("--provider")
    p.add_argument("--enhanced", action="store_true", help="Use enhanced loop with reasoning")
    p.add_argument("--reasoning-rounds", type=int, default=3, help="Number of reasoning rounds")
    p.set_defaults(func=cmd_parallel)

    # enhanced
    p = sub.add_parser("enhanced", help="Run a task with multi-round reasoning")
    p.add_argument("--task", "-t", required=True)
    p.add_argument("--model", "-m")
    p.add_argument("--provider")
    p.add_argument("--max-iter", type=int, default=100)
    p.add_argument("--reasoning-rounds", type=int, default=3, help="Number of reasoning rounds")
    p.set_defaults(func=cmd_enhanced)

    # smart-route
    p = sub.add_parser("smart-route", help="Test smart model routing")
    p.add_argument("--task", "-t", required=True, help="Task to route")
    p.add_argument("--budget", type=float, default=50.0, help="Monthly budget in dollars")
    p.add_argument("--prefer-local", action="store_true", help="Prefer local models")
    p.add_argument("--quality-threshold", type=float, default=0.0, help="Minimum quality score")
    p.set_defaults(func=cmd_smart_route)

    # plan
    def cmd_plan(args):
        from runtime.plan_runner import PlanRunner, create_example_plan
        runner = PlanRunner()
        if args.plan_action == "run":
            plan = asyncio.run(runner.run_plan(args.plan_path, args.resume, args.model or "deepseek-chat"))
            print(f"\nPlan {plan.status}: {plan.completed_tasks}/{plan.total_tasks} tasks completed")
        elif args.plan_action == "loop":
            plans = asyncio.run(runner.run_loop(args.plan_path, max_cycles=args.max_cycles, model=args.model or "deepseek-chat"))
            print(f"\nAuto-loop completed: {len(plans)} cycles")
        elif args.plan_action == "status":
            runner.show_status()
        elif args.plan_action == "example":
            create_example_plan()

    p = sub.add_parser("plan", help="Run a plan (multi-task execution)")
    p.add_argument("plan_action", choices=["run", "loop", "status", "example"], help="Plan action")
    p.add_argument("plan_path", nargs="?", help="Path to plan JSON file")
    p.add_argument("--resume", action="store_true", help="Resume from saved progress")
    p.add_argument("--model", "-m", help="LLM model to use")
    p.add_argument("--max-cycles", type=int, default=5, help="Max auto-loop cycles")
    p.set_defaults(func=cmd_plan)

    # mcp
    def cmd_mcp(args):
        from mcp import create_server
        server = create_server()

        if args.mcp_action == "list":
            tools = server.list_tools()
            print(f"[codex-local] MCP Server: {server.get_tool_count()} tools, {server.get_module_count()} modules\n")
            for t in tools:
                params = t.get("parameters", {}).get("properties", {})
                param_names = ", ".join(params.keys()) if params else "none"
                print(f"  {t['name']:30s} | {t['description'][:50]}")
            print(f"\nTotal: {len(tools)} tools")

        elif args.mcp_action == "call":
            tool_name = args.tool_name
            tool_args = {}
            if args.tool_args:
                # Parse key=value pairs or JSON
                raw = " ".join(args.tool_args)
                if raw.startswith("{"):
                    tool_args = json.loads(raw)
                else:
                    for kv in args.tool_args:
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            # Try to parse as JSON value (int, bool, etc.)
                            try:
                                v = json.loads(v)
                            except (json.JSONDecodeError, ValueError):
                                pass
                            tool_args[k] = v
            result = server.call_tool(tool_name, tool_args)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

        elif args.mcp_action == "serve":
            mode = args.mode or "stdio"
            if mode == "http":
                from mcp import HTTPServer
                host = args.host or "127.0.0.1"
                port = args.port or 8765
                print(f"[codex-local] Starting MCP HTTP server on {host}:{port}...")
                http_server = HTTPServer(server, host=host, port=port)
                asyncio.run(http_server.run())
            else:
                print(f"[codex-local] Starting MCP STDIO server | {server.get_tool_count()} tools", file=sys.stderr)
                from mcp import spawn_stdio_server
                spawn_stdio_server(server)

    p = sub.add_parser("mcp", help="MCP server operations")
    mcp_sub = p.add_subparsers(dest="mcp_action")

    p_list = mcp_sub.add_parser("list", help="List all registered MCP tools")
    p_list.set_defaults(func=cmd_mcp)

    p_call = mcp_sub.add_parser("call", help="Call an MCP tool")
    p_call.add_argument("tool_name", help="Tool name to call")
    p_call.add_argument("tool_args", nargs="*", help="Arguments as key=value or JSON")
    p_call.set_defaults(func=cmd_mcp)

    p_serve = mcp_sub.add_parser("serve", help="Start MCP server")
    p_serve.add_argument("--mode", choices=["stdio", "http"], default="stdio", help="Server mode")
    p_serve.add_argument("--host", default="127.0.0.1", help="HTTP host")
    p_serve.add_argument("--port", type=int, default=8765, help="HTTP port")
    p_serve.set_defaults(func=cmd_mcp)

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()