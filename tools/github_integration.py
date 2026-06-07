"""
GitHub Integration Module for Codex-Local
Provides deep GitHub API integration including:
- Clone repositories
- Create/Manage Pull Requests
- List/Manage Issues
- Read/Write files
- Branch management
"""

import os
import json
import subprocess
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitHubConfig:
    """GitHub configuration"""
    token: str = ""
    api_base: str = "https://api.github.com"
    default_branch: str = "main"

    def __post_init__(self):
        if not self.token:
            self.token = os.environ.get("GITHUB_TOKEN", "")


class GitHubIntegration:
    """GitHub API integration class"""

    def __init__(self, config: Optional[GitHubConfig] = None):
        self.config = config or GitHubConfig()
        self.session = requests.Session()
        self._setup_session()

    def _setup_session(self):
        """Setup request session with headers"""
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if self.config.token:
            self.session.headers["Authorization"] = f"token {self.config.token}"

    def _check_token(self):
        """Check if GitHub token is set"""
        if not self.config.token:
            raise ValueError("GitHub token not set. Set GITHUB_TOKEN environment variable or pass token in config.")

    # ─── Repository Operations ─────────────────────────────────────────────

    def clone_repo(self, repo_url: str, local_path: str, depth: int = 1) -> Dict[str, Any]:
        """Clone a repository"""
        try:
            cmd = ["git", "clone"]
            if depth > 0:
                cmd.extend(["--depth", str(depth)])
            cmd.extend([repo_url, local_path])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                return {"success": False, "error": result.stderr}

            return {"success": True, "path": local_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_repo_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository information"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}"
        response = self.session.get(url)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def list_repos(self, owner: str, repo_type: str = "all", sort: str = "updated", per_page: int = 30) -> Dict[str, Any]:
        """List repositories for a user/org"""
        self._check_token()
        url = f"{self.config.api_base}/users/{owner}/repos"
        params = {"type": repo_type, "sort": sort, "per_page": per_page}
        response = self.session.get(url, params=params)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    # ─── Branch Operations ────────────────────────────────────────────────

    def list_branches(self, owner: str, repo: str) -> Dict[str, Any]:
        """List branches in a repository"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/branches"
        response = self.session.get(url)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def create_branch(self, owner: str, repo: str, branch_name: str, from_branch: str = "main") -> Dict[str, Any]:
        """Create a new branch"""
        self._check_token()

        # Get the SHA of the source branch
        url = f"{self.config.api_base}/repos/{owner}/{repo}/git/refs/heads/{from_branch}"
        response = self.session.get(url)

        if response.status_code != 200:
            return {"success": False, "error": f"Failed to get source branch: {response.text[:500]}"}

        sha = response.json()["object"]["sha"]

        # Create new branch
        url = f"{self.config.api_base}/repos/{owner}/{repo}/git/refs"
        data = {
            "ref": f"refs/heads/{branch_name}",
            "sha": sha
        }
        response = self.session.post(url, json=data)

        if response.status_code not in (200, 201):
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    # ─── File Operations ──────────────────────────────────────────────────

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> Dict[str, Any]:
        """Get file content from repository"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": ref}
        response = self.session.get(url, params=params)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        data = response.json()
        import base64
        content = base64.b64decode(data.get("content", "")).decode("utf-8")

        return {
            "success": True,
            "content": content,
            "sha": data.get("sha"),
            "size": data.get("size"),
        }

    def create_or_update_file(self, owner: str, repo: str, path: str, content: str,
                              message: str, branch: str = "main", sha: Optional[str] = None) -> Dict[str, Any]:
        """Create or update a file in repository"""
        self._check_token()
        import base64

        url = f"{self.config.api_base}/repos/{owner}/{repo}/contents/{path}"

        data = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }

        if sha:
            data["sha"] = sha

        response = self.session.put(url, json=data)

        if response.status_code not in (200, 201):
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def delete_file(self, owner: str, repo: str, path: str, message: str,
                    sha: str, branch: str = "main") -> Dict[str, Any]:
        """Delete a file from repository"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/contents/{path}"

        data = {
            "message": message,
            "sha": sha,
            "branch": branch,
        }

        response = self.session.delete(url, json=data)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    # ─── Pull Request Operations ──────────────────────────────────────────

    def list_pull_requests(self, owner: str, repo: str, state: str = "open",
                           sort: str = "created", direction: str = "desc", per_page: int = 30) -> Dict[str, Any]:
        """List pull requests"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/pulls"
        params = {"state": state, "sort": sort, "direction": direction, "per_page": per_page}
        response = self.session.get(url, params=params)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def get_pull_request(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """Get a specific pull request"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/pulls/{pull_number}"
        response = self.session.get(url)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def create_pull_request(self, owner: str, repo: str, title: str, body: str,
                            head: str, base: str, draft: bool = False) -> Dict[str, Any]:
        """Create a pull request"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/pulls"

        data = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft,
        }

        response = self.session.post(url, json=data)

        if response.status_code not in (200, 201):
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def update_pull_request(self, owner: str, repo: str, pull_number: int,
                            title: Optional[str] = None, body: Optional[str] = None,
                            state: Optional[str] = None) -> Dict[str, Any]:
        """Update a pull request"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/pulls/{pull_number}"

        data = {}
        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if state is not None:
            data["state"] = state

        response = self.session.patch(url, json=data)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def merge_pull_request(self, owner: str, repo: str, pull_number: int,
                           commit_title: Optional[str] = None, merge_method: str = "merge") -> Dict[str, Any]:
        """Merge a pull request"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/pulls/{pull_number}/merge"

        data = {"merge_method": merge_method}
        if commit_title:
            data["commit_title"] = commit_title

        response = self.session.put(url, json=data)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def add_pr_comment(self, owner: str, repo: str, pull_number: int, body: str) -> Dict[str, Any]:
        """Add a comment to a pull request"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/issues/{pull_number}/comments"

        data = {"body": body}
        response = self.session.post(url, json=data)

        if response.status_code not in (200, 201):
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def request_reviewers(self, owner: str, repo: str, pull_number: int,
                          reviewers: List[str]) -> Dict[str, Any]:
        """Request reviewers for a pull request"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers"

        data = {"reviewers": reviewers}
        response = self.session.post(url, json=data)

        if response.status_code not in (200, 201):
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    # ─── Issue Operations ─────────────────────────────────────────────────

    def list_issues(self, owner: str, repo: str, state: str = "open",
                    sort: str = "created", direction: str = "desc", per_page: int = 30) -> Dict[str, Any]:
        """List issues"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/issues"
        params = {"state": state, "sort": sort, "direction": direction, "per_page": per_page}
        response = self.session.get(url, params=params)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def get_issue(self, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        """Get a specific issue"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/issues/{issue_number}"
        response = self.session.get(url)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def create_issue(self, owner: str, repo: str, title: str, body: str,
                     labels: List[str] = [], assignees: List[str] = []) -> Dict[str, Any]:
        """Create an issue"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/issues"

        data = {
            "title": title,
            "body": body,
            "labels": labels,
            "assignees": assignees,
        }

        response = self.session.post(url, json=data)

        if response.status_code not in (200, 201):
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def add_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> Dict[str, Any]:
        """Add a comment to an issue"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/issues/{issue_number}/comments"

        data = {"body": body}
        response = self.session.post(url, json=data)

        if response.status_code not in (200, 201):
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def close_issue(self, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        """Close an issue"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/issues/{issue_number}"

        data = {"state": "closed"}
        response = self.session.patch(url, json=data)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    # ─── Commit Operations ────────────────────────────────────────────────

    def list_commits(self, owner: str, repo: str, sha: str = "main",
                     per_page: int = 30) -> Dict[str, Any]:
        """List commits"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/commits"
        params = {"sha": sha, "per_page": per_page}
        response = self.session.get(url, params=params)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def get_commit(self, owner: str, repo: str, commit_sha: str) -> Dict[str, Any]:
        """Get a specific commit"""
        self._check_token()
        url = f"{self.config.api_base}/repos/{owner}/{repo}/commits/{commit_sha}"
        response = self.session.get(url)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    # ─── Search Operations ────────────────────────────────────────────────

    def search_code(self, query: str, owner: Optional[str] = None,
                    repo: Optional[str] = None, per_page: int = 30) -> Dict[str, Any]:
        """Search code in repositories"""
        self._check_token()
        url = f"{self.config.api_base}/search/code"

        search_query = query
        if owner and repo:
            search_query = f"{query} repo:{owner}/{repo}"

        params = {"q": search_query, "per_page": per_page}
        response = self.session.get(url, params=params)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def search_issues(self, query: str, owner: Optional[str] = None,
                      repo: Optional[str] = None, per_page: int = 30) -> Dict[str, Any]:
        """Search issues"""
        self._check_token()
        url = f"{self.config.api_base}/search/issues"

        search_query = query
        if owner and repo:
            search_query = f"{query} repo:{owner}/{repo}"

        params = {"q": search_query, "per_page": per_page}
        response = self.session.get(url, params=params)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    # ─── Auto PR Generation ───────────────────────────────────────────────

    def auto_create_pr(self, owner: str, repo: str,
                       feature_branch: str, base_branch: str = "main",
                       title: Optional[str] = None, body: Optional[str] = None,
                       auto_merge: bool = False) -> Dict[str, Any]:
        """
        Automatically create a Pull Request with smart defaults.

        This method:
        1. Creates the branch if it doesn't exist
        2. Generates PR title from branch name if not provided
        3. Generates PR body from commits if not provided
        4. Creates the PR
        5. Optionally auto-merges
        """
        self._check_token()

        # Check if branch exists
        branches_result = self.list_branches(owner, repo)
        if not branches_result.get("success"):
            return branches_result

        branch_names = [b["name"] for b in branches_result.get("data", [])]

        if feature_branch not in branch_names:
            # Create branch
            create_result = self.create_branch(owner, repo, feature_branch, base_branch)
            if not create_result.get("success"):
                return create_result

        # Generate title from branch name if not provided
        if not title:
            # Convert branch name to title: feature/add-login -> Add Login
            title = feature_branch.replace("-", " ").replace("_", " ").title()
            if "/" in title:
                title = title.split("/")[-1]

        # Generate body from commits if not provided
        if not body:
            commits_result = self.list_commits(owner, repo, sha=feature_branch, per_page=10)
            if commits_result.get("success"):
                commits = commits_result.get("data", [])
                commit_messages = [c["commit"]["message"].split("\n")[0] for c in commits[:5]]
                body = "## Changes\n\n" + "\n".join(f"- {msg}" for msg in commit_messages)
                body += "\n\n---\n*Auto-generated by Codex-Local*"
            else:
                body = "*Auto-generated by Codex-Local*"

        # Create PR
        pr_result = self.create_pull_request(
            owner=owner,
            repo=repo,
            title=title,
            body=body,
            head=feature_branch,
            base=base_branch,
        )

        if not pr_result.get("success"):
            return pr_result

        result = {"success": True, "pr": pr_result.get("data")}

        # Auto-merge if requested
        if auto_merge:
            pr_number = pr_result["data"]["number"]
            merge_result = self.merge_pull_request(owner, repo, pr_number)
            result["merged"] = merge_result.get("success", False)
            if not merge_result.get("success"):
                result["merge_error"] = merge_result.get("error")

        return result

    def auto_fix_and_pr(self, owner: str, repo: str, issue_number: int,
                        fix_description: str, auto_merge: bool = False) -> Dict[str, Any]:
        """
        Automatically create a fix for an issue and create a PR.

        This method:
        1. Gets the issue details
        2. Creates a branch named fix/issue-{number}
        3. Creates the PR with issue reference
        4. Links the PR to the issue
        """
        self._check_token()

        # Get issue details
        issue_result = self.get_issue(owner, repo, issue_number)
        if not issue_result.get("success"):
            return issue_result

        issue = issue_result["data"]
        issue_title = issue["title"]

        # Create branch name
        branch_name = f"fix/issue-{issue_number}"

        # Create branch
        branch_result = self.create_branch(owner, repo, branch_name)
        if not branch_result.get("success"):
            return branch_result

        # Create PR
        title = f"Fix #{issue_number}: {issue_title}"
        body = f"""## Fix for Issue #{issue_number}

**Issue:** {issue_title}

**Description:**
{fix_description}

**Changes:**
- Addressed the issue described in #{issue_number}

---
*Auto-generated by Codex-Local*
*Closes #{issue_number}*
"""

        pr_result = self.create_pull_request(
            owner=owner,
            repo=repo,
            title=title,
            body=body,
            head=branch_name,
            base="main",
        )

        if not pr_result.get("success"):
            return pr_result

        result = {"success": True, "pr": pr_result.get("data")}

        # Add comment to issue
        pr_number = pr_result["data"]["number"]
        self.add_issue_comment(
            owner, repo, issue_number,
            f"A fix has been proposed in PR #{pr_number}"
        )

        return result

    # ─── Utility Methods ──────────────────────────────────────────────────

    def get_rate_limit(self) -> Dict[str, Any]:
        """Get current rate limit status"""
        self._check_token()
        url = f"{self.config.api_base}/rate_limit"
        response = self.session.get(url)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "data": response.json()}

    def test_connection(self) -> Dict[str, Any]:
        """Test GitHub API connection"""
        self._check_token()
        url = f"{self.config.api_base}/user"
        response = self.session.get(url)

        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

        return {"success": True, "user": response.json().get("login")}


# ─── Tool Definitions ─────────────────────────────────────────────────────

GITHUB_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "GitHubClone",
            "description": "Clone a GitHub repository to local path",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "description": "Repository URL"},
                    "local_path": {"type": "string", "description": "Local path to clone to"},
                    "depth": {"type": "integer", "description": "Clone depth (0 for full clone)", "default": 1},
                },
                "required": ["repo_url", "local_path"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubGetRepo",
            "description": "Get repository information",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                },
                "required": ["owner", "repo"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubListBranches",
            "description": "List branches in a repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                },
                "required": ["owner", "repo"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubCreateBranch",
            "description": "Create a new branch",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "branch_name": {"type": "string", "description": "New branch name"},
                    "from_branch": {"type": "string", "description": "Source branch", "default": "main"},
                },
                "required": ["owner", "repo", "branch_name"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubGetFile",
            "description": "Get file content from repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "path": {"type": "string", "description": "File path"},
                    "ref": {"type": "string", "description": "Branch or commit SHA", "default": "main"},
                },
                "required": ["owner", "repo", "path"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubCreateFile",
            "description": "Create or update a file in repository",
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
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubListPRs",
            "description": "List pull requests",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "state": {"type": "string", "description": "PR state (open/closed/all)", "default": "open"},
                },
                "required": ["owner", "repo"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubCreatePR",
            "description": "Create a pull request",
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
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubAutoCreatePR",
            "description": "Automatically create a PR with smart defaults",
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
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubMergePR",
            "description": "Merge a pull request",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "pull_number": {"type": "integer", "description": "PR number"},
                    "merge_method": {"type": "string", "description": "Merge method (merge/squash/rebase)", "default": "merge"},
                },
                "required": ["owner", "repo", "pull_number"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubListIssues",
            "description": "List issues",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "state": {"type": "string", "description": "Issue state (open/closed/all)", "default": "open"},
                },
                "required": ["owner", "repo"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubCreateIssue",
            "description": "Create an issue",
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
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubSearchCode",
            "description": "Search code in repositories",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                },
                "required": ["query"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "GitHubRateLimit",
            "description": "Get current rate limit status",
            "parameters": {
                "type": "object",
                "properties": {},
            }
        }
    },
]


# ─── Singleton Instance ───────────────────────────────────────────────────

_github_instance: Optional[GitHubIntegration] = None


def get_github(config: Optional[GitHubConfig] = None) -> GitHubIntegration:
    """Get or create singleton GitHub integration instance"""
    global _github_instance
    if _github_instance is None:
        _github_instance = GitHubIntegration(config)
    return _github_instance


if __name__ == "__main__":
    # Test connection
    github = get_github()
    result = github.test_connection()
    print(json.dumps(result, indent=2))
