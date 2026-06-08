"""
Deep Thinker — 给 codex-local 加深度思考能力

核心思路：
1. 行动前思考（Pre-Action Think）：先想清楚再动手
2. 行动后反思（Post-Action Reflect）：做完回顾对不对
3. 多角度分析（Multi-Perspective）：从不同角度看问题
4. 对抗性验证（Adversarial Check）：找自己的漏洞
"""

import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class ThoughtStep:
    """一个思考步骤"""
    type: str  # analyze, plan, verify, reflect, adversarial
    content: str
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class ThinkingChain:
    """一条完整的思考链"""
    task: str
    steps: List[ThoughtStep] = field(default_factory=list)
    final_decision: str = ""
    confidence: float = 0.0
    revisions: int = 0

    def add_step(self, step_type: str, content: str, **kwargs):
        step = ThoughtStep(type=step_type, content=content, **kwargs)
        self.steps.append(step)
        return step

    def to_prompt(self) -> str:
        """把思考链转成 prompt 片段"""
        lines = [f"Task: {self.task}\n"]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"Step {i} [{step.type}]: {step.content}")
            if step.evidence:
                lines.append(f"  Evidence: {', '.join(step.evidence)}")
            if step.alternatives:
                lines.append(f"  Alternatives: {', '.join(step.alternatives)}")
            lines.append(f"  Confidence: {step.confidence:.0%}\n")
        if self.final_decision:
            lines.append(f"Decision: {self.final_decision}")
            lines.append(f"Overall Confidence: {self.confidence:.0%}")
        return "\n".join(lines)


class DeepThinker:
    """深度思考引擎"""

    def __init__(self, llm_caller=None):
        """
        llm_caller: async function(messages) -> str
        如果不提供，用纯规则推理
        """
        self.llm_caller = llm_caller
        self.thinking_history: List[ThinkingChain] = []

    async def think_before_act(self, task: str, context: str = "",
                                available_tools: List[str] = None) -> ThinkingChain:
        """行动前深度思考"""
        chain = ThinkingChain(task=task)

        # Step 1: 分析问题
        analysis = self._analyze_problem(task, context)
        chain.add_step("analyze", analysis["content"],
                       confidence=analysis["confidence"],
                       evidence=analysis.get("evidence", []))

        # Step 2: 制定计划
        plan = self._make_plan(task, analysis, available_tools or [])
        chain.add_step("plan", plan["content"],
                       confidence=plan["confidence"],
                       alternatives=plan.get("alternatives", []))

        # Step 3: 预判风险
        risks = self._predict_risks(task, plan)
        if risks["content"]:
            chain.add_step("risk", risks["content"],
                           confidence=risks["confidence"])

        # Step 4: 对抗性验证
        adversarial = self._adversarial_check(task, plan)
        if adversarial["content"]:
            chain.add_step("adversarial", adversarial["content"],
                           confidence=adversarial["confidence"])

        # 最终决策
        chain.final_decision = plan["content"]
        chain.confidence = min(s.confidence for s in chain.steps)

        self.thinking_history.append(chain)
        return chain

    async def reflect_after_act(self, chain: ThinkingChain,
                                 action_taken: str, result: str,
                                 success: bool) -> ThinkingChain:
        """行动后反思"""
        # Step 5: 结果分析
        if success:
            chain.add_step("reflect",
                          f"Action succeeded: {action_taken}",
                          confidence=0.9,
                          evidence=[result[:200]])
        else:
            chain.add_step("reflect",
                          f"Action failed: {action_taken}",
                          confidence=0.3,
                          evidence=[result[:200]])
            chain.revisions += 1

            # Step 6: 失败归因
            cause = self._analyze_failure(task=chain.task,
                                          action=action_taken,
                                          error=result)
            chain.add_step("failure_analysis", cause["content"],
                          confidence=cause["confidence"])

            # Step 7: 修正计划
            revision = self._revise_plan(chain, action_taken, result)
            chain.add_step("revision", revision["content"],
                          confidence=revision["confidence"],
                          alternatives=revision.get("alternatives", []))

        return chain

    def _analyze_problem(self, task: str, context: str) -> Dict:
        """分析问题本质"""
        analysis = {
            "content": "",
            "confidence": 0.7,
            "evidence": []
        }

        task_lower = task.lower()

        # 任务类型识别
        if any(w in task_lower for w in ["fix", "bug", "error", "broken"]):
            analysis["content"] = "This is a bug fix task. Need to: 1) reproduce the bug, 2) find root cause, 3) make minimal fix, 4) verify."
            analysis["evidence"].append("Task contains bug-related keywords")
            analysis["confidence"] = 0.8

        elif any(w in task_lower for w in ["create", "build", "add", "implement"]):
            analysis["content"] = "This is a feature creation task. Need to: 1) understand requirements, 2) design solution, 3) implement, 4) test."
            analysis["evidence"].append("Task contains creation keywords")
            analysis["confidence"] = 0.7

        elif any(w in task_lower for w in ["refactor", "improve", "optimize"]):
            analysis["content"] = "This is an improvement task. Need to: 1) understand current state, 2) identify improvement areas, 3) make changes, 4) verify no regression."
            analysis["evidence"].append("Task contains improvement keywords")
            analysis["confidence"] = 0.7

        elif any(w in task_lower for w in ["test", "verify", "check"]):
            analysis["content"] = "This is a verification task. Need to: 1) understand what to verify, 2) run tests, 3) analyze results."
            analysis["evidence"].append("Task contains verification keywords")
            analysis["confidence"] = 0.8

        else:
            analysis["content"] = "General task. Need to: 1) understand the goal, 2) find relevant files, 3) make changes, 4) verify."
            analysis["confidence"] = 0.5

        # 复杂度评估
        if any(w in task_lower for w in ["across", "multiple", "all", "every"]):
            analysis["content"] += " NOTE: This is a cross-file task, be careful about side effects."
            analysis["confidence"] -= 0.1

        return analysis

    def _make_plan(self, task: str, analysis: Dict, tools: List[str]) -> Dict:
        """制定执行计划"""
        plan = {
            "content": "",
            "confidence": 0.7,
            "alternatives": []
        }

        steps = []

        # 根据任务类型制定计划
        if "bug fix" in analysis["content"].lower():
            steps = [
                "1. Read the relevant file to understand current code",
                "2. Identify the exact bug location",
                "3. Make the minimal fix (change only what's necessary)",
                "4. Run the specific test to verify",
                "5. If test passes, run broader tests to check for regressions"
            ]
            plan["alternatives"] = [
                "If the bug is complex, try reproducing it in isolation first",
                "If the fix is unclear, check similar patterns in the codebase"
            ]

        elif "feature creation" in analysis["content"].lower():
            steps = [
                "1. Read existing code to understand patterns",
                "2. Design the new feature (function signature, inputs, outputs)",
                "3. Implement the feature",
                "4. Write tests for the feature",
                "5. Run all tests to verify no regression"
            ]
            plan["alternatives"] = [
                "If the feature is complex, break it into smaller sub-features",
                "If unsure about design, check similar features in the codebase"
            ]

        elif "improvement" in analysis["content"].lower():
            steps = [
                "1. Run existing tests to establish baseline",
                "2. Identify specific improvement targets",
                "3. Make changes incrementally",
                "4. Run tests after each change",
                "5. Compare results with baseline"
            ]

        else:
            steps = [
                "1. Read relevant files",
                "2. Understand the current state",
                "3. Make necessary changes",
                "4. Verify the changes work"
            ]

        plan["content"] = "\n".join(steps)
        return plan

    def _predict_risks(self, task: str, plan: Dict) -> Dict:
        """预判风险"""
        risks = []
        plan_lower = plan["content"].lower()

        if "read" in plan_lower and "write" in plan_lower:
            risks.append("Risk: Modifying files that are read later could cause inconsistency")

        if "multiple" in task.lower() or "all" in task.lower():
            risks.append("Risk: Changes across multiple files could have unexpected interactions")

        if "delete" in task.lower() or "remove" in task.lower():
            risks.append("Risk: Deletion operations are hard to reverse")

        if not risks:
            return {"content": "", "confidence": 0.0}

        return {
            "content": "\n".join(risks),
            "confidence": 0.6
        }

    def _adversarial_check(self, task: str, plan: Dict) -> Dict:
        """对抗性验证：找计划的漏洞"""
        issues = []
        plan_lower = plan["content"].lower()

        # 检查是否有验证步骤
        if "test" not in plan_lower and "verify" not in plan_lower:
            issues.append("WARNING: Plan has no verification step. Add a test or check.")

        # 检查是否太激进
        if "all" in task.lower() and "first" not in plan_lower:
            issues.append("WARNING: Task affects 'all' but plan doesn't start with a small test.")

        # 检查是否有回退方案
        if "alternative" not in plan_lower and "fallback" not in plan_lower:
            issues.append("SUGGESTION: Consider what to do if the first approach fails.")

        if not issues:
            return {"content": "", "confidence": 0.0}

        return {
            "content": "\n".join(issues),
            "confidence": 0.5
        }

    def _analyze_failure(self, task: str, action: str, error: str) -> Dict:
        """分析失败原因"""
        error_lower = error.lower()

        if "filenotfound" in error_lower or "no such file" in error_lower:
            return {
                "content": "File not found. Check the file path is correct and the file exists.",
                "confidence": 0.9
            }
        elif "syntaxerror" in error_lower:
            return {
                "content": "Syntax error in the code. Check for missing brackets, quotes, or indentation.",
                "confidence": 0.9
            }
        elif "typeerror" in error_lower:
            return {
                "content": "Type error. Check that function arguments match the expected types.",
                "confidence": 0.8
            }
        elif "importerror" in error_lower or "modulenotfound" in error_lower:
            return {
                "content": "Import error. Check if the module is installed and the import path is correct.",
                "confidence": 0.9
            }
        elif "assertion" in error_lower:
            return {
                "content": "Assertion failed. The code runs but produces wrong output. Check the logic.",
                "confidence": 0.8
            }
        elif "timeout" in error_lower:
            return {
                "content": "Timeout. The code took too long. Check for infinite loops or very slow operations.",
                "confidence": 0.8
            }
        else:
            return {
                "content": f"Unknown error. Analyze the error message carefully: {error[:200]}",
                "confidence": 0.5
            }

    def _revise_plan(self, chain: ThinkingChain, failed_action: str,
                     error: str) -> Dict:
        """修正计划"""
        # 找到最后一个 plan 步骤
        last_plan = None
        for step in reversed(chain.steps):
            if step.type == "plan":
                last_plan = step
                break

        if not last_plan:
            return {
                "content": "No previous plan found. Start fresh with a different approach.",
                "confidence": 0.5
            }

        revision = f"Previous approach failed: {failed_action}\n"
        revision += f"Error: {error[:200]}\n"
        revision += "Revised plan:\n"
        revision += "1. Understand why the previous approach failed\n"
        revision += "2. Try a different approach based on the error\n"
        revision += "3. Verify the new approach works"

        return {
            "content": revision,
            "confidence": 0.6,
            "alternatives": [
                "Try a completely different approach",
                "Break the problem into smaller parts",
                "Ask for more context or clarification"
            ]
        }

    def get_stats(self) -> Dict:
        """获取思考统计"""
        if not self.thinking_history:
            return {"total_thinking_sessions": 0}

        total_steps = sum(len(c.steps) for c in self.thinking_history)
        avg_confidence = sum(c.confidence for c in self.thinking_history) / len(self.thinking_history)
        total_revisions = sum(c.revisions for c in self.thinking_history)

        return {
            "total_thinking_sessions": len(self.thinking_history),
            "total_thought_steps": total_steps,
            "average_confidence": round(avg_confidence, 2),
            "total_revisions": total_revisions,
            "steps_per_thinking": round(total_steps / len(self.thinking_history), 1)
        }


def create_deep_thinker(llm_caller=None) -> DeepThinker:
    """工厂函数"""
    return DeepThinker(llm_caller=llm_caller)
