"""
Codex-Local Git Workflow
Automated git operations: commit, branch, diff, rollback.
Every function returns {success, output, error}.
"""

import subprocess
from pathlib import Path
from typing import Dict, Optional


def _run_git(args: list, cwd: Optional[str] = None) -> Dict:
    """Run a git command and return structured result."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return {"success": True, "output": result.stdout.strip(), "error": None}
        else:
            return {"success": False, "output": result.stdout.strip(), "error": result.stderr.strip()}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "git not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "git command timed out"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def auto_commit(message: str, cwd: Optional[str] = None) -> Dict:
    """Auto git add + commit. Returns {success, output, error}."""
    add_result = _run_git(["add", "-A"], cwd=cwd)
    if not add_result["success"]:
        return {"success": False, "output": "", "error": f"git add failed: {add_result['error']}"}

    commit_result = _run_git(["commit", "-m", message], cwd=cwd)
    return {
        "success": commit_result["success"],
        "output": commit_result["output"],
        "error": commit_result["error"],
    }


def auto_branch(name: str, cwd: Optional[str] = None) -> Dict:
    """Create and switch to a new branch. Returns {success, output, error}."""
    return _run_git(["checkout", "-b", name], cwd=cwd)


def diff_summary(cwd: Optional[str] = None) -> Dict:
    """Return list of changed files with line additions/deletions.
    Returns {success, output: {files: [...], total_additions, total_deletions}, error}."""
    result = _run_git(["diff", "--stat"], cwd=cwd)
    if not result["success"]:
        return {"success": False, "output": None, "error": result["error"]}

    # Also get numstat for structured data
    numstat = _run_git(["diff", "--numstat"], cwd=cwd)
    files = []
    total_add = 0
    total_del = 0

    if numstat["success"] and numstat["output"]:
        for line in numstat["output"].splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                add_str, del_str, filename = parts
                adds = int(add_str) if add_str != "-" else 0
                dels = int(del_str) if del_str != "-" else 0
                total_add += adds
                total_del += dels
                files.append({"file": filename, "additions": adds, "deletions": dels})

    return {
        "success": True,
        "output": {
            "files": files,
            "total_additions": total_add,
            "total_deletions": total_del,
            "stat_text": result["output"],
        },
        "error": None,
    }


def rollback(cwd: Optional[str] = None) -> Dict:
    """Rollback to the last commit (hard reset HEAD~1). Returns {success, output, error}."""
    return _run_git(["reset", "--hard", "HEAD~1"], cwd=cwd)


def current_branch(cwd: Optional[str] = None) -> Dict:
    """Get current branch name. Returns {success, output, error}."""
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)


def log(limit: int = 10, cwd: Optional[str] = None) -> Dict:
    """Get recent commit log. Returns {success, output, error}."""
    return _run_git(["log", f"--oneline", f"-{limit}"], cwd=cwd)
