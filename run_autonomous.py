"""
Codex-Local Autonomous Runner
Executes multiple tasks in sequence, fully automatically, zero human interaction.
"""
import sys, os, json, asyncio, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ['DEEPSEEK_API_KEY'] = 'sk-REDACTED'

from runtime.loop import CodexLoop, LoopConfig


TASKS = [
    # Phase 1: Core competency tests
    "Write a Python quicksort implementation to D:/codex-local/auto_sort.py and run it with input [3,1,4,1,5,9]. Report the sorted output.",
    "Write a factorial function to D:/codex-local/auto_fact.py. Calculate and print factorial(20). Report the result.",
    "Create D:/codex-local/auto_prime.py that finds all primes under 100. Print count and list.",
    "Write a Python file D:/codex-local/auto_config.json with keys: project name, version, author. Then read it back and print content.",

    # Phase 2: File operations
    "List all .py files in D:/codex-local/runtime/ using Glob. Print the count and first 5 paths.",
    "Search D:/codex-local/ for all occurrences of 'CodexLoop' using Grep. Report file:line for each match.",
    "Count total lines of Python code in D:/codex-local/runtime/ (not including __pycache__). Report total.",

    # Phase 3: Code execution
    "Write a Python script D:/codex-local/auto_url_fetch.py that fetches http://example.com/ and prints status code and first 200 chars of content.",
    "Create D:/codex-local/auto_csv.py that creates a CSV file D:/codex-local/auto_data.csv with columns: name,age,city and 3 rows of sample data.",
    "Write a Python script D:/codex-local/auto_http_server.py that starts a simple HTTP server on port 8765, serves D:/codex-local/, then stops it after 2 seconds.",

    # Phase 4: Project improvements
    "Find the longest Python file in D:/codex-local/ by line count. Report filename and line count.",
    "Find all TODO or FIXME comments in D:/codex-local/tools/ using Grep. List them with file:line.",
    "Check D:/codex-local/runtime/ for any .py files that import non-existent modules (basic check). Report any issues.",

    # Phase 5: Analysis tasks
    "Analyze D:/codex-local/tools/executor.py: how many distinct tool categories are there (file/Git/browser/etc)? Report each category with count.",
    "What is the total disk size of D:/codex-local/sandbox/ directory? Report in KB.",
    "Check if D:/codex-local/data/ exists and what files are in it. Report listing.",

    # Phase 6: Self-improvement
    "Read D:/codex-local/runtime/loop.py and identify the single most impactful improvement to make it more robust. Implement that improvement.",
    "Read D:/codex-local/tools/executor.py and identify one tool that has a potential bug or edge case. Fix it.",
    "Check D:/codex-local/ for any .py file with syntax warnings. List them and fix one.",
    "Review the Sandbox class in D:/codex-local/runtime/sandbox.py and add one missing safety feature (e.g. max file size, max memory).",

    # Phase 7: Testing
    "Run all tests in D:/codex-local/tests/ using pytest. Report pass/fail count and any failures.",
    "Create a new test file D:/codex-local/tests/test_auto_executor.py that tests the Write and Read tools. Test: write content, read back, verify match.",
    "Run the new test file you just created. Report results.",

    # Phase 8: Documentation
    "Create D:/codex-local/AUTO_IMPROVEMENTS.md documenting all the improvements made to this project today.",
    "Update D:/codex-local/README.md with a section showing how to run the autonomous loop with example commands.",

    # Phase 9: Final validation
    "Verify D:/codex-local/ can complete this task end-to-end: create D:/codex-local/auto_validation.py that calculates sha256 of 'codex-local', print the hash.",
    "Run D:/codex-local/auto_validation.py and confirm the sha256 hash is: 8f6e5f8a7c3d1e4b9a2f0d3c6e8a1b4d5f7c9e2a4b6d8e0f1a3c5d7e9f1b4d6a8c",
    "Do a final review: create D:/codex-local/AUTO_FINAL_REPORT.md listing what was accomplished, what works, what remains.",
]

REPORT_FILE = Path("D:/codex-local/AUTONOMOUS_REPORT.md")


def load_report():
    if REPORT_FILE.exists():
        return REPORT_FILE.read_text(encoding="utf-8")
    return ""


def append_report(text):
    existing = load_report()
    REPORT_FILE.write_text(existing + "\n" + text, encoding="utf-8")


async def run_task(task_index, task_text):
    print(f"\n[Task {task_index}/{len(TASKS)}] Starting: {task_text[:60]}...")
    start = time.time()

    config = LoopConfig(
        model="deepseek-chat",
        provider="deepseek",
        max_iterations=20,
        trust_code_execution=True,
        trust_file_writes=True,
        trust_shell_commands=False,
        temperature=0.3,
    )
    loop = CodexLoop(config)

    try:
        result = await loop.run_task(task_text)
        elapsed = time.time() - start
        status = loop.status
        iters = loop.iteration_count
        tokens = loop.total_tokens_used
        error = loop.error

        line = f"\n## Task {task_index}/{len(TASKS)}\n"
        line += f"**Status**: {status} | **Time**: {elapsed:.1f}s | **Iterations**: {iters} | **Tokens**: {tokens}\n"
        line += f"**Task**: {task_text[:100]}\n"
        line += f"**Result**: {result[:300] if result else 'None'}\n"
        if error:
            line += f"**Error**: {error}\n"
        append_report(line)

        print(f"  [OK] Done ({elapsed:.1f}s, {tokens} tokens): {status}")
        return True

    except Exception as e:
        elapsed = time.time() - start
        line = f"\n## Task {task_index}/{len(TASKS)} [CRASHED]\n"
        line += f"**Task**: {task_text[:100]}\n"
        line += f"**Error**: {type(e).__name__}: {e}\n"
        line += f"**Time**: {elapsed:.1f}s\n"
        append_report(line)
        print(f"  [FAIL] Crashed: {e}")
        return False


async def main():
    print("=" * 60)
    print("Codex-Local Autonomous Runner")
    print(f"Total tasks: {len(TASKS)}")
    print(f"Report file: {REPORT_FILE}")
    print("=" * 60)

    append_report(f"\n\n# Autonomous Run Started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    append_report(f"Total tasks: {len(TASKS)}\n")

    success = 0
    failed = 0

    for i, task in enumerate(TASKS, 1):
        ok = await run_task(i, task)
        if ok:
            success += 1
        else:
            failed += 1

    total_tokens = sum(t.total_tokens_used for t in [CodexLoop()])  # just for display
    append_report(f"\n\n# Run Complete\n")
    append_report(f"Success: {success}/{len(TASKS)}, Failed: {failed}\n")

    print(f"\n{'='*60}")
    print(f"RUN COMPLETE: {success} success, {failed} failed out of {len(TASKS)} tasks")
    print(f"Full log: {REPORT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())