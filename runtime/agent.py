"""
Codex-Local Simple Agent
教程风格的极简 AI Agent：Brain + Memory + ToolRegistry + Planner + Executor
可以直接运行，对接 codex-local 的工具链。
"""

import os
import sys
import json
from typing import Any, Dict, List, Optional
from pathlib import Path

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from runtime.brain import AgentBrain
from runtime.session import SessionManager
from tools.executor import get_executor


# ─── Memory ──────────────────────────────────────────────────────────────────

class SimpleMemory:
    """简单记忆：短期（会话）+ 长期（持久化）"""

    def __init__(self):
        self.short: Dict[str, Any] = {}   # 当前任务上下文
        self.long: Dict[str, Any] = {}   # 长期偏好/联系人等
        self._manager = None

    @property
    def manager(self) -> SessionManager:
        if self._manager is None:
            self._manager = SessionManager()
        return self._manager

    def get(self, key: str, default=None) -> Any:
        return self.short.get(key, default)

    def set(self, key: str, value: Any):
        self.short[key] = value

    def get_long(self, key: str, default=None) -> Any:
        return self.long.get(key, default)

    def set_long(self, key: str, value: Any):
        self.long[key] = value

    def remember(self, key: str, value: Any, long_term: bool = False):
        """记忆存储"""
        if long_term:
            self.set_long(key, value)
        else:
            self.set(key, value)

    def recall(self, key: str) -> Any:
        """记忆召回"""
        if key in self.short:
            return self.short[key]
        return self.long.get(key)

    def history(self) -> List[Dict]:
        """获取对话历史"""
        return self.short.get("_conversation_history", [])

    def add_turn(self, role: str, content: str):
        """添加一轮对话到历史"""
        history = self.short.get("_conversation_history", [])
        history.append({"role": role, "content": content})
        self.short["_conversation_history"] = history


# ─── Tool Registry ───────────────────────────────────────────────────────────

class AgentToolRegistry:
    """
    轻量工具注册器。
    使用 codex-local 的 executor 作为底层工具实现。
    也支持直接注册自定义函数。
    """

    def __init__(self):
        self._executor = None
        self._custom: Dict[str, callable] = {}

    @property
    def executor(self):
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def register(self, name: str, fn: callable):
        """注册自定义工具函数"""
        self._custom[name] = fn

    def call(self, name: str, **kwargs) -> Any:
        """调用工具"""
        if name in self._custom:
            return self._custom[name](**kwargs)

        # 映射到 executor 工具
        tool_map = {
            "search": "WebFetch",
            "schedule": "TodoWrite",
            "time": "Bash",
            "calculate": "sandbox_exec",
            "read": "Read",
            "write": "Write",
            "python": "sandbox_exec",
            "weather": "WebFetch",
        }

        tool_name = tool_map.get(name, name)
        try:
            return self.executor.execute_tool(tool_name, kwargs)
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─── Planner ────────────────────────────────────────────────────────────────

class SimplePlanner:
    """
    简单规划器：将自然语言目标拆成有序步骤。
    使用 Brain 来决定步骤（比规则匹配更智能）。
    """

    def __init__(self, brain: AgentBrain):
        self.brain = brain

    def plan(self, goal: str) -> List[Dict[str, Any]]:
        """
        让 Brain 决定如何拆解任务。
        要求 Brain 返回 JSON 格式的步骤列表。
        """
        prompt = f"""你是一个任务规划助手。
用户目标：{goal}

请将这个目标拆解成具体的执行步骤。
严格按照以下JSON格式返回，不要有任何其他文字：
{{
  "steps": [
    {{"action": "工具名称", "params": {{"参数名": "参数值"}}, "reason": "为什么需要这一步"}},
    ...
  ]
}}

可用工具：search（搜索）、read（读文件）、write（写文件）、python（执行Python代码）、
         schedule（写TODO）、time（获取时间）、calculate（计算）、weather（查天气）

如果不需要工具，直接返回空的steps数组。
只返回JSON，不要解释。
"""
        result = self.brain.think_json(prompt)

        if "error" in result:
            # Fallback：返回一步到位的通用搜索
            return [{"action": "search", "params": {"url": f"https://www.google.com/search?q={goal}", "prompt": goal}, "reason": "搜索相关信息"}]

        steps = result.get("steps", [])
        if not isinstance(steps, list):
            return []
        return steps


# ─── Executor ───────────────────────────────────────────────────────────────

class SimpleExecutor:
    """
    执行器：把步骤映射为工具调用。
    处理返回值、格式化结果。
    """

    def __init__(self, tools: AgentToolRegistry, memory: SimpleMemory, brain: AgentBrain):
        self.tools = tools
        self.memory = memory
        self.brain = brain

    def run_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行单步"""
        action = step.get("action", "")
        params = step.get("params", {})
        reason = step.get("reason", "")

        try:
            result = self.tools.call(action, **params)

            # 如果是文件操作且成功，存入记忆
            if action in ("read", "write") and isinstance(result, dict) and result.get("success"):
                self.memory.set(f"last_{action}_result", result)

            return {
                "action": action,
                "params": params,
                "reason": reason,
                "result": result,
                "success": True,
            }
        except Exception as e:
            return {
                "action": action,
                "params": params,
                "reason": reason,
                "error": str(e),
                "success": False,
            }

    def run_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量执行步骤"""
        results = []
        for step in steps:
            r = self.run_step(step)
            results.append(r)
            # 把中间结果存入记忆
            self.memory.set(f"last_step", r)
        return results


# ─── Agent ──────────────────────────────────────────────────────────────────

class SimpleAgent:
    """
    简单的任务规划 AI Agent。

    架构：Brain（推理）+ Memory（记忆）+ ToolRegistry（工具）
        + Planner（规划）+ Executor（执行）

    使用方式：
        agent = SimpleAgent()
        result = agent.run("查一下明天北京的天气，如果下雨帮我提醒小王")
    """

    def __init__(
        self,
        model: str = None,
        provider: str = None,
        api_key: str = None,
        workspace: str = None,
    ):
        self.workspace = Path(workspace or os.environ.get("CODEX_WORKSPACE", "D:/"))

        # 核心组件
        self.brain = AgentBrain(model=model, provider=provider, api_key=api_key)
        self.memory = SimpleMemory()
        self.tools = AgentToolRegistry()
        self.planner = SimplePlanner(self.brain)
        self.executor = SimpleExecutor(self.tools, self.memory, self.brain)

        # 系统提示
        self.system_prompt = f"""你是一个任务规划助手，名叫 Codex-Agent。
你的职责是理解用户目标，决定是否需要使用工具，并生成简洁的帮助信息。

你有以下工具可用：
- search: 搜索网页（需要 url 和 prompt 参数）
- read: 读取文件（需要 file_path 参数）
- write: 写文件（需要 file_path 和 content 参数）
- python: 执行Python代码（需要 code 和 language 参数）
- schedule: 生成TODO列表（需要 todos 参数）
- time: 获取当前时间
- calculate: 执行数学计算（需要 expression 参数）

如果用户要求不需要具体工具操作，直接给出有用的回答即可。
语言要简洁、自然、友好。"""

    def run(self, user_task: str, max_steps: int = 10) -> Dict[str, Any]:
        """
        运行 Agent 处理任务。

        流程：
        1. 理解任务（Brain）
        2. 制定计划（Planner）
        3. 执行步骤（Executor）
        4. 生成最终回复（Brain）
        """
        print(f"[Agent] 收到任务：{user_task}")
        self.memory.add_turn("user", user_task)

        # Step 1: 让 Brain 理解任务，生成计划
        plan_prompt = f"""用户任务：{user_task}

请分析这个任务，判断是否需要使用工具。
如果需要，按照以下JSON格式返回你的计划：
{{
  "intent": "一句话描述任务意图",
  "steps": [
    {{"action": "工具名", "params": {{...}}, "reason": "..."}}
  ]
}}

如果不需要工具，直接回答用户：
{{
  "intent": "直接回答",
  "steps": []
}}

只返回JSON。"""

        plan_result = self.brain.think_json(plan_prompt, system=self.system_prompt)
        if "error" in plan_result:
            plan_result = {"intent": user_task, "steps": []}

        intent = plan_result.get("intent", user_task)
        steps = plan_result.get("steps", [])

        print(f"[Agent] 意图：{intent}")
        print(f"[Agent] 计划：{len(steps)} 个步骤")

        # Step 2: 执行步骤
        results = []
        for i, step in enumerate(steps[:max_steps], 1):
            print(f"[Agent] 执行步骤 {i}/{len(steps)}: {step.get('action')}")
            r = self.executor.run_step(step)
            results.append(r)
            self.memory.set(f"step_{i}", r)
            print(f"[Agent]   结果：{str(r.get('result', r.get('error', '')))[:100]}")

        # Step 3: 生成最终回复
        context = {
            "task": user_task,
            "intent": intent,
            "steps": steps,
            "results": results,
        }

        final_prompt = f"""用户任务：{user_task}
任务意图：{intent}
执行了 {len(results)} 个步骤。

执行结果：
{json.dumps(results, ensure_ascii=False, indent=2, default=str)}

请生成一段对用户的最终回复。
- 如果是信息查询任务，给出准确答案
- 如果是操作任务，说明做了什么
- 如果出错了，说明问题并给出建议
语言要简洁、自然、有帮助。"""

        final_reply = self.brain.think(final_prompt, system=self.system_prompt)
        self.memory.add_turn("assistant", final_reply)

        return {
            "intent": intent,
            "task": user_task,
            "steps": steps,
            "results": results,
            "reply": final_reply,
        }

    def chat(self, message: str) -> str:
        """单轮对话（不需要工具执行的简单问答）"""
        reply = self.brain.think(message, system=self.system_prompt)
        self.memory.add_turn("user", message)
        self.memory.add_turn("assistant", reply)
        return reply


# ─── CLI 入口 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=" * 50)
    print("Codex-Local Simple Agent")
    print("=" * 50)

    # 从环境变量或参数获取配置
    model = os.environ.get("CODEX_MODEL", "deepseek-chat")
    provider = os.environ.get("CODEX_PROVIDER", "deepseek")

    print(f"使用模型：{model} (@ {provider})")
    print()

    agent = SimpleAgent(model=model, provider=provider)

    # 测试任务
    test_tasks = [
        "你好，介绍一下你自己",
        "1+1等于几？直接说数字",
        "帮我写一个Hello World到 D:/codex-local/test_hello.py",
    ]

    if len(sys.argv) > 1:
        # 从命令行参数获取任务
        task = " ".join(sys.argv[1:])
        print(f"执行任务：{task}")
        result = agent.run(task)
        print("\n" + "=" * 50)
        print("最终回复：")
        print(result["reply"])
    else:
        # 运行测试任务
        for task in test_tasks:
            print(f"\n>>> {task}")
            result = agent.run(task)
            print(f"\n最终回复：{result['reply']}")
            print("-" * 50)