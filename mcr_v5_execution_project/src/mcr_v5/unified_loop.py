from __future__ import annotations

import uuid

from mcr_v5.cognitive_bridge import CognitiveBridge
from mcr_v5.cognitive_loop import CognitiveLoop
from mcr_v5.core import LoopContext
from mcr_v5.environment_monitor import EnvironmentMonitor
from mcr_v5.evolution import EvolutionEngine
from mcr_v5.failure_analyzer import FailureAnalyzer
from mcr_v5.global_workspace import GlobalWorkspace
from mcr_v5.goal_generator import GoalGenerator
from mcr_v5.homeostasis import Homeostasis
from mcr_v5.immune_system import ImmuneSystem
from mcr_v5.opportunity_detector import OpportunityDetector
from mcr_v5.pattern_detector import PatternDetector
from mcr_v5.provenance import ProvenanceRecorder
from mcr_v5.self_correction import SelfCorrection
from mcr_v5.sleep_consolidator import SleepConsolidator
from mcr_v5.task_engine import TaskEngine


class UnifiedLoopV5:
    def __init__(self) -> None:
        self.environment_monitor = EnvironmentMonitor()
        self.cognitive_bridge = CognitiveBridge()
        self.opportunity_detector = OpportunityDetector()
        self.goal_generator = GoalGenerator()
        self.task_engine = TaskEngine()
        self.provenance = ProvenanceRecorder()
        self.failure_analyzer = FailureAnalyzer()
        self.pattern_detector = PatternDetector()
        self.immune_system = ImmuneSystem()
        self.self_correction = SelfCorrection()
        self.cognitive_loop = CognitiveLoop()
        self.global_workspace = GlobalWorkspace()
        self.homeostasis = Homeostasis()
        self.evolution = EvolutionEngine()
        self.sleep = SleepConsolidator()

    def run_once(self) -> dict:
        ctx = LoopContext(cycle_id=f"cycle_{uuid.uuid4().hex[:8]}")

        # Step 1: 环境扫描
        environment = self.environment_monitor.scan(ctx)
        ctx.step("step_01_environment_scan", "感觉系统", True, environment)

        # Step 2: 世界模型
        world_model = self.cognitive_bridge.build_world_model(ctx, environment)
        ctx.step("step_02_world_model", "神经系统", True, world_model)

        # Step 3: 机会检测
        opportunities = self.opportunity_detector.detect(ctx, world_model)
        ctx.step("step_03_opportunity_detection", "感觉系统", True, {"count": len(opportunities)})

        # Step 4: 目标生成
        goals = self.goal_generator.generate(ctx, opportunities)
        ctx.step("step_04_goal_generation", "自主神经系统", True, {"count": len(goals)})

        # Step 5: 任务执行
        task_results = self.task_engine.execute(ctx, goals)
        ctx.step("step_05_task_execution", "执行系统", True, {"count": len(task_results)})

        # Step 6: 溯源记录
        self.provenance.record(ctx, {"task_results": task_results})
        ctx.step("step_06_provenance", "循环系统", True, {"recorded": True})

        # Step 7: 失败分析
        failures = self.failure_analyzer.analyze(ctx, task_results)
        ctx.step("step_07_failure_analysis", "免疫系统", True, {"count": len(failures)})

        # Step 8: 模式检测
        patterns = self.pattern_detector.detect(ctx)
        ctx.step("step_08_pattern_detection", "免疫系统", True, {"count": len(patterns)})

        # Step 9: 免疫巡逻
        immune_report = self.immune_system.patrol(ctx)
        ctx.step("step_09_immune_patrol", "免疫系统", True, immune_report)

        # Step 10: 自修复
        patches = self.self_correction.repair(ctx, immune_report)
        ctx.step("step_10_self_repair", "免疫系统", True, {"patches": len(patches)})

        # Step 11: 认知反思
        reflection = self.cognitive_loop.reflect(ctx)
        ctx.step("step_11_cognitive_reflection", "神经系统", True, reflection)

        # Step 12: 全局广播
        signal = self.global_workspace.broadcast(ctx, reflection)
        ctx.step("step_12_global_broadcast", "内分泌系统", True, signal)

        # Step 13: 稳态调节
        policy = self.homeostasis.regulate(ctx, signal)
        ctx.step("step_13_homeostasis", "稳态系统", True, policy)

        # Step 14: 技能进化
        skills = self.evolution.evolve(ctx, failures, patterns)
        ctx.step("step_14_skill_evolution", "进化系统", True, {"skills": len(skills)})

        # Step 15: Sleep 巩固
        memory = self.sleep.consolidate(ctx)
        ctx.step("step_15_sleep_consolidation", "记忆系统", True, memory)

        return {
            "cycle_id": ctx.cycle_id,
            "status": "ok",
            "events": [event.__dict__ for event in ctx.events],
            "steps": ctx.steps,
            "failures": ctx.failures,
            "skills": ctx.skills,
        }
