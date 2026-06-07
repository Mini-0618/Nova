"""
Codex-Local Self-Critic
Agent 完成任务后自我审查：检查正确性、完整性、一致性。
在交付前发现并修复问题。
"""

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from runtime.brain import AgentBrain


@dataclass
class CriticReport:
    """审查报告"""
    passed: bool
    score: float                    # 0-10
    issues: List[Dict[str, str]]   # [{"severity": "high/medium/low", "type": "...", "description": "...", "suggestion": "..."}]
    verdict: str                    # 总结语


@dataclass
class ReviewResult:
    original_answer: str
    critic_report: CriticReport
    revised_answer: str             # 如果有问题，经过修订的答案
    improved: bool                  # 是否真的有改进


class SelfCritic:
    """
    任务交付前的自我审查。

    审查维度：
    1. 正确性 — 事实是否准确，逻辑是否通顺
    2. 完整性 — 是否覆盖了用户需求的所有方面
    3. 一致性 — 答案内部是否矛盾，与上下文是否冲突
    4. 可执行性 — 如果是代码/计划，是否真的能执行

    使用方式：
        critic = SelfCritic(model="deepseek-chat")
        review = critic.review(task="用户任务", answer="AI给出的答案")
        if not review.critic_report.passed:
            print("审查发现问题：", review.critic_report.issues)
            print("修订后：", review.revised_answer)
    """

    def __init__(self, model: str = None, provider: str = None):
        self.brain = AgentBrain(model=model, provider=provider)

    SYSTEM_PROMPT = """你是一个严格的技术审查员（Technical Reviewer）。
你的职责是在AI回答交付用户之前，发现其中的问题。

审查标准：
1. 正确性 — 事实是否准确，逻辑是否通顺，代码是否有bug
2. 完整性 — 是否覆盖了用户需求的所有方面，有没有遗漏
3. 一致性 — 答案内部是否矛盾，前后说法是否冲突
4. 可执行性 — 如果是代码，是否语法正确、逻辑完整、能够运行
5. 安全性 — 是否有潜在风险（如命令注入、SQL注入、不安全函数）

评分标准（0-10）：
- 9-10：优秀，直接交付
- 7-8：良好，有小问题但不严重
- 5-6：一般，有明显问题需要修复
- 3-4：有严重问题，建议重做
- 0-2：完全不合格

你必须按以下JSON格式回复，不要有任何其他文字：

{
  "score": 8,
  "passed": true,
  "issues": [
    {"severity": "medium", "type": "完整性", "description": "没有考虑边界情况", "suggestion": "添加空值检查"}
  ],
  "verdict": "整体良好，但有两处小问题建议修复"
}

如果没有问题（9-10分），issues 填写空数组 []。
"""

    REVISION_PROMPT = """你是修订助手。

原始答案（有问题）：
{original}

审查发现的问题：
{issues}

请根据审查意见修订答案，修复所有问题。
只返回修订后的完整答案，不要有其他文字。
语言简洁、精确。
"""

    def review(self, task: str, answer: str, context: str = "") -> ReviewResult:
        """
        审查一个答案。

        Args:
            task: 原始用户任务
            answer: AI给出的答案
            context: 额外的上下文（如执行结果）

        Returns:
            ReviewResult，包含审查报告和修订后的答案
        """
        review_prompt = f"""## 审查任务
用户需求：{task}

## AI 回答
{answer}
"""

        if context:
            review_prompt += f"\n\n## 额外上下文（执行结果）\n{context}"

        review_prompt += "\n\n请严格审查以上回答的质量。"

        response = self.brain.think(review_prompt, system=self.SYSTEM_PROMPT)

        try:
            report_data = json.loads(response)
        except json.JSONDecodeError:
            # 降级
            return ReviewResult(
                original_answer=answer,
                critic_report=CriticReport(passed=True, score=10, issues=[], verdict="审查解析失败，跳过"),
                revised_answer=answer,
                improved=False,
            )

        # 解析审查结果
        score = max(0, min(10, float(report_data.get("score", 10))))
        passed = report_data.get("passed", score >= 7)
        issues_raw = report_data.get("issues", [])
        issues = []
        for item in issues_raw:
            if isinstance(item, dict):
                issues.append({
                    "severity": item.get("severity", "medium"),
                    "type": item.get("type", "未知"),
                    "description": item.get("description", ""),
                    "suggestion": item.get("suggestion", ""),
                })

        verdict = report_data.get("verdict", "")
        critic_report = CriticReport(
            passed=passed,
            score=score,
            issues=issues,
            verdict=verdict,
        )

        # 如果有问题，修订答案
        revised = answer
        improved = False

        if not passed and issues:
            issues_text = "\n".join(
                f"- [{i['severity']}] {i['type']}: {i['description']} → {i['suggestion']}"
                for i in issues
            )
            revision_prompt = self.REVISION_PROMPT.format(
                original=answer,
                issues=issues_text,
            )
            revised = self.brain.think(revision_prompt)
            improved = revised != answer

        return ReviewResult(
            original_answer=answer,
            critic_report=critic_report,
            revised_answer=revised,
            improved=improved,
        )

    def review_code(self, code: str, language: str = "python") -> CriticReport:
        """
        专门审查代码：语法正确性 + 安全 + 可运行性。
        """
        prompt = f"""## 代码审查

语言：{language}
```{{language}}
{code}
```

审查要点：
1. 语法是否正确
2. 是否有安全漏洞（命令注入、路径遍历、不安全函数等）
3. 逻辑是否完整
4. 是否有运行时错误风险
5. 代码风格是否合理

只返回JSON：
{{"score": 8, "passed": true/false, "issues": [{{"severity": "high", "type": "安全性", "description": "...", "suggestion": "..."}}], "verdict": "..."}}
"""
        response = self.brain.think(prompt, system=self.SYSTEM_PROMPT)

        try:
            data = json.loads(response)
            return CriticReport(
                passed=data.get("passed", True),
                score=max(0, min(10, float(data.get("score", 10)))),
                issues=[
                    {"severity": i.get("severity", "medium"), "type": i.get("type", ""), "description": i.get("description", ""), "suggestion": i.get("suggestion", "")}
                    for i in data.get("issues", []) if isinstance(i, dict)
                ],
                verdict=data.get("verdict", ""),
            )
        except json.JSONDecodeError:
            return CriticReport(passed=True, score=10, issues=[], verdict="审查解析失败，跳过")


# ─── Critic 集成到 Agent ──────────────────────────────────────────────────

class ReActAgentWithCritic:
    """
    ReAct Agent + 自我审查。
    任务完成后自动审查，通过后才交付。
    """

    def __init__(self, model: str = None, provider: str = None, max_iterations: int = 15):
        from runtime.react import ReActAgent
        self.agent = ReActAgent(model=model, provider=provider, max_iterations=max_iterations)
        self.critic = SelfCritic(model=model, provider=provider)

    def run(self, task: str, verbose: bool = True) -> ReviewResult:
        """运行任务并审查结果"""
        result = self.agent.run(task, verbose=verbose)

        if verbose:
            print(f"\n[Critic] 审查结果：score={result.final_answer[:50]}...")

        review = self.critic.review(task, result.final_answer)

        if verbose:
            cr = review.critic_report
            print(f"[Critic] 评分：{cr.score}/10 | {'✅ 通过' if cr.passed else '❌ 需修订'}")
            if cr.issues:
                print(f"[Critic] 问题：{len(cr.issues)}个")
                for issue in cr.issues:
                    print(f"  [{issue['severity']}] {issue['type']}: {issue['description']}")

        return review


# ─── 测试 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Self-Critic 测试")
    print("=" * 50)

    critic = SelfCritic(model="deepseek-chat")

    # 测试1：正常答案
    print("\n--- 测试1：正常答案 ---")
    review = critic.review(
        task="计算1+1等于几",
        answer="1+1=2"
    )
    print(f"评分：{review.critic_report.score}/10 | 通过：{review.critic_report.passed}")
    print(f"结论：{review.critic_report.verdict}")

    # 测试2：有问题的代码
    print("\n--- 测试2：有问题的代码 ---")
    report = critic.review_code("import os\nos.system('rm -rf /')")
    print(f"评分：{report.score}/10 | 通过：{report.passed}")
    for issue in report.issues:
        print(f"  [{issue['severity']}] {issue['type']}: {issue['description']}")
    print(f"结论：{report.verdict}")