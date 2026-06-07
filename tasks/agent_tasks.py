"""
RootCode Integration Tasks
Distribute tasks to 4 agents for parallel execution.
Each agent has isolated context to avoid pollution.
"""

import os
import sys
import json
import asyncio
from pathlib import Path

# Add parent directory to path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from runtime.agent_system import (
    create_agent, AgentType, AgentConfig,
    ParallelAgentRunner, get_tool_registry
)


# ─── Task Definitions ─────────────────────────────────────────────────────

TASKS = [
    {
        "id": "mcp_integration",
        "name": "MCP协议集成",
        "agent_type": AgentType.CODE,
        "task": """
任务：从Claude Code的skills目录提取MCP协议实现，集成到RootCode。

步骤：
1. 读取 C:\\Users\\联想\\.claude\\skills\\codex-local-*.md 文件
2. 分析MCP协议的核心概念和实现
3. 在 D:\\codex-local\\mcp\\ 目录下完善MCP服务器实现
4. 添加文件系统、浏览器、数据库等MCP工具
5. 测试MCP服务器是否正常工作

输出：完善的MCP服务器代码和文档
""",
        "config": AgentConfig(
            agent_type=AgentType.CODE,
            max_iterations=30,
            model="deepseek-chat",
            provider="deepseek",
        )
    },
    {
        "id": "sandbox_optimization",
        "name": "沙箱执行优化",
        "agent_type": AgentType.CODE,
        "task": """
任务：从OpenAI Codex的沙箱实现学习，优化RootCode的沙箱执行。

步骤：
1. 分析 C:\\Users\\联想\\.codex\\.sandbox-bin\\ 目录下的沙箱实现
2. 学习Codex的安全沙箱机制
3. 优化 D:\\codex-local\\runtime\\sandbox.py
4. 添加资源限制、超时控制、OOM检测
5. 测试沙箱执行是否正常

输出：优化后的沙箱执行代码
""",
        "config": AgentConfig(
            agent_type=AgentType.CODE,
            max_iterations=30,
            model="deepseek-chat",
            provider="deepseek",
        )
    },
    {
        "id": "memory_system",
        "name": "记忆系统",
        "agent_type": AgentType.CODE,
        "task": """
任务：从MCR项目学习记忆系统，为RootCode添加长期记忆。

步骤：
1. 分析 D:\\AIProjects\\MCR\\ 目录下的记忆系统实现
2. 学习MCR的知识记忆机制
3. 创建 D:\\codex-local\\runtime\\memory.py
4. 实现短期记忆（会话内）和长期记忆（跨会话）
5. 集成到CodexLoop中

输出：完整的记忆系统代码
""",
        "config": AgentConfig(
            agent_type=AgentType.CODE,
            max_iterations=30,
            model="deepseek-chat",
            provider="deepseek",
        )
    },
    {
        "id": "web_ui_enhancement",
        "name": "Web界面完善",
        "agent_type": AgentType.CODE,
        "task": """
任务：从Hermes Web UI学习，完善RootCode的Chatbot界面。

步骤：
1. 分析 C:\\Users\\联想\\hermes-web-ui\\ 目录下的Web界面实现
2. 学习Hermes的认证系统和界面设计
3. 完善 D:\\codex-local\\chatbot\\ 目录
4. 添加用户认证、会话管理、历史记录
5. 优化界面设计和用户体验

输出：完善的Chatbot界面代码
""",
        "config": AgentConfig(
            agent_type=AgentType.CODE,
            max_iterations=30,
            model="deepseek-chat",
            provider="deepseek",
        )
    }
]


# ─── Task Runner ──────────────────────────────────────────────────────────

async def run_all_tasks():
    """Run all tasks in parallel with isolated agents"""
    print("=" * 60)
    print("ROOTCODE INTEGRATION TASKS")
    print("=" * 60)
    print(f"\nRunning {len(TASKS)} tasks in parallel...")
    print("-" * 60)

    # Create agents for each task
    agents = []
    for task_def in TASKS:
        agent = create_agent(
            agent_type=task_def["agent_type"],
            config=task_def["config"]
        )
        agents.append({
            "agent": agent,
            "task": task_def["task"],
            "id": task_def["id"],
            "name": task_def["name"]
        })
        print(f"Created agent for: {task_def['name']} ({task_def['id']})")

    print("-" * 60)

    # Run agents in parallel
    runner = ParallelAgentRunner(max_workers=4)

    # Add progress listeners
    for item in agents:
        def on_event(event, data, item=item):
            if event == "agent_start":
                print(f"[START] {item['name']}: {data.get('task', '')[:50]}...")
            elif event == "agent_complete":
                print(f"[DONE] {item['name']}: {data.get('status', '')} ({data.get('duration', 0):.1f}s)")

        item["agent"].add_listener(on_event)

    # Execute
    results = await runner.run_agents(agents)

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    for i, result in enumerate(results):
        task_name = TASKS[i]["name"]
        status = "SUCCESS" if result.status.value == "completed" else "FAILED"
        duration = f"{result.duration:.1f}s" if result.duration else "N/A"

        print(f"\n{task_name}:")
        print(f"  Status: {status}")
        print(f"  Duration: {duration}")

        if result.result:
            print(f"  Result: {result.result[:200]}...")
        if result.error:
            print(f"  Error: {result.error[:200]}...")

    return results


# ─── Single Task Runner ───────────────────────────────────────────────────

async def run_single_task(task_id: str):
    """Run a single task by ID"""
    task_def = None
    for t in TASKS:
        if t["id"] == task_id:
            task_def = t
            break

    if not task_def:
        print(f"Task not found: {task_id}")
        return None

    print(f"Running task: {task_def['name']}")

    agent = create_agent(
        agent_type=task_def["agent_type"],
        config=task_def["config"]
    )

    # Add progress listener
    def on_event(event, data):
        if event == "agent_start":
            print(f"[START] {data.get('task', '')[:50]}...")
        elif event == "agent_complete":
            print(f"[DONE] {data.get('status', '')} ({data.get('duration', 0):.1f}s)")

    agent.add_listener(on_event)

    result = await agent.run(task_def["task"])

    print(f"\nResult:")
    print(f"  Status: {result.status.value}")
    print(f"  Duration: {result.duration:.1f}s")

    if result.result:
        print(f"  Result: {result.result[:500]}...")
    if result.error:
        print(f"  Error: {result.error[:500]}...")

    return result


# ─── CLI Entry Point ──────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="RootCode Integration Tasks")
    parser.add_argument("--task", "-t", help="Run specific task by ID")
    parser.add_argument("--list", "-l", action="store_true", help="List all tasks")
    parser.add_argument("--all", "-a", action="store_true", help="Run all tasks in parallel")

    args = parser.parse_args()

    if args.list:
        print("Available tasks:")
        for task in TASKS:
            print(f"  {task['id']}: {task['name']}")
        return

    if args.task:
        asyncio.run(run_single_task(args.task))
    elif args.all:
        asyncio.run(run_all_tasks())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
