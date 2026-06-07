"""
Codex-Local ReAct Agent
Reasoning + Acting Loop: think → act → observe → think → act → ...
自我纠正：错误了会回头重新想
"""

import os
import sys
import json
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from runtime.brain import AgentBrain
from tools.executor import get_executor


# ─── ReAct 步骤状态 ──────────────────────────────────────────────────────────

@dataclass
class ReActStep:
    step_number: int
    thought: str          # 我在想什么
    action: str           # 我决定做什么
    action_input: Dict   # 传给工具的参数
    observation: Any      # 观察到的结果
    error: Optional[str] = None
    corrected: bool = False  # 这步是否被纠正过


@dataclass
class ReActResult:
    task: str
    success: bool
    steps: List[ReActStep]
    final_answer: str
    iterations: int
    total_tokens: int = 0


# ─── ReAct Prompt 模板 ─────────────────────────────────────────────────────

THINK_SYSTEM_PROMPT = """你是一个推理引擎，执行 ReAct (Reasoning + Acting) 循环。

ReAct 循环：
1. THINK（思考）→ 分析当前状态，决定下一步行动
2. ACT（行动）→ 调用工具执行
3. OBSERVE（观察）→ 收集执行结果
4. repeat 直到任务完成

格式要求：
你必须严格按以下JSON格式回复，不要有任何其他文字：

{
  "thought": "分析当前情况，我在想什么",
  "action": "工具名称（如 Read / Write / Bash / search 等）",
  "action_input": {"参数名": "参数值"},
  "reasoning": "为什么我选择这个工具而不是其他"
}

如果任务已经完成，不需要再行动：
{
  "thought": "任务已完成",
  "action": "FINISH",
  "action_input": {},
  "reasoning": "结果已经满足用户需求"
}

如果发现之前的步骤有错误：
{
  "thought": "之前的结果有问题，需要纠正",
  "action": "CORRECT",
  "action_input": {"error": "哪里出错了", "corrective_action": "应该怎么做"},
  "reasoning": "发现错误的原因"
}

可用工具：Read, Write, Edit, Bash, Glob, Grep, sandbox_exec, WebFetch, DataLoad, DataClean, DataStats, DataReport
"""

FINISH_PROMPT = """任务执行完毕。请根据执行过程和结果，生成对用户的最终回复。

要求：
- 简洁明了，直接给出答案
- 如果有错误，说明问题并解释
- 如果是操作任务，说明做了什么
- 语言自然、有帮助
"""


# ─── ReAct Agent ────────────────────────────────────────────────────────────

class ReActAgent:
    """
    ReAct 风格的 Agent。

    与 SimpleAgent 的区别：
    - SimpleAgent：一次性规划所有步骤，然后批量执行
    - ReActAgent：想一步做一步，每步都观察结果再决定下一步
    - ReActAgent：会自我纠正（CORRECT 动作）

    使用方式：
        agent = ReActAgent(model="deepseek-chat", provider="deepseek")
        result = agent.run("帮我分析 D:/data/sales.csv 的销售趋势")
        print(result.final_answer)
    """

    def __init__(
        self,
        model: str = None,
        provider: str = None,
        api_key: str = None,
        max_iterations: int = 15,
        workspace: str = None,
    ):
        self.brain = AgentBrain(model=model, provider=provider, api_key=api_key)
        self.executor = get_executor()
        self.max_iterations = max_iterations
        self.workspace = Path(workspace or os.environ.get("CODEX_WORKSPACE", "D:/"))

    def _format_history(self, steps: List[ReActStep]) -> str:
        """把历史步骤格式化成上下文"""
        if not steps:
            return "（这是第一步，还没有历史）"

        lines = []
        for s in steps:
            status = "✅" if not s.error else f"❌ {s.error}"
            correction = " (已纠正)" if s.corrected else ""
            lines.append(
                f"步骤{s.step_number}{correction}：\n"
                f"  想：{s.thought}\n"
                f"  做：{s.action}({json.dumps(s.action_input, ensure_ascii=False)})\n"
                f"  观察：{str(s.observation)[:200] if s.observation else ''}\n"
                f"  {status}"
            )
        return "\n".join(lines)

    def _execute_action(self, action: str, action_input: Dict) -> tuple:
        """执行一个动作，返回 (observation, error)"""
        if action in ("FINISH", "CORRECT", "null", ""):
            return None, None

        try:
            # 映射 ReAct 动作名到工具名
            tool_map = {
                "Read": "Read",
                "Write": "Write",
                "Edit": "Edit",
                "Bash": "Bash",
                "Glob": "Glob",
                "Grep": "Grep",
                "search": "WebFetch",
                "WebFetch": "WebFetch",
                "python": "sandbox_exec",
                "sandbox_exec": "sandbox_exec",
                "calculate": "sandbox_exec",
                "DataLoad": "DataLoad",
                "DataClean": "DataClean",
                "DataStats": "DataStats",
                "DataReport": "DataReport",
                "GitStatus": "GitStatus",
                "GitLog": "GitLog",
                "GitDiff": "GitDiff",
                "GitCommit": "GitCommit",
            }

            tool_name = tool_map.get(action, action)
            result = self.executor.execute_tool(tool_name, action_input)

            # 格式化结果
            if isinstance(result, dict):
                if not result.get("success", True) and result.get("error"):
                    return None, result["error"]
                # 提取关键信息
                keys = list(result.keys())
                if "content" in result:
                    return result["content"], None
                if "stdout" in result:
                    return result["stdout"], None
                if "output" in result:
                    return result["output"], None
                return result, None
            return result, None

        except Exception as e:
            return None, str(e)

    def _build_context_prompt(self, task: str, steps: List[ReActStep]) -> str:
        """构建发送给 Brain 的上下文"""
        history = self._format_history(steps)

        prompt = f"""## 当前任务
{task}

## 执行历史
{history}

## 当前状态
请分析以上执行历史，决定下一步行动。
- 如果任务已完成，action 填写 "FINISH"
- 如果发现之前有错误，action 填写 "CORRECT"
- 否则，选择合适的工具执行

只返回JSON，不要有其他文字。"""
        return prompt

    def run(self, task: str, verbose: bool = True) -> ReActResult:
        """
        运行 ReAct 循环。

        返回 ReActResult，包含：
        - steps: 所有执行步骤
        - final_answer: 最终回复
        - iterations: 迭代次数
        - success: 是否成功
        """
        steps: List[ReActStep] = []
        total_tokens = 0
        last_error = None

        if verbose:
            print(f"[ReAct] 开始任务：{task[:80]}...")

        for i in range(self.max_iterations):
            iteration = i + 1

            # 1. THINK：让 Brain 决定下一步
            context = self._build_context_prompt(task, steps)
            response = self.brain.think(context, system=THINK_SYSTEM_PROMPT)

            # 2. 解析 Brain 的回复
            try:
                decision = json.loads(response)
            except json.JSONDecodeError:
                # 降级：把整个回复当作思考，重新尝试
                decision = {
                    "thought": response[:200],
                    "action": "Bash",
                    "action_input": {"command": f"echo '{task}'"},
                    "reasoning": "JSON解析失败，降级处理",
                }

            thought = decision.get("thought", "")
            action = decision.get("action", "")
            action_input = decision.get("action_input", {})
            reasoning = decision.get("reasoning", "")

            if verbose:
                print(f"[ReAct 步骤{iteration}] {action}: {reasoning[:60]}...")

            # 3. 检查是否结束
            if action == "FINISH":
                final_answer = thought or "任务已完成。"
                if verbose:
                    print(f"[ReAct] 完成于步骤{iteration} ✅")
                return ReActResult(
                    task=task,
                    success=True,
                    steps=steps,
                    final_answer=final_answer,
                    iterations=iteration,
                    total_tokens=total_tokens,
                )

            # 4. 处理纠正
            if action == "CORRECT":
                corrective = action_input.get("corrective_action", "")
                if verbose:
                    print(f"[ReAct] 纠正：{corrective}")
                # 记录纠正信息，但不停止，继续
                steps.append(ReActStep(
                    step_number=iteration,
                    thought=thought,
                    action="CORRECT",
                    action_input=action_input,
                    observation=None,
                    error=action_input.get("error"),
                    corrected=True,
                ))
                continue

            # 5. ACT：执行动作
            observation, error = self._execute_action(action, action_input)

            step = ReActStep(
                step_number=iteration,
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
                error=error,
            )
            steps.append(step)

            if error:
                if verbose:
                    print(f"[ReAct]   ❌ 错误：{error[:80]}")
                # 不立即失败，继续让 Brain 决定如何纠正

            elif observation is not None:
                if verbose:
                    obs_str = str(observation)[:100].replace("\n", " ")
                    print(f"[ReAct]   ✅ {obs_str}...")

            # 6. 检查是否陷入循环（连续3步同一动作）
            recent_actions = [s.action for s in steps[-3:] if s.action not in ("CORRECT", "FINISH")]
            if len(recent_actions) >= 3 and len(set(recent_actions)) == 1:
                if verbose:
                    print(f"[ReAct] ⚠️ 检测到循环：连续3步执行相同动作，强制结束")
                break

        # 超过最大迭代
        if verbose:
            print(f"[ReAct] 达到最大迭代次数 {self.max_iterations}，强制结束")

        # 生成最终回复
        final_prompt = f"""任务：{task}
执行了 {len(steps)} 步，未能在限制内完成。

执行历史：
{self._format_history(steps)}

请生成一个对用户的回复，说明完成了什么、还有什么问题。
语言简洁、自然。"""

        final_answer = self.brain.think(final_prompt, system=FINISH_PROMPT)

        return ReActResult(
            task=task,
            success=False,
            steps=steps,
            final_answer=final_answer,
            iterations=len(steps),
            total_tokens=total_tokens,
        )

    def run_with_fallback(self, task: str) -> str:
        """
        尝试 ReAct，如果失败（API错误等），降级到简单直接回答。
        """
        try:
            result = self.run(task, verbose=True)
            return result.final_answer
        except Exception as e:
            # 降级：用 Brain 直接回答
            return self.brain.think(task)


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=" * 50)
    print("Codex-Local ReAct Agent")
    print("=" * 50)

    model = os.environ.get("CODEX_MODEL", "deepseek-chat")
    provider = os.environ.get("CODEX_PROVIDER", "deepseek")
    agent = ReActAgent(model=model, provider=provider)

    task = sys.argv[1] if len(sys.argv) > 1 else "1+1等于几？"

    print(f"\n任务：{task}")
    result = agent.run(task)

    print(f"\n{'='*50}")
    print(f"完成：{result.success} | 迭代：{result.iterations}")
    print(f"最终回复：{result.final_answer}")