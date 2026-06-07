"""
Test script for new Codex-Local features:
1. GitHub Integration
2. Parallel Loop
3. Multi-Round Reasoning
4. Auto PR Generation
"""

import os
import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def test_github_integration():
    """Test GitHub integration module"""
    print("=" * 60)
    print("TEST: GitHub Integration")
    print("=" * 60)

    try:
        from tools.github_integration import GitHubIntegration, get_github, GITHUB_TOOL_DEFINITIONS

        # Test initialization
        github = get_github()
        print("[OK] GitHub integration initialized")

        # Test tool definitions
        print(f"[OK] {len(GITHUB_TOOL_DEFINITIONS)} GitHub tools defined")
        for tool in GITHUB_TOOL_DEFINITIONS:
            print(f"  - {tool['function']['name']}")

        # Test connection (will fail without token, but should not crash)
        result = github.test_connection()
        if result.get("success"):
            print(f"[OK] Connected as: {result.get('user')}")
        else:
            print(f"[WARN] Connection test failed (expected without token): {result.get('error')}")

        return True

    except Exception as e:
        print(f"[FAIL] GitHub integration test failed: {e}")
        return False


def test_parallel_loop():
    """Test parallel loop module"""
    print("\n" + "=" * 60)
    print("TEST: Parallel Loop")
    print("=" * 60)

    try:
        from runtime.parallel_loop import (
            ParallelCodexLoop, ParallelConfig, ParallelTask,
            EnhancedParallelLoop, TaskStatus
        )

        # Test initialization
        config = ParallelConfig(max_workers=2)
        engine = ParallelCodexLoop(config)
        print("[OK] Parallel loop initialized")

        # Test task creation
        task = ParallelTask(
            id="test_1",
            task_description="Test task",
        )
        print(f"[OK] Task created: {task.id} - {task.status.value}")

        # Test stats
        stats = engine.get_stats()
        print(f"[OK] Stats retrieved: {stats['total_submitted']} tasks submitted")

        # Test progress
        progress = engine.get_progress()
        print(f"[OK] Progress: {progress['progress_percent']}%")

        return True

    except Exception as e:
        print(f"[FAIL] Parallel loop test failed: {e}")
        return False


def test_enhanced_loop():
    """Test enhanced loop with multi-round reasoning"""
    print("\n" + "=" * 60)
    print("TEST: Enhanced Loop (Multi-Round Reasoning)")
    print("=" * 60)

    try:
        from runtime.loop import (
            EnhancedCodexLoop, LoopConfig, CHAIN_OF_THOUGHT_PROMPT
        )

        # Test initialization
        config = LoopConfig(
            enable_multi_round_reasoning=True,
            reasoning_rounds=2,
            chain_of_thought=True,
        )
        loop = EnhancedCodexLoop(config)
        print("[OK] Enhanced loop initialized")
        print(f"  - Reasoning rounds: {config.reasoning_rounds}")
        print(f"  - Chain of thought: {config.chain_of_thought}")

        # Test reasoning history (empty at start)
        history = loop.get_reasoning_history()
        print(f"[OK] Reasoning history: {len(history)} entries")

        return True

    except Exception as e:
        print(f"[FAIL] Enhanced loop test failed: {e}")
        return False


def test_executor_github_tools():
    """Test GitHub tools in executor"""
    print("\n" + "=" * 60)
    print("TEST: Executor GitHub Tools")
    print("=" * 60)

    try:
        from tools.executor import ToolExecutor, TOOL_DEFINITIONS

        # Count GitHub tools
        github_tools = [t for t in TOOL_DEFINITIONS if t.get("name", "").startswith("GitHub")]
        print(f"[OK] {len(github_tools)} GitHub tools in TOOL_DEFINITIONS")

        # List GitHub tools
        for tool in github_tools:
            print(f"  - {tool['name']}")

        # Test executor has GitHub methods
        executor = ToolExecutor()
        github_methods = [m for m in dir(executor) if m.startswith("github")]
        print(f"[OK] {len(github_methods)} GitHub methods in executor")

        return True

    except Exception as e:
        print(f"[FAIL] Executor GitHub tools test failed: {e}")
        return False


def test_cli_imports():
    """Test CLI imports"""
    print("\n" + "=" * 60)
    print("TEST: CLI Imports")
    print("=" * 60)

    try:
        # Test importing new modules
        from runtime.loop import run_enhanced, EnhancedCodexLoop
        print("[OK] Imported run_enhanced and EnhancedCodexLoop")

        from runtime.parallel_loop import run_parallel, ParallelCodexLoop
        print("[OK] Imported run_parallel and ParallelCodexLoop")

        return True

    except Exception as e:
        print(f"[FAIL] CLI imports test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("CODEX-LOCAL NEW FEATURES TEST SUITE")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("GitHub Integration", test_github_integration()))
    results.append(("Parallel Loop", test_parallel_loop()))
    results.append(("Enhanced Loop", test_enhanced_loop()))
    results.append(("Executor GitHub Tools", test_executor_github_tools()))
    results.append(("CLI Imports", test_cli_imports()))

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[OK] PASS" if result else "[FAIL] FAIL"
        print(f"{status}: {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print("\n[WARN] Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
