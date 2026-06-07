"""
Smart Model Router for Codex-Local
Intelligently routes tasks to the optimal model based on:
- Task complexity (simple/medium/complex)
- Cost constraints
- Quality requirements
- Latency requirements
- Local vs cloud preference

This is the core differentiator of Codex-Local - no other product does this.
"""

import os
import json
import time
import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum


# ─── Task Complexity Levels ───────────────────────────────────────────────

class TaskComplexity(Enum):
    SIMPLE = "simple"      # 补全、格式化、简单解释
    MEDIUM = "medium"      # 重构、函数编写、bug修复
    COMPLEX = "complex"    # 架构设计、复杂算法、多文件重构
    CRITICAL = "critical"  # 安全审计、性能优化、生产问题


# ─── Model Tiers ──────────────────────────────────────────────────────────

class ModelTier(Enum):
    LOCAL = "local"        # Ollama本地模型 - 零成本
    CHEAP = "cheap"        # DeepSeek/MiMo - 低成本
    BALANCED = "balanced"  # GPT-4o - 平衡
    PREMIUM = "premium"    # Claude Opus/GPT-5 - 高质量


# ─── Model Configuration ──────────────────────────────────────────────────

@dataclass
class ModelConfig:
    provider: str
    model: str
    tier: ModelTier
    cost_per_1k_input: float   # $/1K tokens
    cost_per_1k_output: float  # $/1K tokens
    avg_latency_ms: int        # 平均延迟
    quality_score: float       # 质量评分 0-1
    max_context: int           # 最大上下文长度
    supports_tools: bool       # 是否支持工具调用
    supports_streaming: bool   # 是否支持流式输出
    offline_capable: bool      # 是否可离线使用


# ─── Model Registry ───────────────────────────────────────────────────────

MODEL_REGISTRY: Dict[str, ModelConfig] = {
    # 本地模型 - 零成本
    "ollama/llama3:8b": ModelConfig(
        provider="ollama",
        model="llama3:8b",
        tier=ModelTier.LOCAL,
        cost_per_1k_input=0,
        cost_per_1k_output=0,
        avg_latency_ms=500,
        quality_score=0.6,
        max_context=8192,
        supports_tools=False,
        supports_streaming=True,
        offline_capable=True,
    ),
    "ollama/llama3:70b": ModelConfig(
        provider="ollama",
        model="llama3:70b",
        tier=ModelTier.LOCAL,
        cost_per_1k_input=0,
        cost_per_1k_output=0,
        avg_latency_ms=2000,
        quality_score=0.8,
        max_context=8192,
        supports_tools=False,
        supports_streaming=True,
        offline_capable=True,
    ),
    "ollama/deepseek-coder:33b": ModelConfig(
        provider="ollama",
        model="deepseek-coder:33b",
        tier=ModelTier.LOCAL,
        cost_per_1k_input=0,
        cost_per_1k_output=0,
        avg_latency_ms=1500,
        quality_score=0.75,
        max_context=16384,
        supports_tools=False,
        supports_streaming=True,
        offline_capable=True,
    ),
    "ollama/codellama:34b": ModelConfig(
        provider="ollama",
        model="codellama:34b",
        tier=ModelTier.LOCAL,
        cost_per_1k_input=0,
        cost_per_1k_output=0,
        avg_latency_ms=1500,
        quality_score=0.7,
        max_context=16384,
        supports_tools=False,
        supports_streaming=True,
        offline_capable=True,
    ),

    # 低成本云端模型
    "deepseek/deepseek-chat": ModelConfig(
        provider="deepseek",
        model="deepseek-chat",
        tier=ModelTier.CHEAP,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.003,
        avg_latency_ms=800,
        quality_score=0.85,
        max_context=32768,
        supports_tools=True,
        supports_streaming=True,
        offline_capable=False,
    ),
    "deepseek/deepseek-coder": ModelConfig(
        provider="deepseek",
        model="deepseek-coder",
        tier=ModelTier.CHEAP,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.003,
        avg_latency_ms=800,
        quality_score=0.88,
        max_context=32768,
        supports_tools=True,
        supports_streaming=True,
        offline_capable=False,
    ),
    "xiaomi/mimo": ModelConfig(
        provider="xiaomi",
        model="mimo",
        tier=ModelTier.CHEAP,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.003,
        avg_latency_ms=600,
        quality_score=0.82,
        max_context=32768,
        supports_tools=True,
        supports_streaming=True,
        offline_capable=False,
    ),

    # 平衡模型
    "openai/gpt-4o": ModelConfig(
        provider="openai",
        model="gpt-4o",
        tier=ModelTier.BALANCED,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
        avg_latency_ms=600,
        quality_score=0.92,
        max_context=128000,
        supports_tools=True,
        supports_streaming=True,
        offline_capable=False,
    ),
    "anthropic/claude-sonnet-4-6": ModelConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        tier=ModelTier.BALANCED,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        avg_latency_ms=700,
        quality_score=0.93,
        max_context=200000,
        supports_tools=True,
        supports_streaming=True,
        offline_capable=False,
    ),

    # 高级模型
    "anthropic/claude-opus-4-8": ModelConfig(
        provider="anthropic",
        model="claude-opus-4-8",
        tier=ModelTier.PREMIUM,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        avg_latency_ms=1500,
        quality_score=0.98,
        max_context=200000,
        supports_tools=True,
        supports_streaming=True,
        offline_capable=False,
    ),
    "openai/gpt-5": ModelConfig(
        provider="openai",
        model="gpt-5",
        tier=ModelTier.PREMIUM,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        avg_latency_ms=1000,
        quality_score=0.96,
        max_context=256000,
        supports_tools=True,
        supports_streaming=True,
        offline_capable=False,
    ),
}


# ─── Task Analyzer ────────────────────────────────────────────────────────

class TaskAnalyzer:
    """Analyzes task complexity based on multiple signals"""

    # 简单任务关键词
    SIMPLE_KEYWORDS = [
        "format", "格式化", "lint", "fix typo", "rename", "重命名",
        "comment", "注释", "explain", "解释", "read", "读取",
        "list", "列出", "show", "显示", "print", "打印",
    ]

    # 中等任务关键词
    MEDIUM_KEYWORDS = [
        "implement", "实现", "write", "写", "create", "创建",
        "add", "添加", "fix", "修复", "bug", "error", "错误",
        "refactor", "重构", "optimize", "优化", "test", "测试",
        "function", "函数", "class", "类", "method", "方法",
    ]

    # 复杂任务关键词
    COMPLEX_KEYWORDS = [
        "architecture", "架构", "design", "设计", "system", "系统",
        "database", "数据库", "api", "接口", "microservice", "微服务",
        "security", "安全", "performance", "性能", "scale", "扩展",
        "algorithm", "算法", "complex", "复杂", "multiple files", "多文件",
    ]

    # 关键任务关键词
    CRITICAL_KEYWORDS = [
        "production", "生产", "deploy", "部署", "migration", "迁移",
        "audit", "审计", "compliance", "合规", "critical", "关键",
        "security vulnerability", "安全漏洞", "data loss", "数据丢失",
    ]

    def analyze(self, task: str) -> Tuple[TaskComplexity, float, Dict[str, Any]]:
        """
        Analyze task complexity.

        Returns:
            (complexity, confidence, analysis_details)
        """
        task_lower = task.lower()

        # 计算各复杂度级别的匹配分数（关键词权重更高）
        simple_score = sum(2 for kw in self.SIMPLE_KEYWORDS if kw in task_lower)
        medium_score = sum(2 for kw in self.MEDIUM_KEYWORDS if kw in task_lower)
        complex_score = sum(2 for kw in self.COMPLEX_KEYWORDS if kw in task_lower)
        critical_score = sum(3 for kw in self.CRITICAL_KEYWORDS if kw in task_lower)

        # 分析任务长度（更长的任务通常更复杂）
        length_score = len(task) / 100  # 每100字符加1分

        # 分析代码块数量（更多代码块通常更复杂）
        code_blocks = task.count("```")
        code_score = code_blocks * 2

        # 综合评分（关键词权重更高）
        total_simple = simple_score + max(0, 2 - length_score)
        total_medium = medium_score + length_score * 0.5
        total_complex = complex_score + length_score + code_score
        total_critical = critical_score * 2

        # 确定复杂度
        scores = {
            TaskComplexity.SIMPLE: total_simple,
            TaskComplexity.MEDIUM: total_medium,
            TaskComplexity.COMPLEX: total_complex,
            TaskComplexity.CRITICAL: total_critical,
        }

        complexity = max(scores, key=scores.get)

        # 计算置信度
        max_score = max(scores.values())
        total_score = sum(scores.values())
        confidence = max_score / total_score if total_score > 0 else 0.5

        analysis = {
            "scores": {k.value: v for k, v in scores.items()},
            "task_length": len(task),
            "code_blocks": code_blocks,
            "keywords_found": {
                "simple": [kw for kw in self.SIMPLE_KEYWORDS if kw in task_lower],
                "medium": [kw for kw in self.MEDIUM_KEYWORDS if kw in task_lower],
                "complex": [kw for kw in self.COMPLEX_KEYWORDS if kw in task_lower],
                "critical": [kw for kw in self.CRITICAL_KEYWORDS if kw in task_lower],
            },
        }

        return complexity, confidence, analysis


# ─── Model Selector ───────────────────────────────────────────────────────

class ModelSelector:
    """Selects the optimal model based on task complexity and constraints"""

    def __init__(self, models: Dict[str, ModelConfig] = None):
        self.models = models or MODEL_REGISTRY
        self._local_models = {k: v for k, v in self.models.items() if v.tier == ModelTier.LOCAL}
        self._cheap_models = {k: v for k, v in self.models.items() if v.tier == ModelTier.CHEAP}
        self._balanced_models = {k: v for k, v in self.models.items() if v.tier == ModelTier.BALANCED}
        self._premium_models = {k: v for k, v in self.models.items() if v.tier == ModelTier.PREMIUM}

    def select(
        self,
        complexity: TaskComplexity,
        budget_remaining: float = float("inf"),
        prefer_local: bool = False,
        require_tools: bool = False,
        max_latency_ms: int = 10000,
        quality_threshold: float = 0.0,
    ) -> Tuple[str, ModelConfig, str]:
        """
        Select the optimal model.

        Returns:
            (model_key, model_config, reason)
        """
        # 根据复杂度确定候选模型
        if complexity == TaskComplexity.SIMPLE:
            candidates = list(self._local_models.items()) + list(self._cheap_models.items())
            preference = "local_first"
        elif complexity == TaskComplexity.MEDIUM:
            candidates = list(self._cheap_models.items()) + list(self._balanced_models.items())
            preference = "cost_effective"
        elif complexity == TaskComplexity.COMPLEX:
            candidates = list(self._balanced_models.items()) + list(self._premium_models.items())
            preference = "quality_first"
        else:  # CRITICAL
            candidates = list(self._premium_models.items())
            preference = "maximum_quality"

        # 应用约束过滤
        filtered = []
        for key, config in candidates:
            # 预算约束
            if config.cost_per_1k_output > budget_remaining / 1000:
                continue

            # 工具支持约束
            if require_tools and not config.supports_tools:
                continue

            # 延迟约束
            if config.avg_latency_ms > max_latency_ms:
                continue

            # 质量阈值约束
            if config.quality_score < quality_threshold:
                continue

            filtered.append((key, config))

        # 如果prefer_local，优先选择本地模型
        if prefer_local and filtered:
            local_candidates = [(k, v) for k, v in filtered if v.tier == ModelTier.LOCAL]
            if local_candidates:
                filtered = local_candidates
                reason = "prefer_local"
            else:
                reason = preference
        else:
            reason = preference

        if not filtered:
            # 如果没有符合条件的模型，放宽约束
            filtered = [(k, v) for k, v in self.models.items()
                       if v.tier in [ModelTier.LOCAL, ModelTier.CHEAP]]
            reason = "fallback_to_local_or_cheap"

        # 选择最优模型（按质量/成本比排序）
        def score_model(item):
            key, config = item
            quality = config.quality_score
            cost = config.cost_per_1k_output + config.cost_per_1k_input
            latency = config.avg_latency_ms / 1000  # 转换为秒

            # 综合评分：质量权重0.5，成本权重0.3，延迟权重0.2
            if cost == 0:
                cost_score = 1.0  # 本地模型成本为0
            else:
                cost_score = 1.0 / (1.0 + cost * 100)

            latency_score = 1.0 / (1.0 + latency)

            return quality * 0.5 + cost_score * 0.3 + latency_score * 0.2

        filtered.sort(key=score_model, reverse=True)

        selected_key, selected_config = filtered[0]

        return selected_key, selected_config, reason


# ─── Cost Optimizer ────────────────────────────────────────────────────────

class CostOptimizer:
    """Optimizes costs through various strategies"""

    def __init__(self, monthly_budget: float = 50.0):
        self.monthly_budget = monthly_budget
        self.spent_this_month = 0.0
        self.history: List[Dict[str, Any]] = []

    def can_afford(self, estimated_cost: float) -> bool:
        """Check if we can afford the estimated cost"""
        return (self.spent_this_month + estimated_cost) <= self.monthly_budget

    def record_usage(self, cost: float, model: str, tokens_used: int):
        """Record token usage"""
        self.spent_this_month += cost
        self.history.append({
            "timestamp": time.time(),
            "cost": cost,
            "model": model,
            "tokens": tokens_used,
        })

    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status"""
        return {
            "monthly_budget": self.monthly_budget,
            "spent_this_month": self.spent_this_month,
            "remaining": self.monthly_budget - self.spent_this_month,
            "percent_used": (self.spent_this_month / self.monthly_budget * 100) if self.monthly_budget > 0 else 0,
            "can_afford_premium": (self.monthly_budget - self.spent_this_month) > 10.0,
        }

    def estimate_cost(self, model_config: ModelConfig, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a request"""
        input_cost = (input_tokens / 1000) * model_config.cost_per_1k_input
        output_cost = (output_tokens / 1000) * model_config.cost_per_1k_output
        return input_cost + output_cost

    def suggest_downgrade(self, current_model: ModelConfig) -> Optional[str]:
        """Suggest a cheaper model if budget is tight"""
        budget_status = self.get_budget_status()

        if budget_status["percent_used"] > 80:
            # 预算紧张，建议降级
            if current_model.tier == ModelTier.PREMIUM:
                return "balanced"
            elif current_model.tier == ModelTier.BALANCED:
                return "cheap"
            elif current_model.tier == ModelTier.CHEAP:
                return "local"

        return None


# ─── Smart Router ──────────────────────────────────────────────────────────

class SmartRouter:
    """
    The main smart router that orchestrates task analysis, model selection,
    and cost optimization.

    This is the core differentiator of Codex-Local.
    """

    def __init__(
        self,
        monthly_budget: float = 50.0,
        prefer_local: bool = False,
        quality_threshold: float = 0.0,
        models: Dict[str, ModelConfig] = None,
    ):
        self.analyzer = TaskAnalyzer()
        self.selector = ModelSelector(models)
        self.cost_optimizer = CostOptimizer(monthly_budget)
        self.prefer_local = prefer_local
        self.quality_threshold = quality_threshold
        self._routing_history: List[Dict[str, Any]] = []

    def route(
        self,
        task: str,
        require_tools: bool = False,
        max_latency_ms: int = 10000,
        budget_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Route a task to the optimal model.

        Returns:
            {
                "model_key": str,
                "model_config": ModelConfig,
                "complexity": TaskComplexity,
                "confidence": float,
                "reason": str,
                "estimated_cost": float,
                "analysis": dict,
            }
        """
        # 1. 分析任务复杂度
        complexity, confidence, analysis = self.analyzer.analyze(task)

        # 2. 检查预算
        budget = budget_override or self.cost_optimizer.monthly_budget
        budget_status = self.cost_optimizer.get_budget_status()

        # 3. 确定是否优先本地模型
        prefer_local = self.prefer_local or budget_status["percent_used"] > 90

        # 4. 选择模型
        model_key, model_config, reason = self.selector.select(
            complexity=complexity,
            budget_remaining=budget_status["remaining"],
            prefer_local=prefer_local,
            require_tools=require_tools,
            max_latency_ms=max_latency_ms,
            quality_threshold=self.quality_threshold,
        )

        # 5. 估算成本（假设平均1000输入token，500输出token）
        estimated_cost = self.cost_optimizer.estimate_cost(model_config, 1000, 500)

        # 6. 检查是否需要降级
        if not self.cost_optimizer.can_afford(estimated_cost):
            downgrade = self.cost_optimizer.suggest_downgrade(model_config)
            if downgrade:
                # 降级到更便宜的模型
                for k, v in self.selector.models.items():
                    if v.tier.value == downgrade:
                        model_key = k
                        model_config = v
                        reason = f"budget_downgrade_to_{downgrade}"
                        estimated_cost = self.cost_optimizer.estimate_cost(v, 1000, 500)
                        break

        # 7. 记录路由决策
        routing_result = {
            "model_key": model_key,
            "model_config": model_config,
            "complexity": complexity,
            "confidence": confidence,
            "reason": reason,
            "estimated_cost": estimated_cost,
            "analysis": analysis,
            "budget_status": budget_status,
        }

        self._routing_history.append({
            "timestamp": time.time(),
            "task_preview": task[:100],
            "complexity": complexity.value,
            "model": model_key,
            "reason": reason,
            "estimated_cost": estimated_cost,
        })

        return routing_result

    def get_routing_history(self) -> List[Dict[str, Any]]:
        """Get routing history"""
        return self._routing_history

    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics"""
        if not self._routing_history:
            return {"total_routes": 0}

        complexity_counts = {}
        model_counts = {}
        total_cost = 0

        for entry in self._routing_history:
            complexity_counts[entry["complexity"]] = complexity_counts.get(entry["complexity"], 0) + 1
            model_counts[entry["model"]] = model_counts.get(entry["model"], 0) + 1
            total_cost += entry["estimated_cost"]

        return {
            "total_routes": len(self._routing_history),
            "complexity_distribution": complexity_counts,
            "model_distribution": model_counts,
            "total_estimated_cost": total_cost,
            "avg_cost_per_route": total_cost / len(self._routing_history),
            "budget_status": self.cost_optimizer.get_budget_status(),
        }


# ─── Convenience Functions ────────────────────────────────────────────────

_default_router: Optional[SmartRouter] = None


def get_router(
    monthly_budget: float = 50.0,
    prefer_local: bool = False,
) -> SmartRouter:
    """Get or create the default smart router"""
    global _default_router
    if _default_router is None:
        _default_router = SmartRouter(
            monthly_budget=monthly_budget,
            prefer_local=prefer_local,
        )
    return _default_router


def route_task(task: str, **kwargs) -> Dict[str, Any]:
    """Convenience function to route a task"""
    router = get_router()
    return router.route(task, **kwargs)


def get_optimal_model(task: str, **kwargs) -> Tuple[str, ModelConfig]:
    """Get the optimal model for a task"""
    result = route_task(task, **kwargs)
    return result["model_key"], result["model_config"]


# ─── CLI Test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    router = SmartRouter(monthly_budget=50.0)

    test_tasks = [
        "Format this Python file",
        "Implement a REST API with authentication",
        "Design a microservice architecture for e-commerce",
        "Fix this typo in the README",
        "Write unit tests for the payment module",
        "Audit this code for security vulnerabilities",
        "Explain what this function does",
        "Refactor this class to use dependency injection",
    ]

    print("=" * 70)
    print("SMART ROUTER TEST")
    print("=" * 70)

    for task in test_tasks:
        result = router.route(task)
        print(f"\nTask: {task[:50]}...")
        print(f"  Complexity: {result['complexity'].value}")
        print(f"  Model: {result['model_key']}")
        print(f"  Reason: {result['reason']}")
        print(f"  Est. Cost: ${result['estimated_cost']:.4f}")

    print("\n" + "=" * 70)
    print("ROUTING STATS")
    print("=" * 70)
    stats = router.get_stats()
    print(json.dumps(stats, indent=2, default=str))
