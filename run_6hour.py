"""
Codex-Local 6灏忔椂鍏ㄨ嚜鍔ㄨ繍琛屽櫒
棰勭畻: ~3.8浜?tokens, 鐩爣: 娣卞害 self-improvement + 鍏ㄩ潰娴嬭瘯
"""
import sys, os, asyncio, time
from pathlib import Path
# CRITICAL: Unset ALL proxy env vars BEFORE importing runtime (which starts a session)
for _k in ['HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy', 'ALL_PROXY', 'all_proxy', 'PYTHONHTTPSVERIFY']:
    os.environ.pop(_k, None)
os.environ['DEEPSEEK_API_KEY'] = 'sk-REDACTED'

from runtime.loop import CodexLoop, LoopConfig

# 娣卞害 self-improvement 浠诲姟锛堟瘡浠诲姟娑堣€楀ぇ锛屼絾浠峰€奸珮锛?TASKS = [
    # === Phase 1: Self-Improvement (澶oken娑堣€? ===
    "Read D:/codex-local/runtime/loop.py and identify the 3 most impactful improvements to make it more reliable. Implement at least 2 of them and verify they compile.",
    "Analyze D:/codex-local/runtime/session.py for potential SQLite bottlenecks or data loss risks. Fix 1 critical issue and write a test for it.",
    "Read D:/codex-local/tools/executor.py. Find any tool method that could crash on edge cases (missing params, wrong types, large files). Fix 3 such cases.",
    "Review D:/codex-local/runtime/sandbox.py. Add one safety feature (max file size, max output, memory limit). Implement and test it.",
    "Read the DecisionEngine in D:/codex-local/runtime/loop.py. Improve the error handling when LLM returns ambiguous output. Add graceful fallback behavior.",
    "Analyze the message truncation in _build_messages(). Improve it to better preserve recent conversation context. Test with a 20-turn conversation.",
    "Read D:/codex-local/tools/debugger.py. Find and fix 1 bug or edge case in the debugging logic.",
    "Read D:/codex-local/tools/refactorer.py. Check if rename/refactor operations could lose code. Add a backup mechanism.",
    "Review D:/codex-local/runtime/brain.py. Does it handle API errors gracefully? Add retry logic and error recovery.",

    # === Phase 2: Comprehensive Tool Testing (澶氬伐鍏峰帇娴? ===
    "Create D:/codex-local/auto_tool_test.py that tests Read/Write/Edit on files of various sizes (1KB, 10KB, 100KB). Test and report results.",
    "Run D:/codex-local/auto_tool_test.py and capture the output. Fix any failures.",
    "Create D:/codex-local/auto_git_test.py that initializes a temp Git repo, makes 3 commits, checks log, and reports history.",
    "Run D:/codex-local/auto_git_test.py and report results.",
    "Create D:/codex-local/auto_glob_test.py that uses Glob to list all .py files in D:/codex-local/, counts them, and reports top 10 largest.",
    "Run D:/codex-local/auto_glob_test.py and report results.",
    "Create D:/codex-local/auto_grep_test.py that uses Grep to find all 'def ' occurrences in D:/codex-local/runtime/, count by file, report top files by function count.",
    "Run D:/codex-local/auto_grep_test.py and report results.",

    # === Phase 3: Code Generation & Execution ===
    "Create D:/codex-local/auto_bubble_sort.py implementing bubble sort. Run it with input [64, 34, 25, 12, 22, 11, 90] and report sorted output.",
    "Create D:/codex-local/auto_binary_search.py implementing binary search. Run it to find number 25 in [2, 5, 8, 12, 16, 23, 38, 56, 72, 91] and report index.",
    "Create D:/codex-local/auto_matrix_mult.py that multiplies two 3x3 matrices and prints result. Run it.",
    "Create D:/codex-local/auto_json_parser.py that parses a complex JSON object, extracts nested values, and prints them. Test with a JSON file you create.",
    "Create D:/codex-local/auto_regex_tool.py that uses regex to extract emails, URLs, and phone numbers from sample text. Run and report.",
    "Create D:/codex-local/auto_file_stats.py that walks D:/codex-local/runtime/ and reports: total files, total lines, total chars, average file size.",
    "Run D:/codex-local/auto_file_stats.py and report output.",

    # === Phase 4: Project Self-Analysis ===
    "Read D:/codex-local/runtime/loop.py. Count how many times 'tool_calls' appears. Also find all places where errors are caught and report if any error types are silently ignored.",
    "Analyze D:/codex-local/ for circular imports. Read each __init__.py and check if any module imports another that imports back. Report findings.",
    "Count total lines of code in D:/codex-local/ by file type (.py, .json, .md). Report in a formatted table.",
    "Find the 3 largest .py files in D:/codex-local/ by line count. For each, identify the top 3 longest functions.",
    "Read D:/codex-local/tools/executor.py. Map all 54 tool names to their method implementations. Report any tools that are defined but not implemented or vice versa.",
    "Search D:/codex-local/ for any TODO, FIXME, HACK, or XXX comments. List them with file:line and categorize by type.",
    "Check D:/codex-local/runtime/loop.py for any hardcoded values (magic numbers/strings) that should be constants. List them.",

    # === Phase 5: Deep Self-Improvement (杩唬鏀硅繘) ===
    "Read D:/codex-local/AUTO_IMPROVEMENTS.md. Based on its content, identify what's MISSING from the project and write a plan to add those missing pieces.",
    "Based on your analysis of the codebase, create D:/codex-local/IMPROVEMENT_PLAN.md listing 10 specific improvements to make Codex-Local more production-ready.",
    "Implement 1 improvement from IMPROVEMENT_PLAN.md. Create the new file or modify existing code. Verify it compiles.",
    "Run pytest on D:/codex-local/tests/ and confirm all tests still pass after your changes.",
    "Create D:/codex-local/tests/test_improvement.py with 3 tests for the improvement you just made. Run them.",
    "Analyze why some tasks in the previous autonomous run hit 'unknown' tool_call_id errors. Read loop.py and propose a fix.",
    "Implement the fix for 'unknown' tool_call_id issue you identified. Test it with Write + Read in one task.",
    "Stress test: Run 5 consecutive tasks that each involve Read + Write + Bash. Report success/failure for each.",

    # === Phase 6: Documentation & Final Report ===
    "Create D:/codex-local/ARCHITECTURE.md documenting the complete Codex-Local architecture with current code references.",
    "Update D:/codex-local/README.md with: (1) Current status, (2) How to run autonomous mode, (3) All 54 available tools.",
    "Create D:/codex-local/TOKEN_USAGE.md documenting token consumption patterns observed during this 6-hour run.",
    "Create D:/codex-local/FINAL_6H_REPORT.md as a comprehensive report of everything accomplished: what worked, what failed, token usage, files created, improvements made.",
]

REPORT_FILE = Path("D:/codex-local/SIX_HOUR_REPORT.md")


def append(text):
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if REPORT_FILE.exists():
        try:
            existing = REPORT_FILE.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            existing = ""
    REPORT_FILE.write_text(existing + "\n" + text, encoding="utf-8", errors="ignore")


async def run_task(i, text):
    print(f"[{i}/{len(TASKS)}] Starting: {text[:60]}...")
    start = time.time()
    config = LoopConfig(
        model="deepseek-chat", provider="deepseek",
        max_iterations=25,
        trust_code_execution=True, trust_file_writes=True,
        trust_shell_commands=False, temperature=0.3,
    )
    loop = CodexLoop(config)
    try:
        result = await loop.run_task(text)
        elapsed = time.time() - start
        append(f"\n## [{i}/{len(TASKS)}] {time.strftime('%H:%M:%S')}")
        append(f"**Time**: {elapsed:.1f}s | **Tokens**: {loop.total_tokens_used} | **Status**: {loop.status}")
        append(f"**Task**: {text[:120]}")
        append(f"**Result**: {result[:500] if result else 'None'}")
        if loop.error:
            append(f"**Error**: {loop.error}")
        print(f"  OK {elapsed:.0f}s {loop.total_tokens_used}t")
        return loop.total_tokens_used
    except Exception as e:
        elapsed = time.time() - start
        append(f"\n## [{i}/{len(TASKS)}] CRASHED")
        append(f"**Task**: {text[:120]}")
        append(f"**Error**: {type(e).__name__}: {e}")
        print(f"  CRASH {type(e).__name__}: {e}")
        return 0


async def main():
    total_tokens = 0
    append(f"# 6灏忔椂鍏ㄨ嚜鍔ㄨ繍琛屾姤鍛奬n## 寮€濮? {time.strftime('%Y-%m-%d %H:%M:%S')}")
    append(f"鎬讳换鍔℃暟: {len(TASKS)}")
    for i, task in enumerate(TASKS, 1):
        t = await run_task(i, task)
        total_tokens += t
    append(f"\n# 杩愯瀹屾垚")
    append(f"鎬绘秷鑰? {total_tokens} tokens (~{total_tokens/1_000_000:.1f}M)")
    print(f"\n=== DONE: {total_tokens} tokens ({total_tokens/1_000_000:.1f}M) across {len(TASKS)} tasks ===")


if __name__ == "__main__":
    asyncio.run(main())
