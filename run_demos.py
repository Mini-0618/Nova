"""Run all Phase 6 Demos"""
import sys, json, os, shutil
sys.path.insert(0, r'D:\codex-local')

OUT = r'D:\codex-local\demo_outputs'

# ─── Debug Demo ────────────────────────────────────────────────────────────────
print("=== Debug Demo ===")
from tools.debugger import CodeDebugger
dbg = CodeDebugger()

# Write buggy file
buggy_path = os.path.join(OUT, 'buggy.py')
with open(buggy_path, 'w') as f:
    f.write("def divide(a, b):\n    return a / b\n\ndef main():\n    x = 10\n    y = 0\n    result = divide(x, y)\n    print(f'Result: {result}')\n\nmain()\n")

result = dbg.run_file(buggy_path)
report = {
    'success': result.success,
    'exception_type': result.exception_type,
    'exception_message': result.exception_message,
    'stack_trace': result.stack_trace,
    'frames': [{'file': f.filename, 'line': f.lineno, 'function': f.function} for f in result.frames] if result.frames else []
}
with open(os.path.join(OUT, 'debug_report.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2)
print(f"  Exception: {result.exception_type} - {result.exception_message}")

# ─── Git Demo ─────────────────────────────────────────────────────────────────
print("=== Git Demo ===")
demo_repo = os.path.join(OUT, 'test_repo')
if os.path.exists(demo_repo):
    shutil.rmtree(demo_repo)
os.makedirs(demo_repo)

from tools.git_integration import GitRepo
import git

# Init repo with GitPython directly (git.exe was found at C:\Program Files\Git\cmd\git.exe)
git_repo = git.Repo.init(demo_repo)
git_repo.config_writer().set_value("user", "email", "demo@demo.com").release()
git_repo.config_writer().set_value("user", "name", "Demo").release()

# Create file and commit
with open(os.path.join(demo_repo, 'readme.md'), 'w') as f:
    f.write('# Test\n')
git_repo.index.add(['readme.md'])
git_repo.index.commit('initial commit')

# Modify file
with open(os.path.join(demo_repo, 'readme.md'), 'w') as f:
    f.write('# Test\nModified\n')

repo = GitRepo(demo_repo)
status = repo.status()
commits = repo.log(max_count=5)
diffs = repo.diff('HEAD')

report = {
    'branch': status.branch,
    'clean': status.clean,
    'staged': status.staged,
    'modified': status.modified,
    'commits': [{'hash': c.hash, 'message': c.message} for c in commits],
    'diffs': [{'file': d.file, 'status': d.status} for d in diffs],
}
with open(os.path.join(OUT, 'git_report.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2)
print(f"  Branch: '{status.branch}' | Clean: {status.clean} | Modified: {status.modified}")

# ─── Refactor Demo ────────────────────────────────────────────────────────────
print("=== Refactor Demo ===")
ref_dir = os.path.join(OUT, 'refactor_demo')
if os.path.exists(ref_dir):
    shutil.rmtree(ref_dir)
os.makedirs(ref_dir)

with open(os.path.join(ref_dir, 'utils.py'), 'w') as f:
    f.write('def old_helper(x, y):\n    return x + y\n\nresult = old_helper(1, 2)\nprint(old_helper(3, 4))\n')
with open(os.path.join(ref_dir, 'main.py'), 'w') as f:
    f.write('from utils import old_helper\n\nx = old_helper(10, 20)\nprint(old_helper(x, 30))\n')

from tools.refactorer import MultiModuleRefactorer
ref = MultiModuleRefactorer(ref_dir)
plan = ref.rename_symbol('old_helper', 'new_helper')
results = ref.apply_plan(plan)

report = {
    'description': plan.description,
    'changes_planned': len(plan.changes),
    'applied': results['applied'],
    'failed': results['failed'],
}
with open(os.path.join(OUT, 'refactor_report.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2)
print(f"  Planned: {len(plan.changes)} | Applied: {results['applied']}")

# Verify refactor worked
with open(os.path.join(ref_dir, 'utils.py')) as f:
    content = f.read()
ref_ok = 'new_helper' in content and 'old_helper' not in content
print(f"  Refactor verify: {'PASS' if ref_ok else 'FAIL'}")

# ─── Browser Demo ─────────────────────────────────────────────────────────────
print("=== Browser Demo ===")
try:
    from tools.browser_automation import BrowserController
    b = BrowserController(headless=True)
    r = b.navigate("https://example.com")
    if r.success:
        ss_path = os.path.join(OUT, 'browser_screenshot.png')
        b.screenshot(ss_path)
        report = {'success': True, 'url': r.url, 'title': r.title, 'screenshot': ss_path}
        print(f"  OK: {r.url} | {r.title}")
    else:
        report = {'success': False, 'error': r.error}
        print(f"  BLOCKED: {r.error}")
    b.close()
except Exception as e:
    report = {'success': False, 'error': str(e)}
    print(f"  BLOCKED: {e}")

with open(os.path.join(OUT, 'browser_report.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2)

print("\n=== All Demos Complete ===")
print(f"Outputs in: {OUT}")