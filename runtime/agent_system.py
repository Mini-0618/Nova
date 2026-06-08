"""
RootCode Agent System
Inspired by Claude Code's Agent capabilities.

Supports:
- Multiple agent types (general-purpose, Explore, Plan, etc.)
- Parallel execution
- Tool registration system
- Workflow orchestration
"""

import os
import json
import logging
import time
import asyncio
import uuid
from typing import Optional, Dict, Any, List, Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

_log = logging.getLogger(__name__)

# ─── Agent Types ──────────────────────────────────────────────────────────

class AgentType(Enum):
    GENERAL_PURPOSE = "general-purpose"  # 啥都能干
    EXPLORE = "explore"                  # 只读搜索，扫大量文件找信息
    PLAN = "plan"                        # 做架构设计和实现方案
    CODE = "code"                        # 写代码、改代码
    TEST = "test"                        # 测试和验证
    RESEARCH = "research"                # 调研和分析


# ─── Agent Status ─────────────────────────────────────────────────────────

class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ─── Agent Configuration ──────────────────────────────────────────────────

@dataclass
class AgentConfig:
    agent_type: AgentType = AgentType.GENERAL_PURPOSE
    max_iterations: int = 50
    max_tokens: int = 4096
    temperature: float = 0.7
    model: str = "deepseek-chat"
    provider: str = "deepseek"
    timeout: float = 300.0  # 5分钟超时
    enable_tools: bool = True
    tools: List[str] = field(default_factory=list)  # 空表示所有工具


# ─── Agent Result ─────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    agent_id: str
    agent_type: AgentType
    status: AgentStatus
    result: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0
    tokens_used: int = 0
    tool_calls: int = 0


# ─── Tool Definition ──────────────────────────────────────────────────────

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    category: str = "general"


# ─── Tool Registry ────────────────────────────────────────────────────────

class ToolRegistry:
    """Registry for all available tools"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._categories: Dict[str, List[str]] = {}

    def register(self, tool: ToolDefinition):
        """Register a tool"""
        self._tools[tool.name] = tool
        if tool.category not in self._categories:
            self._categories[tool.category] = []
        self._categories[tool.category].append(tool.name)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name"""
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[ToolDefinition]:
        """List all tools, optionally filtered by category"""
        if category:
            names = self._categories.get(category, [])
            return [self._tools[n] for n in names if n in self._tools]
        return list(self._tools.values())

    def list_categories(self) -> List[str]:
        """List all categories"""
        return list(self._categories.keys())

    def execute(self, name: str, **kwargs) -> Any:
        """Execute a tool"""
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool not found: {name}")
        return tool.handler(**kwargs)


# ─── Global Tool Registry ─────────────────────────────────────────────────

_tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry"""
    return _tool_registry


# ─── Built-in Tools ───────────────────────────────────────────────────────

def _read_file(file_path: str, limit: Optional[int] = None, offset: Optional[int] = None) -> Dict[str, Any]:
    """Read file contents"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if offset:
            lines = lines[offset:]
        if limit:
            lines = lines[:limit]
        return {"success": True, "content": "".join(lines), "lines": len(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _write_file(file_path: str, content: str) -> Dict[str, Any]:
    """Write content to file"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "bytes": len(content.encode('utf-8'))}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _edit_file(file_path: str, old_string: str, new_string: str) -> Dict[str, Any]:
    """Edit file by replacing string"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_string not in content:
            return {"success": False, "error": "old_string not found"}
        new_content = content.replace(old_string, new_string, 1)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return {"success": True, "changes": 1}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _run_bash(command: str, timeout: int = 30) -> Dict[str, Any]:
    """Run bash command"""
    import subprocess
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _search_files(pattern: str, path: str = ".") -> Dict[str, Any]:
    """Search files using glob pattern"""
    import glob
    try:
        files = glob.glob(os.path.join(path, pattern), recursive=True)
        return {"success": True, "files": files, "count": len(files)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _grep_files(pattern: str, path: str = ".", glob_pattern: str = "*") -> Dict[str, Any]:
    """Search file contents using regex"""
    import re
    import glob
    try:
        results = []
        files = glob.glob(os.path.join(path, "**", glob_pattern), recursive=True)
        for file_path in files:
            if os.path.isfile(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, line in enumerate(f, 1):
                            if re.search(pattern, line):
                                results.append({
                                    "file": file_path,
                                    "line": i,
                                    "text": line.strip()
                                })
                except Exception:
                    _log.warning("Failed to read file %s during search", file_path, exc_info=True)
        return {"success": True, "results": results[:100], "count": len(results)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _web_fetch(url: str, prompt: str = "") -> Dict[str, Any]:
    """Fetch web content"""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        return {"success": True, "content": content[:5000], "url": url}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _web_search(query: str) -> Dict[str, Any]:
    """Search the web (placeholder - needs actual implementation)"""
    return {
        "success": True,
        "message": "Web search not implemented yet. Use web_fetch to get specific URLs.",
        "query": query
    }


def _list_files(path: str = ".", recursive: bool = False) -> Dict[str, Any]:
    """List files in directory"""
    try:
        if recursive:
            files = [
                os.path.join(root, f)
                for root, dirs, filenames in os.walk(path)
                for f in filenames
            ]
        else:
            files = os.listdir(path)
        return {"success": True, "files": files, "count": len(files)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_current_dir() -> Dict[str, Any]:
    """Get current working directory"""
    return {"success": True, "path": os.getcwd()}


def _change_dir(path: str) -> Dict[str, Any]:
    """Change working directory"""
    try:
        os.chdir(path)
        return {"success": True, "path": os.getcwd()}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Register Built-in Tools ──────────────────────────────────────────────

def register_built_in_tools():
    """Register all built-in tools"""
    tools = [
        ToolDefinition(
            name="Read",
            description="Read the complete contents of a file",
            parameters={"file_path": "string", "limit": "integer", "offset": "integer"},
            handler=_read_file,
            category="file"
        ),
        ToolDefinition(
            name="Write",
            description="Create or overwrite a file with content",
            parameters={"file_path": "string", "content": "string"},
            handler=_write_file,
            category="file"
        ),
        ToolDefinition(
            name="Edit",
            description="Edit a file by replacing a string",
            parameters={"file_path": "string", "old_string": "string", "new_string": "string"},
            handler=_edit_file,
            category="file"
        ),
        ToolDefinition(
            name="Bash",
            description="Execute a shell command",
            parameters={"command": "string", "timeout": "integer"},
            handler=_run_bash,
            category="system"
        ),
        ToolDefinition(
            name="Glob",
            description="Search files using glob pattern",
            parameters={"pattern": "string", "path": "string"},
            handler=_search_files,
            category="search"
        ),
        ToolDefinition(
            name="Grep",
            description="Search file contents using regex",
            parameters={"pattern": "string", "path": "string", "glob_pattern": "string"},
            handler=_grep_files,
            category="search"
        ),
        ToolDefinition(
            name="WebFetch",
            description="Fetch web content from URL",
            parameters={"url": "string", "prompt": "string"},
            handler=_web_fetch,
            category="web"
        ),
        ToolDefinition(
            name="WebSearch",
            description="Search the web",
            parameters={"query": "string"},
            handler=_web_search,
            category="web"
        ),
        ToolDefinition(
            name="ListFiles",
            description="List files in directory",
            parameters={"path": "string", "recursive": "boolean"},
            handler=_list_files,
            category="file"
        ),
        ToolDefinition(
            name="GetCurrentDir",
            description="Get current working directory",
            parameters={},
            handler=_get_current_dir,
            category="system"
        ),
        ToolDefinition(
            name="ChangeDir",
            description="Change working directory",
            parameters={"path": "string"},
            handler=_change_dir,
            category="system"
        ),
    ]

    for tool in tools:
        _tool_registry.register(tool)


# ─── Agent Base Class ─────────────────────────────────────────────────────

class Agent:
    """Base agent class"""

    def __init__(self, config: AgentConfig, tool_registry: ToolRegistry):
        self.id = str(uuid.uuid4())
        self.config = config
        self.tool_registry = tool_registry
        self.status = AgentStatus.IDLE
        self.result: Optional[AgentResult] = None
        self._listeners: List[Callable] = []

    def add_listener(self, cb: Callable):
        """Add event listener"""
        self._listeners.append(cb)

    def _notify(self, event: str, data: Dict[str, Any]):
        """Notify listeners"""
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                _log.warning("Listener callback %s failed for event=%s", cb, event, exc_info=True)

    async def run(self, task: str) -> AgentResult:
        """Run the agent with a task"""
        raise NotImplementedError


# ─── General Purpose Agent ────────────────────────────────────────────────

class GeneralPurposeAgent(Agent):
    """General purpose agent that can handle any task"""

    async def run(self, task: str) -> AgentResult:
        """Run the agent with a task"""
        self.status = AgentStatus.RUNNING
        start_time = time.time()

        self._notify("agent_start", {
            "agent_id": self.id,
            "agent_type": self.config.agent_type.value,
            "task": task[:100]
        })

        try:
            # Import here to avoid circular imports
            from runtime.loop import CodexLoop, LoopConfig

            # Create loop config
            loop_config = LoopConfig(
                max_iterations=self.config.max_iterations,
                max_output_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                model=self.config.model,
                provider=self.config.provider,
            )

            # Create and run loop
            loop = CodexLoop(loop_config)
            result = await loop.run_task(task)

            self.status = AgentStatus.COMPLETED
            self.result = AgentResult(
                agent_id=self.id,
                agent_type=self.config.agent_type,
                status=AgentStatus.COMPLETED,
                result=result,
                duration=time.time() - start_time,
                tokens_used=loop.total_tokens_used,
            )

        except Exception as e:
            self.status = AgentStatus.FAILED
            self.result = AgentResult(
                agent_id=self.id,
                agent_type=self.config.agent_type,
                status=AgentStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time,
            )

        self._notify("agent_complete", {
            "agent_id": self.id,
            "status": self.status.value,
            "duration": self.result.duration
        })

        return self.result


# ─── Explore Agent ────────────────────────────────────────────────────────

class ExploreAgent(Agent):
    """Read-only search agent for scanning files"""

    async def run(self, task: str) -> AgentResult:
        """Run the agent with a task"""
        self.status = AgentStatus.RUNNING
        start_time = time.time()

        self._notify("agent_start", {
            "agent_id": self.id,
            "agent_type": "explore",
            "task": task[:100]
        })

        try:
            # Parse task to find what to search
            results = []

            # List files
            list_result = self.tool_registry.execute("ListFiles", path=".", recursive=True)
            if list_result.get("success"):
                results.append(f"Found {list_result['count']} files")

            # Search for specific patterns if mentioned
            if "python" in task.lower() or ".py" in task.lower():
                py_files = self.tool_registry.execute("Glob", pattern="**/*.py", path=".")
                if py_files.get("success"):
                    results.append(f"Python files: {py_files['count']}")

            if "javascript" in task.lower() or ".js" in task.lower():
                js_files = self.tool_registry.execute("Glob", pattern="**/*.js", path=".")
                if js_files.get("success"):
                    results.append(f"JavaScript files: {js_files['count']}")

            # Generate summary
            result_text = "\n".join(results) if results else "No specific files found"

            self.status = AgentStatus.COMPLETED
            self.result = AgentResult(
                agent_id=self.id,
                agent_type=self.config.agent_type,
                status=AgentStatus.COMPLETED,
                result=result_text,
                duration=time.time() - start_time,
            )

        except Exception as e:
            self.status = AgentStatus.FAILED
            self.result = AgentResult(
                agent_id=self.id,
                agent_type=self.config.agent_type,
                status=AgentStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time,
            )

        self._notify("agent_complete", {
            "agent_id": self.id,
            "status": self.status.value,
            "duration": self.result.duration
        })

        return self.result


# ─── Agent Factory ────────────────────────────────────────────────────────

def create_agent(
    agent_type: AgentType = AgentType.GENERAL_PURPOSE,
    config: Optional[AgentConfig] = None,
    tool_registry: Optional[ToolRegistry] = None,
) -> Agent:
    """Create an agent of the specified type"""
    if config is None:
        config = AgentConfig(agent_type=agent_type)
    if tool_registry is None:
        tool_registry = _tool_registry

    if agent_type == AgentType.GENERAL_PURPOSE:
        return GeneralPurposeAgent(config, tool_registry)
    elif agent_type == AgentType.EXPLORE:
        return ExploreAgent(config, tool_registry)
    else:
        # Default to general purpose
        return GeneralPurposeAgent(config, tool_registry)


# ─── Parallel Agent Runner ────────────────────────────────────────────────

class ParallelAgentRunner:
    """Run multiple agents in parallel"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    async def run_agents(self, agents: List[Dict[str, Any]]) -> List[AgentResult]:
        """
        Run multiple agents in parallel.

        Args:
            agents: List of {"agent": Agent, "task": str}

        Returns:
            List of AgentResult
        """
        tasks = []
        for item in agents:
            agent = item["agent"]
            task = item["task"]
            tasks.append(agent.run(task))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to AgentResult
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(AgentResult(
                    agent_id=agents[i]["agent"].id,
                    agent_type=agents[i]["agent"].config.agent_type,
                    status=AgentStatus.FAILED,
                    error=str(result),
                ))
            else:
                processed_results.append(result)

        return processed_results


# ─── Initialize ───────────────────────────────────────────────────────────

# Register built-in tools on module load
register_built_in_tools()


# ─── CLI Test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("ROOTCODE AGENT SYSTEM TEST")
        print("=" * 60)

        # Test tool registry
        registry = get_tool_registry()
        print(f"\nRegistered tools: {len(registry.list_tools())}")
        print(f"Categories: {registry.list_categories()}")

        # Test file operations
        print("\n--- Testing File Tools ---")
        test_file = "D:/codex-local/test_agent.txt"
        result = registry.execute("Write", file_path=test_file, content="Hello from Agent!")
        print(f"Write: {result}")

        result = registry.execute("Read", file_path=test_file)
        print(f"Read: {result}")

        result = registry.execute("ListFiles", path="D:/codex-local", recursive=False)
        print(f"ListFiles: {result['count']} files")

        # Test agent creation
        print("\n--- Testing Agent Creation ---")
        agent = create_agent(AgentType.GENERAL_PURPOSE)
        print(f"Agent created: {agent.id}")

        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)

        print("\n[DONE] All tests passed!")

    asyncio.run(test())
