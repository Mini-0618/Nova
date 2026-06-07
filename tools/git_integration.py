"""
Codex-Local Git Integration
GitPython-based Git operations: diff, log, blame, branch, commit, status, stash, merge.
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

# ─── Git Executable Resolver ─────────────────────────────────────────────────

def _find_git_exe() -> Optional[str]:
    """Find git.exe with priority: PATH > common Windows locations."""
    # 1. Try PATH
    git_path = shutil.which("git")
    if git_path:
        return git_path

    # 2. Try common Windows locations (in order of likelihood)
    candidates = [
        Path("C:/Program Files/Git/cmd/git.exe"),
        Path("C:/Program Files/Git/bin/git.exe"),
        Path("C:/Program Files (x86)/Git/cmd/git.exe"),
        Path("C:/Users/lenovo/AppData/Local/Programs/Git/cmd/git.exe"),
        Path("C:/Program Files/Git/cmd/git.exe"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)

    return None

# Set git executable BEFORE importing git
GIT_EXE = os.environ.get("GIT_PYTHON_GIT_EXECUTABLE") or _find_git_exe()
if GIT_EXE:
    os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = GIT_EXE

import git  # noqa: E402


@dataclass
class GitCommit:
    hash: str
    author: str
    email: str
    date: str
    message: str
    files_changed: List[str] = field(default_factory=list)


@dataclass
class GitDiff:
    file: str
    status: str  # 'modified', 'added', 'deleted', 'renamed'
    hunks: List[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0


@dataclass
class GitStatus:
    branch: str
    clean: bool
    staged: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    untracked: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)


class GitRepo:
    """
    High-level Git operations.

    Usage:
        repo = GitRepo("D:/myproject")
        print(repo.status())
        commits = repo.log(max_count=10)
        diffs = repo.diff("HEAD~1", "HEAD")
        repo.checkout("feature-branch")
        repo.commit("my message")
    """

    def __init__(self, path: str):
        self.path = Path(path).resolve()
        try:
            self.repo = git.Repo(str(self.path))
        except git.InvalidGitRepositoryError:
            self.repo = None

    def close(self):
        """Release GitPython resources, especially on Windows temp repos."""
        if self.repo is not None:
            self.repo.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def is_repo(self) -> bool:
        return self.repo is not None

    # ─── Status ────────────────────────────────────────────────────────────

    def status(self) -> GitStatus:
        """Get current git status."""
        if not self.repo:
            return GitStatus(branch="", clean=False)

        branch = self.repo.active_branch.name
        status = self.repo.git.status(porcelain=True, untracked_files="all")

        staged = []
        modified = []
        untracked = []
        conflicts = []

        for line in status.split("\n"):
            if not line:
                continue
            if line.startswith("?? "):
                untracked.append(line[3:])
            elif line.startswith("UU "):
                conflicts.append(line[3:])
            elif line.startswith(" M"):
                modified.append(line[3:])
            elif line.startswith("M "):
                staged.append(line[2:])
            elif line.startswith("A "):
                staged.append(line[2:])
            elif line.startswith("D "):
                staged.append(line[2:])

        return GitStatus(
            branch=branch,
            clean=len(modified) == 0 and len(staged) == 0 and len(conflicts) == 0 and len(untracked) == 0,
            staged=staged,
            modified=modified,
            untracked=untracked,
            conflicts=conflicts,
        )

    # ─── Log ───────────────────────────────────────────────────────────────

    def log(self, max_count: int = 50, path: Optional[str] = None) -> List[GitCommit]:
        """Get commit history."""
        if not self.repo:
            return []

        commits = []
        try:
            for commit in self.repo.iter_commits(max_count=max_count, paths=path):
                commits.append(GitCommit(
                    hash=commit.hexsha[:12],
                    author=commit.author.name,
                    email=commit.author.email,
                    date=commit.committed_datetime.isoformat(),
                    message=commit.message.strip(),
                ))
        except Exception:
            pass

        return commits

    # ─── Diff ──────────────────────────────────────────────────────────────

    def diff(self, ref1: str = "HEAD", ref2: str = "", file: Optional[str] = None) -> List[GitDiff]:
        """
        Get diff between two refs.
        If ref2 is empty, diff ref1 against working tree.
        """
        if not self.repo:
            return []

        diffs = []
        try:
            if file:
                diff_index = self.repo.diff(ref1, ref2, "--", file)
            else:
                diff_index = self.repo.diff(ref1, ref2)

            for d in diff_index:
                diffs.append(GitDiff(
                    file=d.a_path or d.b_path or "",
                    status=self._get_diff_status(d),
                    insertions=d.additions or 0,
                    deletions=d.deletions or 0,
                ))
        except Exception as e:
            pass

        return diffs

    def _get_diff_status(self, d) -> str:
        if d.new_file:
            return "added"
        elif d.deleted_file:
            return "deleted"
        elif d.renamed_file:
            return "renamed"
        else:
            return "modified"

    def diff_stat(self, ref1: str = "HEAD", ref2: str = "") -> Dict[str, int]:
        """Get a summary of changes."""
        diffs = self.diff(ref1, ref2)
        return {
            "files_changed": len(diffs),
            "insertions": sum(d.insertions for d in diffs),
            "deletions": sum(d.deletions for d in diffs),
        }

    # ─── Blame ─────────────────────────────────────────────────────────────

    def blame(self, file: str, max_lines: int = 100) -> List[Dict[str, Any]]:
        """Get blame information for a file."""
        if not self.repo:
            return []

        try:
            blame = self.repo.blame("HEAD", "--", file)
            result = []
            for commit, lines in blame:
                for line in lines[:max_lines]:
                    result.append({
                        "commit": commit.hexsha[:12],
                        "author": commit.author.name,
                        "date": commit.committed_datetime.isoformat(),
                        "line": line,
                    })
            return result[:max_lines]
        except Exception:
            return []

    # ─── Branch ────────────────────────────────────────────────────────────

    def branches(self) -> List[str]:
        """List all local branches."""
        if not self.repo:
            return []
        return [b.name for b in self.repo.branches]

    def current_branch(self) -> str:
        """Get current branch name."""
        if not self.repo:
            return ""
        return self.repo.active_branch.name

    def create_branch(self, name: str, checkout: bool = True) -> str:
        """Create a new branch."""
        if not self.repo:
            return ""
        try:
            branch = self.repo.create_head(name, checkout=checkout)
            return branch.name
        except Exception:
            return ""

    def checkout(self, ref: str, create_if_missing: bool = False) -> bool:
        """Checkout a branch or commit."""
        if not self.repo:
            return False
        try:
            if create_if_missing and ref not in self.repo.branches:
                self.repo.create_head(ref).checkout()
            else:
                self.repo.git.checkout(ref)
            return True
        except Exception:
            return False

    # ─── Commit ────────────────────────────────────────────────────────────

    def add(self, paths: List[str]) -> bool:
        """Stage files."""
        if not self.repo:
            return False
        try:
            self.repo.index.add(paths)
            return True
        except Exception:
            return False

    def commit(self, message: str, author_name: Optional[str] = None, author_email: Optional[str] = None) -> str:
        """Create a commit."""
        if not self.repo:
            return ""
        try:
            if author_name:
                self.repo.config_writer().set_value("user", "name", author_name).release()
            if author_email:
                self.repo.config_writer().set_value("user", "email", author_email).release()

            commit = self.repo.index.commit(message)
            return commit.hexsha[:12]
        except Exception:
            return ""

    def amend(self, message: Optional[str] = None, author_name: Optional[str] = None, author_email: Optional[str] = None) -> str:
        """Amend the last commit."""
        if not self.repo:
            return ""
        try:
            if author_name:
                self.repo.config_writer().set_value("user", "name", author_name).release()
            if author_email:
                self.repo.config_writer().set_value("user", "email", author_email).release()

            self.repo.git.commit("--amend", "--no-edit")
            return self.repo.head.commit.hexsha[:12]
        except Exception:
            return ""

    # ─── Stash ─────────────────────────────────────────────────────────────

    def stash(self, message: str = "", include_untracked: bool = True) -> bool:
        """Stash current changes."""
        if not self.repo:
            return False
        try:
            flags = ["--include-untracked"] if include_untracked else []
            self.repo.git.stash("push", "-m", message, *flags)
            return True
        except Exception:
            return False

    def stash_list(self, max_count: int = 20) -> List[Dict[str, str]]:
        """List stashes."""
        if not self.repo:
            return []
        try:
            stashes = []
            for line in self.repo.git.stash("list", f"--format=%gd|%s|%ai").split("\n"):
                if "|" in line:
                    parts = line.split("|")
                    stashes.append({
                        "ref": parts[0],
                        "message": parts[1] if len(parts) > 1 else "",
                        "date": parts[2] if len(parts) > 2 else "",
                    })
            return stashes[:max_count]
        except Exception:
            return []

    def stash_pop(self) -> bool:
        """Apply and remove the last stash."""
        if not self.repo:
            return False
        try:
            self.repo.git.stash("pop")
            return True
        except Exception:
            return False

    # ─── Merge ─────────────────────────────────────────────────────────────

    def merge(self, branch: str, message: Optional[str] = None) -> Dict[str, Any]:
        """Merge a branch into current branch."""
        if not self.repo:
            return {"success": False, "error": "Not a git repo"}

        try:
            self.repo.git.merge(branch)
            return {"success": True, "merged": branch}
        except git.GitCommandError as e:
            if "CONFLICT" in str(e):
                return {"success": False, "conflict": True, "error": str(e)}
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def resolve_conflicts(self, resolution: Dict[str, str]) -> bool:
        """Resolve conflicts by choosing sides."""
        if not self.repo:
            return False
        try:
            for path, choice in resolution.items():
                if choice == "ours":
                    # Take our version
                    self.repo.git.checkout("--ours", path)
                elif choice == "theirs":
                    self.repo.git.checkout("--theirs", path)
                self.repo.index.add([path])
            return True
        except Exception:
            return False

    # ─── Tags ─────────────────────────────────────────────────────────────

    def tags(self) -> List[str]:
        """List all tags."""
        if not self.repo:
            return []
        return [t.name for t in self.repo.tags]

    def create_tag(self, name: str, message: Optional[str] = None) -> str:
        """Create a tag."""
        if not self.repo:
            return ""
        try:
            if message:
                self.repo.create_tag(name, message=message)
            else:
                self.repo.create_tag(name)
            return name
        except Exception:
            return ""

    # ─── Remote ────────────────────────────────────────────────────────────

    def remotes(self) -> List[str]:
        """List remotes."""
        if not self.repo:
            return []
        return [r.name for r in self.repo.remotes]

    def fetch(self, remote: str = "origin") -> bool:
        """Fetch from a remote."""
        if not self.repo:
            return False
        try:
            self.repo.remotes[remote].fetch()
            return True
        except Exception:
            return False

    def pull(self, remote: str = "origin") -> bool:
        """Pull from a remote."""
        if not self.repo:
            return False
        try:
            self.repo.remotes[remote].pull()
            return True
        except Exception:
            return False

    def push(self, remote: str = "origin", branch: Optional[str] = None, tags: bool = False) -> bool:
        """Push to a remote."""
        if not self.repo:
            return False
        try:
            kwargs = {}
            if tags:
                kwargs["tags"] = True
            self.repo.remotes[remote].push(branch or self.current_branch(), **kwargs)
            return True
        except Exception:
            return False

    # ─── Search ────────────────────────────────────────────────────────────

    def search(self, query: str, path: Optional[str] = None, max_count: int = 50) -> List[Dict[str, Any]]:
        """Search commit messages and code."""
        if not self.repo:
            return []
        results = []
        try:
            for line in self.repo.git.log(all=True, grep=query, max_count=max_count, format="%H|%s|%ai").split("\n"):
                if "|" in line:
                    parts = line.split("|")
                    results.append({
                        "hash": parts[0],
                        "message": parts[1] if len(parts) > 1 else "",
                        "date": parts[2] if len(parts) > 2 else "",
                    })
        except Exception:
            pass
        return results

    # ─── Reset ─────────────────────────────────────────────────────────────

    def reset(self, ref: str, mode: str = "mixed") -> bool:
        """Reset HEAD to a ref. mode: soft|mixed|hard."""
        if not self.repo:
            return False
        try:
            self.repo.git.reset(ref, mode)
            return True
        except Exception:
            return False


# ─── Tool wrapper ───────────────────────────────────────────────────────────

def git_operation(operation: str, path: str, **kwargs) -> Dict[str, Any]:
    """
    Execute a git operation. Used by the tool executor.
    """
    try:
        repo = GitRepo(path)

        if operation == "status":
            s = repo.status()
            return {
                "success": True,
                "branch": s.branch,
                "clean": s.clean,
                "staged": s.staged,
                "modified": s.modified,
                "untracked": s.untracked,
                "conflicts": s.conflicts,
            }

        elif operation == "log":
            commits = repo.log(max_count=kwargs.get("max_count", 50))
            return {"success": True, "commits": [asdict(c) for c in commits]}

        elif operation == "diff":
            diffs = repo.diff(kwargs.get("ref1", "HEAD"), kwargs.get("ref2", ""))
            return {"success": True, "diffs": [asdict(d) for d in diffs]}

        elif operation == "diff_stat":
            stat = repo.diff_stat(kwargs.get("ref1", "HEAD"), kwargs.get("ref2", ""))
            return {"success": True, "stat": stat}

        elif operation == "blame":
            blame = repo.blame(kwargs.get("file", ""))
            return {"success": True, "blame": blame}

        elif operation == "branch":
            return {"success": True, "branches": repo.branches(), "current": repo.current_branch()}

        elif operation == "checkout":
            success = repo.checkout(kwargs.get("ref", ""))
            return {"success": success}

        elif operation == "commit":
            msg = kwargs.get("message", "")
            if not msg:
                return {"success": False, "error": "message required"}
            hash = repo.commit(msg)
            return {"success": bool(hash), "commit": hash}

        elif operation == "add":
            paths = kwargs.get("paths", [])
            success = repo.add(paths)
            return {"success": success}

        elif operation == "stash":
            msg = kwargs.get("message", "Codex-Local auto-stash")
            success = repo.stash(msg)
            return {"success": success}

        elif operation == "stash_list":
            return {"success": True, "stashes": repo.stash_list()}

        elif operation == "stash_pop":
            return {"success": repo.stash_pop()}

        elif operation == "merge":
            result = repo.merge(kwargs.get("branch", ""))
            return result

        elif operation == "tags":
            return {"success": True, "tags": repo.tags()}

        elif operation == "search":
            results = repo.search(kwargs.get("query", ""))
            return {"success": True, "results": results}

        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    repo = GitRepo(path)
    if repo.is_repo():
        s = repo.status()
        print(f"Branch: {s.branch}, Clean: {s.clean}")
        print(f"Staged: {s.staged[:3]}, Modified: {s.modified[:3]}")
    else:
        print("Not a git repository")
