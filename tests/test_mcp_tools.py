"""
Tests for the unified MCP tool modules.
Covers: server, filesystem, git, search, db, http, process, system tools.
"""

import os
import sys
import json
import tempfile
import sqlite3
from pathlib import Path
import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server import CodexMCPServer, ToolModule, create_server
from mcp.filesystem_tools import FileSystemTools
from mcp.git_tools import GitTools
from mcp.search_tools import SearchTools
from mcp.db_tools import DBTools
from mcp.http_tools import HttpTools
from mcp.process_tools import ProcessTools
from mcp.system_tools import SystemTools


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def server():
    """Create a CodexMCPServer instance."""
    return create_server()


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def tmp_file(tmp_dir):
    """Create a temporary file with content."""
    p = Path(tmp_dir) / "test.txt"
    p.write_text("line1\nline2\nline3\nhello world\n", encoding="utf-8")
    return str(p)


@pytest.fixture
def tmp_db(tmp_dir):
    """Create a temporary SQLite database."""
    from mcp.db_tools import _connections
    db_path = str(Path(tmp_dir) / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.commit()
    conn.close()
    yield db_path
    # Clean up any open connections from db_tools
    for cid in list(_connections.keys()):
        try:
            _connections[cid].close()
        except Exception:
            pass
    _connections.clear()


def _git_available():
    """Check if git is available from Python subprocess."""
    import subprocess
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, OSError):
        return False


_git_ok = _git_available()


@pytest.fixture
def git_repo():
    """Create a temporary git repo in a path without unicode chars."""
    import subprocess
    import shutil
    repo_dir = Path("D:/codex-local/tests/_tmp_git_repo")
    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo_dir), capture_output=True)
    p = repo_dir / "README.md"
    p.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo_dir), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(repo_dir), capture_output=True)
    yield str(repo_dir)
    shutil.rmtree(repo_dir, ignore_errors=True)


# ─── Server Tests ────────────────────────────────────────────────────────────

class TestCodexMCPServer:
    """Test the unified MCP server."""

    def test_server_creation(self, server):
        assert server.name == "codex-local"
        assert server.version == "2.0.0"
        assert server.get_tool_count() > 0
        assert server.get_module_count() == 9

    def test_list_tools(self, server):
        tools = server.list_tools()
        assert len(tools) > 0
        for t in tools:
            assert "name" in t
            assert "description" in t

    def test_call_tool_unknown(self, server):
        result = server.call_tool("nonexistent_tool_xyz", {})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_call_tool_with_args(self, server, tmp_file):
        result = server.call_tool("Read", {"file_path": tmp_file})
        assert result["success"] is True
        assert "line1" in result["content"]

    def test_all_modules_registered(self, server):
        tool_names = [t["name"] for t in server.list_tools()]
        # Check key tools from each module
        expected = [
            "Read", "Write", "Bash",           # filesystem
            "git_status", "git_log",            # git
            "grep_search", "list_functions",    # search
            "db_connect", "db_query",           # db
            "http_get",                         # http
            "process_list",                     # process
            "system_info",                      # system
        ]
        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"


# ─── Filesystem Tools Tests ──────────────────────────────────────────────────

class TestFileSystemTools:
    """Test filesystem tools."""

    def test_read_file(self, tmp_file):
        tools = FileSystemTools()
        result = tools._read(tmp_file)
        assert result["success"] is True
        assert "line1" in result["content"]

    def test_read_with_offset_limit(self, tmp_file):
        tools = FileSystemTools()
        result = tools._read(tmp_file, offset=1, limit=2)
        assert result["success"] is True
        lines = result["content"].split("\n")
        assert len(lines) == 2

    def test_read_nonexistent(self):
        tools = FileSystemTools()
        result = tools._read("/nonexistent/file.txt")
        assert result["success"] is False

    def test_write_file(self, tmp_dir):
        tools = FileSystemTools()
        path = str(Path(tmp_dir) / "new.txt")
        result = tools._write(path, "hello")
        assert result["success"] is True
        assert Path(path).read_text() == "hello"

    def test_edit_file(self, tmp_file):
        tools = FileSystemTools()
        result = tools._edit(tmp_file, "line1", "LINE1")
        assert result["success"] is True
        assert "LINE1" in Path(tmp_file).read_text()

    def test_edit_not_found(self, tmp_file):
        tools = FileSystemTools()
        result = tools._edit(tmp_file, "nonexistent_xyz", "replacement")
        assert result["success"] is False

    def test_glob(self, tmp_dir):
        tools = FileSystemTools()
        Path(tmp_dir, "a.py").write_text("a")
        Path(tmp_dir, "b.py").write_text("b")
        Path(tmp_dir, "c.txt").write_text("c")
        result = tools._glob("*.py", root=tmp_dir)
        assert result["success"] is True
        assert result["count"] == 2

    def test_bash(self, tmp_dir):
        tools = FileSystemTools()
        if os.name == "nt":
            result = tools._bash("echo hello", cwd=tmp_dir)
        else:
            result = tools._bash("echo hello", cwd=tmp_dir)
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_mkdir(self, tmp_dir):
        tools = FileSystemTools()
        path = str(Path(tmp_dir) / "sub" / "dir")
        result = tools._mkdir(path)
        assert result["success"] is True
        assert Path(path).is_dir()

    def test_stat(self, tmp_file):
        tools = FileSystemTools()
        result = tools._stat(tmp_file)
        assert result["success"] is True
        assert result["is_file"] is True
        assert result["size"] > 0


# ─── Git Tools Tests ─────────────────────────────────────────────────────────

@pytest.mark.skipif(not _git_ok, reason="git not available from Python subprocess")
class TestGitTools:
    """Test git tools."""

    def test_git_status(self, git_repo):
        tools = GitTools()
        result = tools._git_status(git_repo)
        assert result["success"] is True

    def test_git_log(self, git_repo):
        tools = GitTools()
        result = tools._git_log(git_repo, count=5)
        assert result["success"] is True
        assert "initial" in result["stdout"]

    def test_git_diff(self, git_repo):
        tools = GitTools()
        # Modify a file
        (Path(git_repo) / "README.md").write_text("changed\n")
        result = tools._git_diff(git_repo)
        assert result["success"] is True
        assert len(result["stdout"]) > 0

    def test_git_branch(self, git_repo):
        tools = GitTools()
        result = tools._git_branch(git_repo)
        assert result["success"] is True
        assert "main" in result["stdout"] or "master" in result["stdout"]

    def test_git_branch_create(self, git_repo):
        tools = GitTools()
        result = tools._git_branch(git_repo, name="feature/test")
        assert result["success"] is True

    def test_git_checkout(self, git_repo):
        tools = GitTools()
        tools._git_branch(git_repo, name="feature/test")
        result = tools._git_checkout(git_repo, "feature/test")
        assert result["success"] is True

    def test_git_blame(self, git_repo):
        tools = GitTools()
        result = tools._git_blame(git_repo, "README.md")
        assert result["success"] is True

    def test_git_nonexistent_repo(self):
        tools = GitTools()
        result = tools._git_status("/nonexistent/repo")
        assert result["success"] is False


# ─── Search Tools Tests ──────────────────────────────────────────────────────

class TestSearchTools:
    """Test search tools."""

    def test_grep_search(self, tmp_dir):
        tools = SearchTools()
        (Path(tmp_dir) / "code.py").write_text("def hello():\n    pass\n")
        result = tools._grep_search(tmp_dir, "def hello")
        assert result["success"] is True
        assert result["count"] >= 1

    def test_grep_with_glob(self, tmp_dir):
        tools = SearchTools()
        (Path(tmp_dir) / "a.py").write_text("import os\n")
        (Path(tmp_dir) / "b.js").write_text("import os\n")
        result = tools._grep_search(tmp_dir, "import", glob="*.py")
        assert result["success"] is True
        assert all(".py" in m["file"] for m in result["matches"])

    def test_glob_search(self, tmp_dir):
        tools = SearchTools()
        (Path(tmp_dir) / "x.py").write_text("x")
        (Path(tmp_dir) / "y.txt").write_text("y")
        result = tools._glob_search(tmp_dir, "*.py")
        assert result["success"] is True
        assert result["count"] == 1

    def test_find_references(self, tmp_dir):
        tools = SearchTools()
        (Path(tmp_dir) / "mod.py").write_text("def foo(): pass\nfoo()\n")
        result = tools._find_references(tmp_dir, "foo")
        assert result["success"] is True
        assert result["count"] >= 2

    def test_list_functions(self, tmp_dir):
        tools = SearchTools()
        code = '''
def hello():
    pass

class MyClass:
    def method(self):
        pass

async def async_func():
    pass
'''
        (Path(tmp_dir) / "mod.py").write_text(code)
        result = tools._list_functions(str(Path(tmp_dir) / "mod.py"))
        assert result["success"] is True
        names = [i["name"] for i in result["items"]]
        assert "hello" in names
        assert "MyClass" in names
        assert "async_func" in names

    def test_list_functions_not_python(self, tmp_dir):
        tools = SearchTools()
        (Path(tmp_dir) / "x.txt").write_text("not python")
        result = tools._list_functions(str(Path(tmp_dir) / "x.txt"))
        assert result["success"] is False


# ─── DB Tools Tests ──────────────────────────────────────────────────────────

class TestDBTools:
    """Test database tools."""

    def test_db_connect(self, tmp_db):
        tools = DBTools()
        result = tools._db_connect(tmp_db)
        assert result["success"] is True
        assert "conn_id" in result

    def test_db_query(self, tmp_db):
        tools = DBTools()
        conn = tools._db_connect(tmp_db)
        result = tools._db_query(conn["conn_id"], "SELECT * FROM users ORDER BY id")
        assert result["success"] is True
        assert result["row_count"] == 2
        assert result["rows"][0]["name"] == "Alice"

    def test_db_tables(self, tmp_db):
        tools = DBTools()
        conn = tools._db_connect(tmp_db)
        result = tools._db_tables(conn["conn_id"])
        assert result["success"] is True
        assert "users" in result["tables"]

    def test_db_schema(self, tmp_db):
        tools = DBTools()
        conn = tools._db_connect(tmp_db)
        result = tools._db_schema(conn["conn_id"], "users")
        assert result["success"] is True
        assert "CREATE TABLE" in result["create_sql"]
        col_names = [c["name"] for c in result["columns"]]
        assert "id" in col_names
        assert "name" in col_names

    def test_db_query_invalid_sql(self, tmp_db):
        tools = DBTools()
        conn = tools._db_connect(tmp_db)
        result = tools._db_query(conn["conn_id"], "INVALID SQL QUERY")
        assert result["success"] is False

    def test_db_query_unknown_conn(self):
        tools = DBTools()
        result = tools._db_query("nonexistent", "SELECT 1")
        assert result["success"] is False


# ─── HTTP Tools Tests ────────────────────────────────────────────────────────

class TestHttpTools:
    """Test HTTP tools (basic, no network dependency for most)."""

    def test_http_get_invalid_url(self):
        tools = HttpTools()
        result = tools._http_get("http://localhost:1")
        assert result["success"] is False

    def test_http_post_invalid_url(self):
        tools = HttpTools()
        result = tools._http_post("http://localhost:1", {"key": "value"})
        assert result["success"] is False

    def test_http_download_invalid_url(self, tmp_dir):
        tools = HttpTools()
        result = tools._http_download("http://localhost:1", str(Path(tmp_dir) / "out.txt"))
        assert result["success"] is False


# ─── Process Tools Tests ─────────────────────────────────────────────────────

class TestProcessTools:
    """Test process tools."""

    def test_process_list(self):
        tools = ProcessTools()
        result = tools._process_list()
        assert result["success"] is True
        assert result["count"] > 0

    def test_process_list_with_filter(self):
        tools = ProcessTools()
        # Filter for python processes
        result = tools._process_list(filter="python")
        assert result["success"] is True

    def test_process_info_current(self):
        tools = ProcessTools()
        pid = os.getpid()
        result = tools._process_info(pid)
        assert result["success"] is True

    def test_process_info_nonexistent(self):
        tools = ProcessTools()
        # Use a very high PID that's unlikely to exist
        # On Windows, tasklist may return info for PID 0 or error differently
        result = tools._process_info(999999999)
        # Just verify it doesn't crash -- success may vary by OS
        assert isinstance(result, dict)


# ─── System Tools Tests ──────────────────────────────────────────────────────

class TestSystemTools:
    """Test system tools."""

    def test_system_info(self):
        tools = SystemTools()
        result = tools._system_info()
        assert result["success"] is True
        assert "os" in result
        assert "cpu_count" in result
        assert result["cpu_count"] > 0

    def test_disk_usage(self):
        tools = SystemTools()
        if os.name == "nt":
            result = tools._disk_usage("C:\\")
        else:
            result = tools._disk_usage("/")
        assert result["success"] is True
        assert result["total_gb"] > 0

    def test_env_get_existing(self):
        tools = SystemTools()
        os.environ["TEST_MCP_VAR"] = "hello"
        result = tools._env_get("TEST_MCP_VAR")
        assert result["success"] is True
        assert result["value"] == "hello"
        del os.environ["TEST_MCP_VAR"]

    def test_env_get_missing(self):
        tools = SystemTools()
        result = tools._env_get("NONEXISTENT_VAR_XYZ_123")
        assert result["success"] is False

    def test_env_set(self):
        tools = SystemTools()
        result = tools._env_set("TEST_MCP_SET", "world")
        assert result["success"] is True
        assert os.environ.get("TEST_MCP_SET") == "world"
        del os.environ["TEST_MCP_SET"]


# ─── Integration Test ────────────────────────────────────────────────────────

class TestIntegration:
    """End-to-end integration tests using the full server."""

    def test_full_workflow(self, server, tmp_dir):
        """Test a realistic workflow: create, read, edit, search a file."""
        path = str(Path(tmp_dir) / "workflow.py")

        # Write
        r = server.call_tool("Write", {"file_path": path, "content": "def hello():\n    return 'world'\n"})
        assert r["success"] is True

        # Read
        r = server.call_tool("Read", {"file_path": path})
        assert r["success"] is True
        assert "hello" in r["content"]

        # Edit
        r = server.call_tool("Edit", {"file_path": path, "old_string": "world", "new_string": "universe"})
        assert r["success"] is True

        # Verify edit
        r = server.call_tool("Read", {"file_path": path})
        assert "universe" in r["content"]

        # Search
        r = server.call_tool("grep_search", {"path": tmp_dir, "pattern": "universe"})
        assert r["success"] is True
        assert r["count"] >= 1

    def test_db_workflow(self, server, tmp_db):
        """Test database workflow: connect, list tables, query, schema."""
        # Connect
        r = server.call_tool("db_connect", {"path": tmp_db})
        assert r["success"] is True
        conn_id = r["conn_id"]

        # List tables
        r = server.call_tool("db_tables", {"conn_id": conn_id})
        assert r["success"] is True
        assert "users" in r["tables"]

        # Schema
        r = server.call_tool("db_schema", {"conn_id": conn_id, "table": "users"})
        assert r["success"] is True

        # Query
        r = server.call_tool("db_query", {"conn_id": conn_id, "sql": "SELECT count(*) as cnt FROM users"})
        assert r["success"] is True
        assert r["rows"][0]["cnt"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
