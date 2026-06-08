"""
Codex-Local Tool Executor
Implements all tools Codex can call: Read, Write, Edit, Bash, Glob, Grep, etc.
"""

import os
import re
import json
import asyncio
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import glob as glob_module

import os, sys as _sys
_root = Path(__file__).parent.parent
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from runtime.sandbox import execute_code, get_sandbox  # noqa: E402


# ─── Tool Definitions ────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "Read",
        "description": "Read the complete contents of a file from the filesystem.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read. Absolute or relative to workspace.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-indexed).",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "type": "function",
        "name": "Write",
        "description": "Create a new file or overwrite an existing file with the given content.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file.",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "type": "function",
        "name": "Edit",
        "description": "Make a targeted edit to one specific file. For scattered changes use Write.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit.",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text in the file to replace. Must match the source exactly.",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text.",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "type": "function",
        "name": "Bash",
        "description": "Execute a shell command and return its output.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30).",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for the command.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "type": "function",
        "name": "Glob",
        "description": "Return files matching a glob pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts').",
                },
                "cwd": {
                    "type": "string",
                    "description": "Root directory for the search.",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "type": "function",
        "name": "Grep",
        "description": "Search for a pattern in files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for.",
                },
                "glob": {
                    "type": "string",
                    "description": "Only search files matching this glob pattern.",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["files_with_matches", "content", "count"],
                    "description": "Output format (default: content).",
                },
            },
            "required": ["path", "pattern"],
        },
    },
    {
        "type": "function",
        "name": "GlobWalk",
        "description": "Recursively list all files under a directory matching patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "root": {
                    "type": "string",
                    "description": "Root directory to start from.",
                },
                "patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of glob patterns to match (e.g., ['**/*.py', '**/*.json']).",
                },
            },
            "required": ["root"],
        },
    },
    {
        "type": "function",
        "name": "TodoWrite",
        "description": "Write a todo list to a JSON file for tracking goals.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the todo JSON file.",
                },
                "todos": {
                    "type": "array",
                    "description": "List of todo items with 'content', 'status', 'activeForm'.",
                },
            },
            "required": ["file_path", "todos"],
        },
    },
    {
        "type": "function",
        "name": "sandbox_exec",
        "description": "Execute Python/JS/Shell code in an isolated sandbox and return stdout/stderr/exit code.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The code to execute.",
                },
                "language": {
                    "type": "string",
                    "description": "Language: python, javascript, shell (default: python).",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID for persistent state between runs.",
                },
            },
            "required": ["code"],
        },
    },
    {
        "type": "function",
        "name": "NotebookEdit",
        "description": "Edit a Jupyter notebook cell.",
        "parameters": {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the .ipynb file.",
                },
                "cell_id": {
                    "type": "string",
                    "description": "ID of the cell to edit.",
                },
                "new_source": {
                    "type": "string",
                    "description": "New cell content.",
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown"],
                },
                "edit_mode": {
                    "type": "string",
                    "enum": ["replace", "insert", "delete"],
                },
            },
            "required": ["notebook_path", "new_source"],
        },
    },
    {
        "type": "function",
        "name": "WebSearch",
        "description": "Search the web for information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "recency_days": {
                    "type": "integer",
                    "description": "Only return results from the last N days.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "WebFetch",
        "description": "Fetch a URL and extract information from it.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch.",
                },
                "prompt": {
                    "type": "string",
                    "description": "What to extract from the page.",
                },
            },
            "required": ["url", "prompt"],
        },
    },
    # ─── Project Analysis ───────────────────────────────────────────────
    {
        "type": "function",
        "name": "ProjectAnalyze",
        "description": "Analyze project structure: module dependencies, classes, functions, import graphs.",
        "parameters": {
            "type": "object",
            "properties": {
                "root": {
                    "type": "string",
                    "description": "Project root directory.",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to analyze (default 1000).",
                },
            },
            "required": ["root"],
        },
    },
    {
        "type": "function",
        "name": "ProjectFindSymbol",
        "description": "Find all definitions and usages of a symbol (function/class/variable) in the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Symbol name to search for.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "ProjectExplainSymbol",
        "description": "Explain what a symbol does, where it's defined, and where it's used.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Symbol name to explain.",
                },
            },
            "required": ["name"],
        },
    },
    # ─── Browser Automation ─────────────────────────────────────────────
    {
        "type": "function",
        "name": "BrowserNavigate",
        "description": "Navigate to a URL in the browser.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to navigate to.",
                },
                "wait_until": {
                    "type": "string",
                    "description": "Wait until: networkidle, load, domcontentloaded (default: networkidle).",
                },
            },
            "required": ["url"],
        },
    },
    {
        "type": "function",
        "name": "BrowserClick",
        "description": "Click an element by CSS selector.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the element to click.",
                },
            },
            "required": ["selector"],
        },
    },
    {
        "type": "function",
        "name": "BrowserType",
        "description": "Type text into an input field.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the input field.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type.",
                },
                "clear_first": {
                    "type": "boolean",
                    "description": "Clear the field before typing (default: true).",
                },
            },
            "required": ["selector", "text"],
        },
    },
    {
        "type": "function",
        "name": "BrowserScreenshot",
        "description": "Take a screenshot of the current page or an element.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to save the screenshot.",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Screenshot the full scrollable page.",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector to screenshot a specific element.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "BrowserEvaluate",
        "description": "Execute JavaScript in the page and return the result.",
        "parameters": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "JavaScript code to execute.",
                },
            },
            "required": ["script"],
        },
    },
    {
        "type": "function",
        "name": "BrowserText",
        "description": "Get text content of an element.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the element.",
                },
            },
            "required": ["selector"],
        },
    },
    # ─── Git Integration ────────────────────────────────────────────────
    {
        "type": "function",
        "name": "GitStatus",
        "description": "Get current Git status: branch, staged, modified, untracked files.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Path to the Git repository.",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "type": "function",
        "name": "GitLog",
        "description": "Get commit history.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Path to the Git repository.",
                },
                "max_count": {
                    "type": "integer",
                    "description": "Max number of commits (default: 50).",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "type": "function",
        "name": "GitDiff",
        "description": "Get diff between two refs or between ref and working tree.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Path to the Git repository.",
                },
                "ref1": {
                    "type": "string",
                    "description": "First ref (e.g., HEAD~1).",
                },
                "ref2": {
                    "type": "string",
                    "description": "Second ref (empty = diff against working tree).",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "type": "function",
        "name": "GitCommit",
        "description": "Stage files and create a commit.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Path to the Git repository.",
                },
                "message": {
                    "type": "string",
                    "description": "Commit message.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to stage (omit to stage all).",
                },
            },
            "required": ["repo", "message"],
        },
    },
    {
        "type": "function",
        "name": "GitBranch",
        "description": "List branches or create a new branch.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Path to the Git repository.",
                },
                "create": {
                    "type": "string",
                    "description": "Create a new branch with this name.",
                },
                "checkout": {
                    "type": "string",
                    "description": "Checkout this branch.",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "type": "function",
        "name": "GitBlame",
        "description": "Get blame info (who changed each line) for a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Path to the Git repository.",
                },
                "file": {
                    "type": "string",
                    "description": "File to blame.",
                },
            },
            "required": ["repo", "file"],
        },
    },
    # ─── GitHub Integration ─────────────────────────────────────────────
    {
        "type": "function",
        "name": "GitHubClone",
        "description": "Clone a GitHub repository to local path.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_url": {"type": "string", "description": "Repository URL"},
                "local_path": {"type": "string", "description": "Local path to clone to"},
                "depth": {"type": "integer", "description": "Clone depth (0 for full)", "default": 1},
            },
            "required": ["repo_url", "local_path"],
        },
    },
    {
        "type": "function",
        "name": "GitHubGetRepo",
        "description": "Get GitHub repository information.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "type": "function",
        "name": "GitHubListBranches",
        "description": "List branches in a GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "type": "function",
        "name": "GitHubCreateBranch",
        "description": "Create a new branch in GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "branch_name": {"type": "string", "description": "New branch name"},
                "from_branch": {"type": "string", "description": "Source branch", "default": "main"},
            },
            "required": ["owner", "repo", "branch_name"],
        },
    },
    {
        "type": "function",
        "name": "GitHubGetFile",
        "description": "Get file content from GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "path": {"type": "string", "description": "File path"},
                "ref": {"type": "string", "description": "Branch or commit SHA", "default": "main"},
            },
            "required": ["owner", "repo", "path"],
        },
    },
    {
        "type": "function",
        "name": "GitHubCreateFile",
        "description": "Create or update a file in GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "File content"},
                "message": {"type": "string", "description": "Commit message"},
                "branch": {"type": "string", "description": "Branch name", "default": "main"},
            },
            "required": ["owner", "repo", "path", "content", "message"],
        },
    },
    {
        "type": "function",
        "name": "GitHubListPRs",
        "description": "List pull requests in a GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "state": {"type": "string", "description": "PR state (open/closed/all)", "default": "open"},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "type": "function",
        "name": "GitHubCreatePR",
        "description": "Create a pull request.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "title": {"type": "string", "description": "PR title"},
                "body": {"type": "string", "description": "PR body"},
                "head": {"type": "string", "description": "Head branch"},
                "base": {"type": "string", "description": "Base branch", "default": "main"},
            },
            "required": ["owner", "repo", "title", "body", "head"],
        },
    },
    {
        "type": "function",
        "name": "GitHubAutoCreatePR",
        "description": "Automatically create a PR with smart defaults. Generates title from branch name and body from commits if not provided.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "feature_branch": {"type": "string", "description": "Feature branch name"},
                "base_branch": {"type": "string", "description": "Base branch", "default": "main"},
                "title": {"type": "string", "description": "PR title (auto-generated if empty)"},
                "body": {"type": "string", "description": "PR body (auto-generated if empty)"},
                "auto_merge": {"type": "boolean", "description": "Auto-merge after creation", "default": False},
            },
            "required": ["owner", "repo", "feature_branch"],
        },
    },
    {
        "type": "function",
        "name": "GitHubMergePR",
        "description": "Merge a pull request.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "pull_number": {"type": "integer", "description": "PR number"},
                "merge_method": {"type": "string", "description": "Merge method (merge/squash/rebase)", "default": "merge"},
            },
            "required": ["owner", "repo", "pull_number"],
        },
    },
    {
        "type": "function",
        "name": "GitHubListIssues",
        "description": "List issues in a GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "state": {"type": "string", "description": "Issue state (open/closed/all)", "default": "open"},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "type": "function",
        "name": "GitHubCreateIssue",
        "description": "Create an issue in a GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "title": {"type": "string", "description": "Issue title"},
                "body": {"type": "string", "description": "Issue body"},
                "labels": {"type": "array", "items": {"type": "string"}, "description": "Labels"},
            },
            "required": ["owner", "repo", "title", "body"],
        },
    },
    {
        "type": "function",
        "name": "GitHubSearchCode",
        "description": "Search code in GitHub repositories.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "owner": {"type": "string", "description": "Repository owner (optional)"},
                "repo": {"type": "string", "description": "Repository name (optional)"},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "GitHubRateLimit",
        "description": "Get current GitHub API rate limit status.",
        "parameters": {"type": "object", "properties": {}},
    },
    # ─── Code Debugger ──────────────────────────────────────────────────
    {
        "type": "function",
        "name": "DebugRun",
        "description": "Run Python code and get detailed error info with stack trace and local variables.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute.",
                },
                "globals": {
                    "type": "object",
                    "description": "Global variables to pass to the code.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30).",
                },
            },
            "required": ["code"],
        },
    },
    {
        "type": "function",
        "name": "DebugPytest",
        "description": "Run pytest on a test file and get detailed results.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to test file or directory.",
                },
                "test_name": {
                    "type": "string",
                    "description": "Specific test name (optional).",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 60).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "DebugExplain",
        "description": "Get a human-readable explanation of an error from a DebugRun result.",
        "parameters": {
            "type": "object",
            "properties": {
                "error_output": {
                    "type": "string",
                    "description": "The error output from DebugRun.",
                },
                "stack_trace": {
                    "type": "string",
                    "description": "The stack trace string.",
                },
            },
            "required": ["error_output"],
        },
    },
    # ─── Multi-File Refactoring ────────────────────────────────────────
    {
        "type": "function",
        "name": "RefactorRename",
        "description": "Rename a symbol (function/class/variable) across all files in a project.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_root": {
                    "type": "string",
                    "description": "Project root directory.",
                },
                "old_name": {
                    "type": "string",
                    "description": "Current symbol name.",
                },
                "new_name": {
                    "type": "string",
                    "description": "New symbol name.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific files to rename in (omit for all files).",
                },
            },
            "required": ["project_root", "old_name", "new_name"],
        },
    },
    {
        "type": "function",
        "name": "RefactorExtract",
        "description": "Extract code into a new function.",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "File to extract from.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line number (1-indexed).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line number (1-indexed).",
                },
                "new_func_name": {
                    "type": "string",
                    "description": "Name for the new function.",
                },
            },
            "required": ["file", "start_line", "end_line", "new_func_name"],
        },
    },
    {
        "type": "function",
        "name": "RefactorMove",
        "description": "Move a function or class from one file to another.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol_name": {
                    "type": "string",
                    "description": "Name of the function/class to move.",
                },
                "from_file": {
                    "type": "string",
                    "description": "Source file path.",
                },
                "to_file": {
                    "type": "string",
                    "description": "Destination file path.",
                },
            },
            "required": ["symbol_name", "from_file", "to_file"],
        },
    },
    # ─── Data Cleaning ─────────────────────────────────────────────────
    {
        "type": "function",
        "name": "DataLoad",
        "description": "加载CSV或Excel文件，返回行数/列数/列名/数据类型/临时路径。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要加载的数据文件路径（.csv, .xlsx, .xls）",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "type": "function",
        "name": "DataQuality",
        "description": "质量检测：扫描空值、重复行、异常值（IQR方法），给出质量评分0-100。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "数据文件路径（.csv）",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "type": "function",
        "name": "DataClean",
        "description": "执行数据清洗：去重、空值填充（数值填0，字符串填空）、去除首尾空格、列名标准化。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "数据文件路径",
                },
                "output_path": {
                    "type": "string",
                    "description": "清洗后输出路径（默认 D:/codex-local/data/cleaned_data.csv）",
                },
                "remove_duplicates": {
                    "type": "boolean",
                    "description": "是否删除重复行（默认True）",
                },
                "fill_numeric_nulls": {
                    "type": "number",
                    "description": "数值列空值填充值（默认0）",
                },
                "fill_string_nulls": {
                    "type": "string",
                    "description": "字符串列空值填充值（默认空字符串）",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "type": "function",
        "name": "DataStats",
        "description": "计算描述性统计：数值列（均值/标准差/分位数）、分类列（唯一值/Top分布）、相关性矩阵。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "数据文件路径",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "type": "function",
        "name": "DataReport",
        "description": "生成HTML数据质量报告，包含概览/列信息/质量评分/统计图表。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "数据文件路径",
                },
                "output_path": {
                    "type": "string",
                    "description": "报告输出路径（默认 D:/codex-local/data/data_quality_report.html）",
                },
                "title": {
                    "type": "string",
                    "description": "报告标题（默认'数据质量报告'）",
                },
            },
            "required": ["file_path"],
        },
    },
    # ─── SQL 查询 ─────────────────────────────────────────────────────
    {
        "type": "function",
        "name": "SqlQuery",
        "description": "执行SQL查询，支持SQLite/MySQL/PostgreSQL。返回格式化表格结果。",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_string": {
                    "type": "string",
                    "description": "数据库路径或连接字符串（SQLite: 'D:/db/app.db', MySQL: 'mysql://user:pass@host:3306/db'）",
                },
                "query": {
                    "type": "string",
                    "description": "SQL查询语句",
                },
                "params": {
                    "type": "array",
                    "description": "参数化查询参数（防SQL注入）",
                },
            },
            "required": ["connection_string", "query"],
        },
    },
    {
        "type": "function",
        "name": "SqlTables",
        "description": "列出数据库中所有表。",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_string": {
                    "type": "string",
                    "description": "数据库路径或连接字符串",
                },
            },
            "required": ["connection_string"],
        },
    },
    {
        "type": "function",
        "name": "SqlDescribe",
        "description": "获取表的结构（列名/类型/约束）。",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_string": {
                    "type": "string",
                    "description": "数据库路径或连接字符串",
                },
                "table": {
                    "type": "string",
                    "description": "表名",
                },
            },
"required": ["connection_string", "table"],
        },
    },
    # ─── Windows Control ────────────────────────────────────────────────────
    {
        "type": "function",
        "name": "WinScreenshot",
        "description": "Take a screenshot of the entire screen or a region. Returns file path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Save path (optional)."},
                "x": {"type": "integer", "description": "X coordinate of region (optional)."},
                "y": {"type": "integer", "description": "Y coordinate of region (optional)."},
                "width": {"type": "integer", "description": "Width of region (optional)."},
                "height": {"type": "integer", "description": "Height of region (optional)."},
            },
        },
    },
    {
        "type": "function",
        "name": "WinMouseMove",
        "description": "Move mouse cursor to absolute screen coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Target X coordinate."},
                "y": {"type": "integer", "description": "Target Y coordinate."},
            },
            "required": ["x", "y"],
        },
    },
    {
        "type": "function",
        "name": "WinMouseClick",
        "description": "Click at screen coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "clicks": {"type": "integer", "default": 1},
            },
            "required": ["x", "y"],
        },
    },
    {
        "type": "function",
        "name": "WinType",
        "description": "Type text using the keyboard.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type."},
            },
            "required": ["text"],
        },
    },
    {
        "type": "function",
        "name": "WinPress",
        "description": "Press a keyboard key (enter, esc, tab, space, f1-f12, etc).",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name."},
            },
            "required": ["key"],
        },
    },
    {
        "type": "function",
        "name": "WinHotkey",
        "description": "Press a keyboard hotkey (e.g. ctrl+c, win+r, alt+tab).",
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {"type": "array", "items": {"type": "string"}, "description": "Keys to press together."},
            },
            "required": ["keys"],
        },
    },
    {
        "type": "function",
        "name": "WinWindowList",
        "description": "List all open windows.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "WinWindowFind",
        "description": "Find windows by name substring.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Window name contains this string."},
            },
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "WinWindowActivate",
        "description": "Bring a window to the foreground.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Window name contains."},
            },
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "WinProcessList",
        "description": "List running processes.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "WinProcessKill",
        "description": "Kill a process by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Process name contains."},
            },
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "WinScroll",
        "description": "Scroll mouse wheel. Positive=up, negative=down.",
        "parameters": {
            "type": "object",
            "properties": {
                "clicks": {"type": "integer", "description": "Number of clicks."},
            },
            "required": ["clicks"],
        },
    },
    {
        "type": "function",
        "name": "WinDrag",
        "description": "Drag mouse from start to end coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer"},
                "start_y": {"type": "integer"},
                "end_x": {"type": "integer"},
                "end_y": {"type": "integer"},
            },
            "required": ["start_x", "start_y", "end_x", "end_y"],
        },
    },
    # ─── Memory System ──────────────────────────────────────────────────────
    {
        "type": "function",
        "name": "MemoryStore",
        "description": "Store information in long-term memory for future reference.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to remember.",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for the memory.",
                },
                "importance": {
                    "type": "number",
                    "description": "Importance score 0-1 (default: 0.7).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "type": "function",
        "name": "MemoryRecall",
        "description": "Search and recall memories from long-term storage.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant memories.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 5).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "MemoryLearn",
        "description": "Learn and store semantic knowledge (facts, concepts, procedures).",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The knowledge to learn.",
                },
                "title": {
                    "type": "string",
                    "description": "Title for the knowledge.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "type": "function",
        "name": "MemoryForget",
        "description": "Delete a specific memory by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "The memory ID to delete.",
                },
            },
            "required": ["memory_id"],
        },
    },
    {
        "type": "function",
        "name": "MemoryStats",
        "description": "Get memory system statistics.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]


class ToolExecutor:
    def __init__(self, workspace_root: Optional[str] = None):
        default_workspace = str(Path(__file__).parent.parent)  # Project root
        self.workspace_root = Path(workspace_root or os.environ.get("CODEX_WORKSPACE", default_workspace))
        self.sandbox = get_sandbox()

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_root / p

    # ─── Read ────────────────────────────────────────────────────────────────

    def read(self, file_path: str, limit: Optional[int] = None, offset: Optional[int] = None) -> dict:
        try:
            path = self._resolve_path(file_path)
            if not path.exists():
                return {"success": False, "error": f"File not found: {path}"}
            if not path.is_file():
                return {"success": False, "error": f"Not a file: {path}"}

            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            total_lines = len(lines)

            if offset is not None:
                lines = lines[offset:]
            if limit is not None:
                lines = lines[:limit]

            content = "\n".join(lines)

            # Truncate oversized content to prevent context window overflow
            MAX_CONTENT_CHARS = 20_000
            truncated = False
            if len(content) > MAX_CONTENT_CHARS:
                content = content[:MAX_CONTENT_CHARS]
                truncated = True

            result = {
                "success": True,
                "content": content,
                "lines": len(lines),
                "total_lines": total_lines,
                "file_path": str(path),
            }
            if truncated:
                result["truncated"] = True
                result["warning"] = f"Content truncated from {len(chr(10).join(lines))} to {MAX_CONTENT_CHARS} chars. Use offset/limit to read specific sections."
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Write ───────────────────────────────────────────────────────────────

    def write(self, file_path: str, content: str) -> dict:
        try:
            path = self._resolve_path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {
                "success": True,
                "file_path": str(path),
                "bytes": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Edit ────────────────────────────────────────────────────────────────

    def edit(self, file_path: str, old_string: str, new_string: str) -> dict:
        try:
            path = self._resolve_path(file_path)
            if not path.exists():
                return {"success": False, "error": f"File not found: {path}"}

            original = path.read_text(encoding="utf-8", errors="replace")

            if old_string not in original:
                return {
                    "success": False,
                    "error": f"old_string not found in file. Check for whitespace differences.",
                    "hint": f"Looking for: {repr(old_string[:100])}",
                }

            new_content = original.replace(old_string, new_string, 1)
            path.write_text(new_content, encoding="utf-8")

            return {
                "success": True,
                "file_path": str(path),
                "changes": f"Replaced 1 occurrence",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Bash ────────────────────────────────────────────────────────────────

    def bash(self, command: str, timeout: int = 30, cwd: Optional[str] = None) -> dict:
        try:
            work_dir = self._resolve_path(cwd) if cwd else self.workspace_root
            # Ensure Python is in PATH for Windows subprocess
            env = {**os.environ, "TERM": "xterm-256color"}
            py_dir = os.path.dirname(sys.executable)
            if py_dir and py_dir not in env.get("PATH", ""):
                env["PATH"] = py_dir + os.pathsep + env.get("PATH", "")
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                cwd=str(work_dir),
                env=env,
            )
            return {
                "success": proc.returncode == 0,
                "stdout": proc.stdout.decode("utf-8", errors="replace"),
                "stderr": proc.stderr.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
            }
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}

    # ─── Glob ────────────────────────────────────────────────────────────────

    def glob(self, pattern: str, cwd: Optional[str] = None) -> dict:
        try:
            root = self._resolve_path(cwd) if cwd else self.workspace_root
            files = [str(p) for p in root.glob(pattern)]
            return {"success": True, "files": sorted(files), "count": len(files)}
        except Exception as e:
            return {"success": False, "files": [], "error": str(e)}

    def glob_walk(self, root: str, patterns: List[str]) -> dict:
        try:
            root_path = self._resolve_path(root)
            all_files = set()
            for pattern in patterns:
                all_files.update(str(p) for p in root_path.glob(pattern))
            return {"success": True, "files": sorted(all_files), "count": len(all_files)}
        except Exception as e:
            return {"success": False, "files": [], "error": str(e)}

    # ─── Grep ────────────────────────────────────────────────────────────────

    def grep(self, path: str, pattern: str, glob: Optional[str] = None,
             output_mode: str = "content") -> dict:
        try:
            search_path = self._resolve_path(path)
            results = []

            if search_path.is_file():
                files_to_search = [search_path]
            elif search_path.is_dir():
                if glob:
                    files_to_search = list(search_path.glob(glob))
                else:
                    files_to_search = [f for f in search_path.rglob("*") if f.is_file()]
            else:
                return {"success": False, "error": f"Path not found: {search_path}"}

            for fpath in files_to_search:
                if not fpath.is_file():
                    continue
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    for lineno, line in enumerate(content.splitlines(), 1):
                        if re.search(pattern, line):
                            if output_mode == "content":
                                results.append({
                                    "file": str(fpath),
                                    "line": lineno,
                                    "text": line.rstrip(),
                                })
                            elif output_mode == "count":
                                results.append({
                                    "file": str(fpath),
                                    "line": lineno,
                                    "text": line.rstrip(),
                                })
                except Exception:
                    continue

            if output_mode == "count":
                from collections import Counter
                file_counts = dict(Counter(r["file"] for r in results))
                return {"success": True, "counts": file_counts, "total": len(results)}

            return {"success": True, "results": results, "count": len(results)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── TodoWrite ──────────────────────────────────────────────────────────

    def todo_write(self, file_path: str, todos: List[dict]) -> dict:
        return self.write(file_path, json.dumps({"todos": todos, "updated": datetime.now().isoformat()}, indent=2))

    # ─── NotebookEdit ───────────────────────────────────────────────────────

    def notebook_edit(self, notebook_path: str, new_source: str,
                      cell_id: Optional[str] = None, cell_type: str = "code",
                      edit_mode: str = "replace") -> dict:
        try:
            path = self._resolve_path(notebook_path)
            if not path.exists():
                # Create a new notebook
                nb = {
                    "cells": [],
                    "metadata": {},
                    "nbformat": 4,
                    "nbformat_minor": 5,
                }
            else:
                nb = json.loads(path.read_text(encoding="utf-8"))

            if edit_mode == "insert":
                cell = {"cell_type": cell_type, "metadata": {}, "source": new_source}
                nb.setdefault("cells", []).insert(0, cell)
            elif edit_mode == "delete":
                if cell_id and "cells" in nb:
                    nb["cells"] = [c for c in nb["cells"] if c.get("id") != cell_id]
            else:
                if cell_id and "cells" in nb:
                    for c in nb["cells"]:
                        if c.get("id") == cell_id:
                            c["source"] = new_source
                            break
                else:
                    # Replace last or append
                    if nb.get("cells"):
                        nb["cells"][-1]["source"] = new_source
                    else:
                        nb.setdefault("cells", []).append({"cell_type": cell_type, "metadata": {}, "source": new_source})

            path.write_text(json.dumps(nb, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"success": True, "file_path": str(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── WebSearch ──────────────────────────────────────────────────────────

    def web_search(self, query: str, recency_days: Optional[int] = None) -> dict:
        # Delegate to skill or return stub
        return {
            "success": False,
            "error": "WebSearch requires MCP server or external tool. Use WebFetch instead.",
            "query": query,
        }

    # ─── WebFetch ───────────────────────────────────────────────────────────

    def web_fetch(self, url: str, prompt: str) -> dict:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            return {
                "success": True,
                "url": url,
                "content": content[:2000],
                "status": 200,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "url": url}

    # ─── Project Analysis ────────────────────────────────────────────────

    def projectanalyze(self, root: str, max_files: int = 1000) -> dict:
        try:
            from tools.project_analyzer import ProjectAnalyzer, analyze_project
            result = analyze_project(root, max_files)
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def projectfindsymbol(self, name: str) -> dict:
        try:
            # Get the current project graph from the last analyze call
            # We store it on self for reuse
            if not hasattr(self, "_project_graph_cache"):
                from tools.project_analyzer import ProjectAnalyzer
                analyzer = ProjectAnalyzer(str(self.workspace_root))
                self._project_graph_cache = analyzer.analyze()
            graph = self._project_graph_cache
            symbols = graph.all_symbols.get(name, [])
            return {
                "success": True,
                "symbol": name,
                "definitions": [{"file": s.file, "line": s.line, "type": s.type} for s in symbols],
                "count": len(symbols),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def projectexplainsymbol(self, name: str) -> dict:
        try:
            from tools.project_analyzer import ProjectAnalyzer
            if not hasattr(self, "_project_graph_cache"):
                analyzer = ProjectAnalyzer(str(self.workspace_root))
                self._project_graph_cache = analyzer.analyze()
            graph = self._project_graph_cache
            analyzer = ProjectAnalyzer(str(self.workspace_root))
            explanation = analyzer.explain_symbol(graph, name)
            return {"success": True, "explanation": explanation}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Browser Automation ─────────────────────────────────────────────

    def browsernavigate(self, url: str, wait_until: str = "networkidle") -> dict:
        try:
            from tools.browser_automation import get_browser
            browser = get_browser(headless=False)
            result = browser.navigate(url, wait_until=wait_until)
            return {"success": result.success, "url": result.url, "title": result.title, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def browserclick(self, selector: str) -> dict:
        try:
            from tools.browser_automation import get_browser
            browser = get_browser()
            result = browser.click(selector)
            return {"success": result.success, "url": browser.url(), "title": browser.title(), "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def browsertype(self, selector: str, text: str, clear_first: bool = True) -> dict:
        try:
            from tools.browser_automation import get_browser
            browser = get_browser()
            result = browser.type(selector, text, clear_first=clear_first)
            return {"success": result.success, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def browserscreenshot(self, path: str, full_page: bool = False, selector: Optional[str] = None) -> dict:
        try:
            from tools.browser_automation import get_browser
            browser = get_browser()
            result = browser.screenshot(path=path, full_page=full_page, selector=selector)
            return {"success": result.success, "screenshot_path": result.screenshot_path, "error": result.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def browserevaluate(self, script: str) -> dict:
        try:
            from tools.browser_automation import get_browser
            browser = get_browser()
            result = browser.evaluate(script)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def browsertext(self, selector: str) -> dict:
        try:
            from tools.browser_automation import get_browser
            browser = get_browser()
            text = browser.text(selector)
            return {"success": True, "text": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Git Integration ────────────────────────────────────────────────

    def gitstatus(self, repo: str) -> dict:
        try:
            from tools.git_integration import GitRepo
            r = GitRepo(repo)
            s = r.status()
            return {
                "success": True,
                "branch": s.branch,
                "clean": s.clean,
                "staged": s.staged,
                "modified": s.modified,
                "untracked": s.untracked,
                "conflicts": s.conflicts,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def gitlog(self, repo: str, max_count: int = 50) -> dict:
        try:
            from tools.git_integration import GitRepo
            r = GitRepo(repo)
            commits = r.log(max_count=max_count)
            return {"success": True, "commits": [{"hash": c.hash, "author": c.author, "message": c.message, "date": c.date} for c in commits]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def gitdiff(self, repo: str, ref1: str = "HEAD", ref2: str = "") -> dict:
        try:
            from tools.git_integration import GitRepo
            r = GitRepo(repo)
            diffs = r.diff(ref1, ref2)
            return {"success": True, "diffs": [{"file": d.file, "status": d.status, "insertions": d.insertions, "deletions": d.deletions} for d in diffs]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def gitcommit(self, repo: str, message: str, files: Optional[List[str]] = None) -> dict:
        try:
            from tools.git_integration import GitRepo
            r = GitRepo(repo)
            if files:
                r.add(files)
            hash = r.commit(message)
            return {"success": bool(hash), "commit": hash}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def gitbranch(self, repo: str, create: Optional[str] = None, checkout: Optional[str] = None) -> dict:
        try:
            from tools.git_integration import GitRepo
            r = GitRepo(repo)
            if checkout:
                success = r.checkout(checkout)
                return {"success": success, "action": f"checkout {checkout}"}
            elif create:
                name = r.create_branch(create)
                return {"success": bool(name), "branch": name}
            else:
                return {"success": True, "branches": r.branches(), "current": r.current_branch()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def gitblame(self, repo: str, file: str) -> dict:
        try:
            from tools.git_integration import GitRepo
            r = GitRepo(repo)
            blame = r.blame(file)
            return {"success": True, "blame": blame[:100]}  # limit to 100 lines
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── GitHub Integration ──────────────────────────────────────────────

    def githubclone(self, repo_url: str, local_path: str, depth: int = 1) -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.clone_repo(repo_url, local_path, depth)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubgetrepo(self, owner: str, repo: str) -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.get_repo_info(owner, repo)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githublistbranches(self, owner: str, repo: str) -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.list_branches(owner, repo)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubcreatebranch(self, owner: str, repo: str, branch_name: str, from_branch: str = "main") -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.create_branch(owner, repo, branch_name, from_branch)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubgetfile(self, owner: str, repo: str, path: str, ref: str = "main") -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.get_file_content(owner, repo, path, ref)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubcreatefile(self, owner: str, repo: str, path: str, content: str, message: str, branch: str = "main") -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.create_or_update_file(owner, repo, path, content, message, branch)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githublistprs(self, owner: str, repo: str, state: str = "open") -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.list_pull_requests(owner, repo, state)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubcreatepr(self, owner: str, repo: str, title: str, body: str, head: str, base: str = "main") -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.create_pull_request(owner, repo, title, body, head, base)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubautocreatepr(self, owner: str, repo: str, feature_branch: str, base_branch: str = "main",
                           title: str = "", body: str = "", auto_merge: bool = False) -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.auto_create_pr(owner, repo, feature_branch, base_branch, title or None, body or None, auto_merge)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubmergepr(self, owner: str, repo: str, pull_number: int, merge_method: str = "merge") -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.merge_pull_request(owner, repo, pull_number, merge_method=merge_method)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githublistissues(self, owner: str, repo: str, state: str = "open") -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.list_issues(owner, repo, state)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubcreateissue(self, owner: str, repo: str, title: str, body: str, labels: List[str] = None) -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.create_issue(owner, repo, title, body, labels or [])
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubsearchcode(self, query: str, owner: str = "", repo: str = "") -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.search_code(query, owner or None, repo or None)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def githubratelimit(self) -> dict:
        try:
            from tools.github_integration import get_github
            github = get_github()
            return github.get_rate_limit()
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Code Debugger ──────────────────────────────────────────────────

    def debgrun(self, code: str, globals: Optional[Dict] = None, timeout: int = 30) -> dict:
        try:
            from tools.debugger import CodeDebugger
            dbg = CodeDebugger(str(self.workspace_root))
            result = dbg.run(code, globals_dict=globals, timeout=timeout)
            return {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "exit_code": result.exit_code,
                "exception_type": result.exception_type,
                "exception_message": result.exception_message,
                "stack_trace": result.stack_trace,
                "frames": [{"file": f.filename, "line": f.lineno, "function": f.function, "locals": f.locals} for f in (result.frames or [])],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def debugpytest(self, path: str, test_name: Optional[str] = None, timeout: int = 60) -> dict:
        try:
            from tools.debugger import run_pytest
            result = run_pytest(path, test_name=test_name, timeout=timeout)
            return {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "exit_code": result.exit_code,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def debugexplain(self, error_output: str, stack_trace: Optional[str] = None) -> dict:
        try:
            from tools.debugger import CodeDebugger
            dbg = CodeDebugger()
            # Reconstruct a DebugResult from the error info
            from tools.debugger import DebugResult
            result = DebugResult(success=False, output=error_output, error=error_output, stack_trace=stack_trace or "")
            explanation = dbg.explain_error(result)
            return {"success": True, "explanation": explanation}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Multi-File Refactoring ────────────────────────────────────────

    def refactorrename(self, project_root: str, old_name: str, new_name: str, files: Optional[List[str]] = None) -> dict:
        try:
            from tools.refactorer import MultiModuleRefactorer
            ref = MultiModuleRefactorer(project_root)
            plan = ref.rename_symbol(old_name, new_name, files=files)
            if not plan.changes:
                return {"success": False, "error": "No occurrences found"}
            results = ref.apply_plan(plan)
            return {"success": len(results["failed"]) == 0, "applied": results["applied"], "warnings": plan.warnings}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def refactorextract(self, file: str, start_line: int, end_line: int, new_func_name: str) -> dict:
        try:
            from tools.refactorer import MultiModuleRefactorer
            ref = MultiModuleRefactorer(str(self.workspace_root))
            plan = ref.extract_function(file, start_line, end_line, new_func_name)
            if not plan.changes:
                return {"success": False, "error": "Could not extract", "warnings": plan.warnings}
            results = ref.apply_plan(plan)
            return {"success": len(results["failed"]) == 0, "applied": results["applied"], "warnings": plan.warnings}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def refactormove(self, symbol_name: str, from_file: str, to_file: str) -> dict:
        try:
            from tools.refactorer import MultiModuleRefactorer
            ref = MultiModuleRefactorer(str(self.workspace_root))
            plan = ref.move_symbol(symbol_name, from_file, to_file)
            if not plan.changes:
                return {"success": False, "error": "Could not move", "warnings": plan.warnings}
            results = ref.apply_plan(plan)
            return {"success": len(results["failed"]) == 0, "applied": results["applied"], "warnings": plan.warnings}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Data Cleaner ─────────────────────────────────────────────────

    def dataload(self, file_path: str) -> dict:
        try:
            from tools.data_cleaner import load_data
            return load_data(file_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def dataquality(self, file_path: str) -> dict:
        try:
            from tools.data_cleaner import quality_check
            return quality_check(file_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def dataclean(
        self,
        file_path: str,
        output_path: Optional[str] = None,
        remove_duplicates: bool = True,
        fill_numeric_nulls: float = 0.0,
        fill_string_nulls: str = "",
    ) -> dict:
        try:
            from tools.data_cleaner import clean_data
            return clean_data(
                file_path=file_path,
                output_path=output_path,
                remove_duplicates=remove_duplicates,
                fill_numeric_nulls=fill_numeric_nulls,
                fill_string_nulls=fill_string_nulls,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}

    def datastats(self, file_path: str) -> dict:
        try:
            from tools.data_cleaner import calc_stats
            return calc_stats(file_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def datareport(self, file_path: str, output_path: Optional[str] = None, title: str = "数据质量报告") -> dict:
        try:
            from tools.data_cleaner import gen_report
            return gen_report(data_path=file_path, output_path=output_path, title=title)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── SQL Tool ───────────────────────────────────────────────────────

    def sqlquery(self, connection_string: str, query: str, params: Optional[List] = None) -> dict:
        try:
            from tools.sql_tool import sql_query, format_query_result
            result = sql_query(connection_string, query, params)
            return {
                "success": result.success,
                "columns": result.columns,
                "rows": [list(r) for r in result.rows],
                "row_count": result.row_count,
                "affected_rows": result.affected_rows,
                "error": result.error,
                "duration_ms": result.duration_ms,
                "formatted": format_query_result(result),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sqltables(self, connection_string: str) -> dict:
        try:
            from tools.sql_tool import sql_tables, format_query_result
            result = sql_tables(connection_string)
            return {
                "success": result.success,
                "tables": [r[0] for r in result.rows],
                "error": result.error,
                "formatted": format_query_result(result),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sqldescribe(self, connection_string: str, table: str) -> dict:
        try:
            from tools.sql_tool import sql_describe, format_query_result
            result = sql_describe(connection_string, table)
            return {
                "success": result.success,
                "columns": result.columns,
                "rows": [list(r) for r in result.rows],
                "error": result.error,
                "formatted": format_query_result(result),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Windows Control ────────────────────────────────────────────────────

    def winscreenshot(self, path: str = "", x: Optional[int] = None, y: Optional[int] = None,
                      width: Optional[int] = None, height: Optional[int] = None) -> dict:
        try:
            from tools.win_control import screenshot
            region = (x, y, width, height) if x is not None else None
            r = screenshot(path or None, region)
            return {"success": r.success, "message": r.message, "data": r.data, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winmousemove(self, x: int, y: int) -> dict:
        try:
            from tools.win_control import mouse_move
            r = mouse_move(x, y)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winmouseclick(self, x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
        try:
            from tools.win_control import mouse_click
            r = mouse_click(x, y, button, clicks)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def wintype(self, text: str) -> dict:
        try:
            from tools.win_control import keyboard_type
            r = keyboard_type(text)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winpress(self, key: str) -> dict:
        try:
            from tools.win_control import keyboard_press
            r = keyboard_press(key)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winhotkey(self, keys: List[str]) -> dict:
        try:
            from tools.win_control import keyboard_hotkey
            r = keyboard_hotkey(*keys)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winwindowlist(self) -> dict:
        try:
            from tools.win_control import window_list
            r = window_list()
            return {"success": r.success, "message": r.message, "windows": r.data.get("windows", []) if r.data else [], "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winwindowfind(self, name: str) -> dict:
        try:
            from tools.win_control import window_find
            r = window_find(name)
            return {"success": r.success, "message": r.message, "windows": r.data.get("windows", []) if r.data else [], "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winwindowactivate(self, name: str) -> dict:
        try:
            from tools.win_control import window_activate
            r = window_activate(name)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winprocesslist(self) -> dict:
        try:
            from tools.win_control import process_list
            r = process_list()
            return {"success": r.success, "message": r.message, "processes": r.data.get("processes", []) if r.data else [], "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winprocesskill(self, name: str) -> dict:
        try:
            from tools.win_control import process_kill
            r = process_kill(name)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def winscroll(self, clicks: int) -> dict:
        try:
            from tools.win_control import mouse_scroll
            r = mouse_scroll(clicks)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def windrag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> dict:
        try:
            from tools.win_control import mouse_drag
            r = mouse_drag(start_x, start_y, end_x, end_y)
            return {"success": r.success, "message": r.message, "error": r.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Memory System ──────────────────────────────────────────────────────

    def memorystore(self, content: str, title: str = "", importance: float = 0.7,
                    tags: Optional[List[str]] = None) -> dict:
        try:
            from runtime.memory import get_memory_manager
            manager = get_memory_manager()
            memory_id = manager.remember(
                content=content,
                importance=importance,
                tags=tags or [],
                title=title or content[:50],
            )
            return {
                "success": True,
                "memory_id": memory_id,
                "message": f"Stored memory: {title or content[:50]}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def memoryrecall(self, query: str, limit: int = 5) -> dict:
        try:
            from runtime.memory import get_memory_manager
            manager = get_memory_manager()
            results = manager.recall(query, top_k=limit)

            memories = []
            for r in results:
                memories.append({
                    "source": r.get("source", "unknown"),
                    "content": r.get("content", "")[:200],
                    "title": r.get("title", ""),
                    "tier": r.get("tier", ""),
                    "score": r.get("score", 0),
                    "importance": r.get("importance", 0),
                    "tags": r.get("tags", []),
                    "memory_id": r.get("memory_id", ""),
                })

            return {
                "success": True,
                "query": query,
                "count": len(memories),
                "memories": memories,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def memorylearn(self, content: str, title: str = "", tags: Optional[List[str]] = None) -> dict:
        try:
            from runtime.memory import get_memory_manager
            manager = get_memory_manager()
            memory_id = manager.learn(
                content=content,
                tags=tags or [],
                title=title or content[:50],
            )
            return {
                "success": True,
                "memory_id": memory_id,
                "message": f"Learned: {title or content[:50]}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def memoryforget(self, memory_id: str) -> dict:
        try:
            from runtime.memory import get_memory_manager
            manager = get_memory_manager()
            success = manager.forget(memory_id)
            return {
                "success": success,
                "message": f"Forgot memory: {memory_id}" if success else f"Memory not found: {memory_id}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def memorystats(self) -> dict:
        try:
            from runtime.memory import get_memory_manager
            manager = get_memory_manager()
            stats = manager.get_stats()
            return {
                "success": True,
                "stats": stats,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Sandbox Execute ────────────────────────────────────────────────────

    def sandbox_exec(self, code: str, language: str = "python", session_id: Optional[str] = None) -> dict:
        result = self.sandbox.execute(code, language, session_id)
        return {
            "success": result.exit_code == 0 and not result.timed_out,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
            "error": result.error,
            "id": result.id,
        }

    # ─── Execute Tool by Name ───────────────────────────────────────────────

    def execute_tool(self, name: str, arguments: dict) -> dict:
        method = getattr(self, name.lower().replace("-", "_"), None)
        if method is None:
            # Try the exact name
            method = getattr(self, name, None)
        if method is None:
            return {"success": False, "error": f"Unknown tool: {name}"}
        try:
            result = method(**arguments)
            return result
        except TypeError as e:
            # Maybe missing required argument
            return {"success": False, "error": f"Tool argument error: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─── Global singleton ────────────────────────────────────────────────────────

_executor: Optional[ToolExecutor] = None


def get_executor() -> ToolExecutor:
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
    return _executor


# ─── CLI test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ex = get_executor()
    print(json.dumps(ex.glob("**/*.py", cwd="D:/codex-local"), indent=2))