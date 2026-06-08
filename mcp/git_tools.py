"""
Git Tools Module
Provides git operations: status, log, diff, commit, branch, checkout, blame.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from .server import ToolModule


class GitTools(ToolModule):
    """Git operations as MCP tools."""

    def _run_git(self, args: List[str], cwd: str = ".") -> Dict[str, Any]:
        """Run a git command and return structured result."""
        try:
            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                timeout=30,
                cwd=cwd,
                text=True,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "exit_code": result.returncode,
            }
        except FileNotFoundError:
            return {"success": False, "error": "git not found in PATH", "exit_code": -1}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "git command timed out", "exit_code": -1}
        except Exception as e:
            return {"success": False, "error": str(e), "exit_code": -1}

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "git_status",
                "description": "Show git working tree status",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "description": "Path to git repository"},
                    },
                    "required": ["repo_path"],
                },
                "handler": self._git_status,
            },
            {
                "name": "git_log",
                "description": "Show git commit log",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "description": "Path to git repository"},
                        "count": {"type": "integer", "description": "Number of commits to show (default: 10)"},
                    },
                    "required": ["repo_path"],
                },
                "handler": self._git_log,
            },
            {
                "name": "git_diff",
                "description": "Show git diff",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "description": "Path to git repository"},
                        "staged": {"type": "boolean", "description": "Show staged changes (default: false)"},
                    },
                    "required": ["repo_path"],
                },
                "handler": self._git_diff,
            },
            {
                "name": "git_commit",
                "description": "Stage all changes and commit with a message",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "description": "Path to git repository"},
                        "message": {"type": "string", "description": "Commit message"},
                    },
                    "required": ["repo_path", "message"],
                },
                "handler": self._git_commit,
            },
            {
                "name": "git_branch",
                "description": "Create a new branch or list branches",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "description": "Path to git repository"},
                        "name": {"type": "string", "description": "Branch name to create (omit to list branches)"},
                    },
                    "required": ["repo_path"],
                },
                "handler": self._git_branch,
            },
            {
                "name": "git_checkout",
                "description": "Switch to a different branch",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "description": "Path to git repository"},
                        "branch": {"type": "string", "description": "Branch name to checkout"},
                    },
                    "required": ["repo_path", "branch"],
                },
                "handler": self._git_checkout,
            },
            {
                "name": "git_blame",
                "description": "Show line-by-line file annotations",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "description": "Path to git repository"},
                        "file": {"type": "string", "description": "File to annotate"},
                    },
                    "required": ["repo_path", "file"],
                },
                "handler": self._git_blame,
            },
        ]

    def _git_status(self, repo_path: str) -> Dict:
        return self._run_git(["status", "--porcelain"], cwd=repo_path)

    def _git_log(self, repo_path: str, count: int = 10) -> Dict:
        return self._run_git(
            ["log", f"--max-count={count}", "--oneline", "--decorate"],
            cwd=repo_path,
        )

    def _git_diff(self, repo_path: str, staged: bool = False) -> Dict:
        args = ["diff"]
        if staged:
            args.append("--staged")
        return self._run_git(args, cwd=repo_path)

    def _git_commit(self, repo_path: str, message: str) -> Dict:
        # Stage all
        stage = self._run_git(["add", "-A"], cwd=repo_path)
        if not stage["success"]:
            return stage
        # Commit
        return self._run_git(["commit", "-m", message], cwd=repo_path)

    def _git_branch(self, repo_path: str, name: str = None) -> Dict:
        if name:
            return self._run_git(["branch", name], cwd=repo_path)
        return self._run_git(["branch", "-a"], cwd=repo_path)

    def _git_checkout(self, repo_path: str, branch: str) -> Dict:
        return self._run_git(["checkout", branch], cwd=repo_path)

    def _git_blame(self, repo_path: str, file: str) -> Dict:
        return self._run_git(["blame", file], cwd=repo_path)
