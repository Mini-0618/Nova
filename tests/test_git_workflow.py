"""Tests for runtime.git_workflow module."""

from unittest.mock import patch, MagicMock

from runtime.git_workflow import (
    _run_git,
    auto_commit,
    auto_branch,
    diff_summary,
    rollback,
    current_branch,
    log,
)


def _make_result(returncode=0, stdout="", stderr=""):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


class TestRunGit:
    @patch("runtime.git_workflow.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = _make_result(0, "ok", "")
        result = _run_git(["status"])
        assert result["success"] is True
        assert result["output"] == "ok"
        assert result["error"] is None

    @patch("runtime.git_workflow.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = _make_result(1, "", "fatal: not a repo")
        result = _run_git(["status"])
        assert result["success"] is False
        assert "fatal" in result["error"]

    @patch("runtime.git_workflow.subprocess.run", side_effect=FileNotFoundError)
    def test_git_not_found(self, mock_run):
        result = _run_git(["status"])
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("runtime.git_workflow.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        result = _run_git(["status"])
        assert result["success"] is False
        assert "timed out" in result["error"]


class TestAutoCommit:
    @patch("runtime.git_workflow._run_git")
    def test_success(self, mock_git):
        mock_git.return_value = {"success": True, "output": "ok", "error": None}
        result = auto_commit("test msg")
        assert result["success"] is True
        assert mock_git.call_count == 2  # add + commit

    @patch("runtime.git_workflow._run_git")
    def test_add_fails(self, mock_git):
        mock_git.return_value = {"success": False, "output": "", "error": "fail"}
        result = auto_commit("msg")
        assert result["success"] is False
        assert "git add failed" in result["error"]


class TestDiffSummary:
    @patch("runtime.git_workflow._run_git")
    def test_parses_numstat(self, mock_git):
        mock_git.side_effect = [
            {"success": True, "output": "file changed", "error": None},
            {"success": True, "output": "10\t5\ta.py\n2\t0\tb.py", "error": None},
        ]
        result = diff_summary()
        assert result["success"] is True
        assert result["output"]["total_additions"] == 12
        assert result["output"]["total_deletions"] == 5
        assert len(result["output"]["files"]) == 2

    @patch("runtime.git_workflow._run_git")
    def test_failure(self, mock_git):
        mock_git.return_value = {"success": False, "output": None, "error": "no repo"}
        result = diff_summary()
        assert result["success"] is False


class TestSimpleWrappers:
    @patch("runtime.git_workflow._run_git")
    def test_auto_branch(self, mock_git):
        mock_git.return_value = {"success": True, "output": "", "error": None}
        result = auto_branch("feature-x")
        assert result["success"] is True
        args = mock_git.call_args[0][0]
        assert "feature-x" in args

    @patch("runtime.git_workflow._run_git")
    def test_rollback(self, mock_git):
        mock_git.return_value = {"success": True, "output": "", "error": None}
        result = rollback()
        assert result["success"] is True
        args = mock_git.call_args[0][0]
        assert "HEAD~1" in args

    @patch("runtime.git_workflow._run_git")
    def test_current_branch(self, mock_git):
        mock_git.return_value = {"success": True, "output": "main", "error": None}
        result = current_branch()
        assert result["output"] == "main"

    @patch("runtime.git_workflow._run_git")
    def test_log(self, mock_git):
        mock_git.return_value = {"success": True, "output": "abc123 msg", "error": None}
        result = log(limit=5)
        assert result["success"] is True
        args = mock_git.call_args[0][0]
        assert "-5" in args
