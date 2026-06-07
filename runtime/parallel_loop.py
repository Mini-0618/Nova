"""
Parallel Codex Loop Engine
Supports running multiple CodexLoop instances in parallel for concurrent task execution.
"""

import os
import json
import asyncio
import threading
import time
import traceback
from typing import Optional, Dict, Any, List, Callable, Coroutine
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum

from runtime.loop import CodexLoop, LoopConfig, _estimate_cost
from runtime.session import SessionManager, get_manager, Session


# ─── Task Status ──────────────────────────────────────────────────────────

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ParallelTask:
    """Represents a task to be executed in parallel"""
    id: str
    task_description: str
    config: Optional[LoopConfig] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    iterations: int = 0
    tokens_used: int = 0

    @property
    def duration(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return time.time() - self.start_time
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task_description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "session_id": self.session_id,
            "duration": self.duration,
            "iterations": self.iterations,
            "tokens_used": self.tokens_used,
        }


# ─── Parallel Loop Configuration ─────────────────────────────────────────

@dataclass
class ParallelConfig:
    """Configuration for parallel execution"""
    max_workers: int = 4
    max_concurrent_tasks: int = 8
    default_loop_config: Optional[LoopConfig] = None
    timeout_per_task: float = 600.0  # 10 minutes per task
    retry_failed_tasks: bool = True
    max_retries: int = 2
    on_task_complete: Optional[Callable[[ParallelTask], None]] = None
    on_task_error: Optional[Callable[[ParallelTask, Exception], None]] = None


# ─── Parallel Codex Loop ─────────────────────────────────────────────────

class ParallelCodexLoop:
    """
    Manages multiple CodexLoop instances running in parallel.

    Features:
    - Concurrent task execution with configurable parallelism
    - Task queue with priority support
    - Automatic retry on failure
    - Progress tracking and callbacks
    - Resource management
    """

    def __init__(self, config: Optional[ParallelConfig] = None):
        self.config = config or ParallelConfig()
        self.tasks: Dict[str, ParallelTask] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        self._running = False
        self._listeners: List[Callable] = []
        self._lock = threading.Lock()

        # Statistics
        self.total_tasks_submitted = 0
        self.total_tasks_completed = 0
        self.total_tasks_failed = 0
        self.total_tokens_used = 0
        self.start_time: Optional[float] = None

    def add_listener(self, cb: Callable):
        """Add event listener"""
        self._listeners.append(cb)

    def _notify(self, event: str, data: Dict[str, Any]):
        """Notify listeners of event"""
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    async def submit_task(self, task_description: str,
                          task_id: Optional[str] = None,
                          config: Optional[LoopConfig] = None,
                          priority: int = 0) -> str:
        """
        Submit a task for parallel execution.

        Args:
            task_description: The task to execute
            task_id: Optional task ID (auto-generated if not provided)
            config: Optional LoopConfig override for this task
            priority: Task priority (higher = more urgent)

        Returns:
            Task ID
        """
        if not task_id:
            task_id = f"task_{int(time.time() * 1000)}_{self.total_tasks_submitted}"

        task = ParallelTask(
            id=task_id,
            task_description=task_description,
            config=config or self.config.default_loop_config or LoopConfig(),
        )

        with self._lock:
            self.tasks[task_id] = task
            self.total_tasks_submitted += 1

        # Put task in queue with priority (negative for min-heap behavior)
        await self.task_queue.put((-priority, task_id, task))

        self._notify("task_submitted", {"task_id": task_id, "task": task_description})

        return task_id

    async def submit_tasks(self, task_descriptions: List[str],
                           configs: Optional[List[LoopConfig]] = None,
                           priority: int = 0) -> List[str]:
        """
        Submit multiple tasks for parallel execution.

        Args:
            task_descriptions: List of tasks to execute
            configs: Optional list of LoopConfig overrides
            priority: Base priority for all tasks

        Returns:
            List of task IDs
        """
        task_ids = []
        for i, desc in enumerate(task_descriptions):
            config = configs[i] if configs and i < len(configs) else None
            task_id = await self.submit_task(desc, config=config, priority=priority)
            task_ids.append(task_id)
        return task_ids

    async def _execute_task(self, task: ParallelTask) -> None:
        """Execute a single task"""
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()

        self._notify("task_started", {"task_id": task.id})

        try:
            loop = CodexLoop(task.config)

            # Add listener to track iterations
            def on_iteration(msg, data):
                if msg == "iteration":
                    task.iterations += 1
                    task.tokens_used = loop.total_tokens_used

            loop.add_listener(on_iteration)

            # Run the task
            result = await loop.run_task(task.task_description)

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.end_time = time.time()
            task.session_id = loop._current_session.id if loop._current_session else None
            task.tokens_used = loop.total_tokens_used

            with self._lock:
                self.total_tasks_completed += 1
                self.total_tokens_used += task.tokens_used

            self._notify("task_completed", task.to_dict())

            # Call completion callback
            if self.config.on_task_complete:
                self.config.on_task_complete(task)

        except Exception as e:
            task.error = f"{type(e).__name__}: {str(e)}"
            task.status = TaskStatus.FAILED
            task.end_time = time.time()

            with self._lock:
                self.total_tasks_failed += 1

            self._notify("task_error", {"task_id": task.id, "error": task.error})

            # Call error callback
            if self.config.on_task_error:
                self.config.on_task_error(task, e)

            # Retry if configured
            if self.config.retry_failed_tasks and task.iterations < self.config.max_retries:
                self._notify("task_retry", {"task_id": task.id, "attempt": task.iterations + 1})
                await self._execute_task(task)

    async def _worker(self, worker_id: int):
        """Worker coroutine that processes tasks from the queue"""
        while self._running:
            try:
                # Get task from queue with timeout
                priority, task_id, task = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0
                )

                # Execute task with timeout
                try:
                    await asyncio.wait_for(
                        self._execute_task(task),
                        timeout=self.config.timeout_per_task
                    )
                except asyncio.TimeoutError:
                    task.error = f"Task timed out after {self.config.timeout_per_task}s"
                    task.status = TaskStatus.FAILED
                    task.end_time = time.time()
                    self._notify("task_timeout", {"task_id": task.id})

                self.task_queue.task_done()

            except asyncio.TimeoutError:
                # No task available, continue
                continue
            except Exception as e:
                traceback.print_exc()

    async def run(self, wait_for_completion: bool = True) -> None:
        """
        Start the parallel loop engine.

        Args:
            wait_for_completion: If True, wait for all tasks to complete
        """
        self._running = True
        self.start_time = time.time()

        self._notify("engine_started", {"max_workers": self.config.max_workers})

        # Start workers
        workers = []
        for i in range(self.config.max_workers):
            worker = asyncio.create_task(self._worker(i))
            workers.append(worker)

        if wait_for_completion:
            # Wait for all tasks to be processed
            await self.task_queue.join()

            # Stop workers
            self._running = False
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            self._notify("engine_stopped", self.get_stats())

    async def stop(self) -> None:
        """Stop the parallel loop engine"""
        self._running = False

        # Cancel running tasks
        for task_id, async_task in self.running_tasks.items():
            async_task.cancel()

        self._notify("engine_stopped", self.get_stats())

    def get_task(self, task_id: str) -> Optional[ParallelTask]:
        """Get task by ID"""
        return self.tasks.get(task_id)

    def get_tasks(self, status: Optional[TaskStatus] = None) -> List[ParallelTask]:
        """Get all tasks, optionally filtered by status"""
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics"""
        duration = time.time() - self.start_time if self.start_time else 0

        status_counts = {}
        for status in TaskStatus:
            count = len([t for t in self.tasks.values() if t.status == status])
            status_counts[status.value] = count

        return {
            "total_submitted": self.total_tasks_submitted,
            "total_completed": self.total_tasks_completed,
            "total_failed": self.total_tasks_failed,
            "total_tokens_used": self.total_tokens_used,
            "duration": duration,
            "status_counts": status_counts,
            "queue_size": self.task_queue.qsize(),
            "is_running": self._running,
        }

    def get_progress(self) -> Dict[str, Any]:
        """Get current progress"""
        total = self.total_tasks_submitted
        completed = self.total_tasks_completed
        failed = self.total_tasks_failed

        if total == 0:
            progress = 0.0
        else:
            progress = (completed + failed) / total * 100

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "progress_percent": progress,
            "remaining": total - completed - failed,
        }


# ─── Convenience Functions ────────────────────────────────────────────────

async def run_parallel(tasks: List[str],
                       max_workers: int = 4,
                       configs: Optional[List[LoopConfig]] = None,
                       timeout_per_task: float = 600.0) -> Dict[str, Any]:
    """
    Convenience function to run multiple tasks in parallel.

    Args:
        tasks: List of task descriptions
        max_workers: Maximum number of concurrent workers
        configs: Optional list of LoopConfig overrides
        timeout_per_task: Timeout per task in seconds

    Returns:
        Dictionary with results and statistics
    """
    config = ParallelConfig(
        max_workers=max_workers,
        timeout_per_task=timeout_per_task,
        default_loop_config=LoopConfig(),
    )

    engine = ParallelCodexLoop(config)

    # Submit all tasks
    task_ids = await engine.submit_tasks(tasks, configs=configs)

    # Run and wait for completion
    await engine.run(wait_for_completion=True)

    # Collect results
    results = {}
    for task_id in task_ids:
        task = engine.get_task(task_id)
        if task:
            results[task_id] = task.to_dict()

    return {
        "results": results,
        "stats": engine.get_stats(),
    }


async def run_parallel_with_callback(tasks: List[str],
                                     on_complete: Callable[[ParallelTask], None],
                                     on_error: Optional[Callable[[ParallelTask, Exception], None]] = None,
                                     max_workers: int = 4) -> ParallelCodexLoop:
    """
    Run tasks in parallel with callbacks.

    Args:
        tasks: List of task descriptions
        on_complete: Callback when task completes
        on_error: Callback when task fails
        max_workers: Maximum number of concurrent workers

    Returns:
        ParallelCodexLoop instance (for further inspection)
    """
    config = ParallelConfig(
        max_workers=max_workers,
        on_task_complete=on_complete,
        on_task_error=on_error,
    )

    engine = ParallelCodexLoop(config)
    await engine.submit_tasks(tasks)
    await engine.run(wait_for_completion=True)

    return engine


# ─── Multi-Round Reasoning ───────────────────────────────────────────────

class MultiRoundReasoner:
    """
    Enhances reasoning by running multiple rounds of thinking.

    This implements Chain-of-Thought and multi-round reasoning to improve
    the quality of responses, especially for complex tasks.
    """

    def __init__(self, loop: CodexLoop, num_rounds: int = 3):
        self.loop = loop
        self.num_rounds = num_rounds
        self.thoughts: List[str] = []

    async def reason(self, task: str) -> str:
        """
        Run multi-round reasoning on a task.

        Args:
            task: The task to reason about

        Returns:
            Final synthesized response
        """
        self.thoughts = []

        # Round 1: Initial analysis
        analysis_prompt = f"""Analyze this task in detail. Consider:
1. What exactly needs to be done?
2. What are the key components?
3. What tools or resources are needed?
4. What are potential challenges?

Task: {task}

Provide a detailed analysis."""

        analysis = await self._think(analysis_prompt)
        self.thoughts.append(analysis)

        # Round 2: Planning
        planning_prompt = f"""Based on the analysis, create a detailed step-by-step plan.

Analysis:
{analysis}

Task: {task}

Create a clear, actionable plan with specific steps."""

        plan = await self._think(planning_prompt)
        self.thoughts.append(plan)

        # Round 3: Execution strategy
        execution_prompt = f"""Review the plan and refine the execution strategy.

Analysis:
{analysis}

Plan:
{plan}

Task: {task}

Identify any gaps, risks, or improvements. Provide the final execution strategy."""

        strategy = await self._think(execution_prompt)
        self.thoughts.append(strategy)

        # Synthesize final response
        synthesis_prompt = f"""Synthesize all reasoning into a final response.

Task: {task}

Analysis:
{analysis}

Plan:
{plan}

Strategy:
{strategy}

Provide the final, complete response."""

        final_response = await self._think(synthesis_prompt)

        return final_response

    async def _think(self, prompt: str) -> str:
        """Run a single thinking round"""
        # Use the loop's LLM directly for reasoning
        from runtime.loop import _call_llm_async, _build_messages

        messages = _build_messages(prompt, [], self.loop.config.system_prompt)
        response = await _call_llm_async(
            messages,
            self.loop.config,
            os.environ.get("CODEX_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "",
            self.loop.config.provider,
            self.loop.config.model,
        )

        # Extract text from response
        output = response.get("output", [])
        for item in output:
            if item.get("type") == "message":
                content = item.get("content", [])
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "output_text":
                        return c.get("text", "")

        return ""


# ─── Enhanced Parallel Loop with Reasoning ────────────────────────────────

class EnhancedParallelLoop(ParallelCodexLoop):
    """
    Parallel loop with multi-round reasoning support.

    Each task goes through:
    1. Multi-round reasoning (Chain-of-Thought)
    2. Parallel execution
    3. Result synthesis
    """

    def __init__(self, config: Optional[ParallelConfig] = None,
                 reasoning_rounds: int = 3):
        super().__init__(config)
        self.reasoning_rounds = reasoning_rounds

    async def _execute_task(self, task: ParallelTask) -> None:
        """Execute task with multi-round reasoning"""
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()

        self._notify("task_started", {"task_id": task.id})

        try:
            loop = CodexLoop(task.config)
            reasoner = MultiRoundReasoner(loop, self.reasoning_rounds)

            # First, reason about the task
            self._notify("reasoning_started", {"task_id": task.id, "rounds": self.reasoning_rounds})
            reasoning_result = await reasoner.reason(task.task_description)
            self._notify("reasoning_completed", {"task_id": task.id, "thoughts": reasoner.thoughts})

            # Then execute with enhanced context
            enhanced_task = f"""Task: {task.task_description}

Detailed Reasoning:
{reasoning_result}

Execute this task based on the above reasoning."""

            result = await loop.run_task(enhanced_task)

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.end_time = time.time()
            task.session_id = loop._current_session.id if loop._current_session else None
            task.tokens_used = loop.total_tokens_used

            with self._lock:
                self.total_tasks_completed += 1
                self.total_tokens_used += task.tokens_used

            self._notify("task_completed", task.to_dict())

            if self.config.on_task_complete:
                self.config.on_task_complete(task)

        except Exception as e:
            task.error = f"{type(e).__name__}: {str(e)}"
            task.status = TaskStatus.FAILED
            task.end_time = time.time()

            with self._lock:
                self.total_tasks_failed += 1

            self._notify("task_error", {"task_id": task.id, "error": task.error})

            if self.config.on_task_error:
                self.config.on_task_error(task, e)

            if self.config.retry_failed_tasks and task.iterations < self.config.max_retries:
                self._notify("task_retry", {"task_id": task.id, "attempt": task.iterations + 1})
                await self._execute_task(task)


# ─── CLI Interface ────────────────────────────────────────────────────────

async def main():
    """CLI entry point for parallel loop"""
    import argparse

    parser = argparse.ArgumentParser(description="Parallel Codex Loop")
    parser.add_argument("--tasks", nargs="+", help="Tasks to execute")
    parser.add_argument("--max-workers", type=int, default=4, help="Max concurrent workers")
    parser.add_argument("--timeout", type=float, default=600.0, help="Timeout per task in seconds")
    parser.add_argument("--reasoning-rounds", type=int, default=3, help="Number of reasoning rounds")
    parser.add_argument("--enhanced", action="store_true", help="Use enhanced loop with reasoning")

    args = parser.parse_args()

    if not args.tasks:
        print("No tasks provided. Use --tasks to specify tasks.")
        return

    # Configure
    config = ParallelConfig(
        max_workers=args.max_workers,
        timeout_per_task=args.timeout,
    )

    # Create engine
    if args.enhanced:
        engine = EnhancedParallelLoop(config, reasoning_rounds=args.reasoning_rounds)
    else:
        engine = ParallelCodexLoop(config)

    # Add progress listener
    def on_event(event, data):
        if event == "task_completed":
            print(f"✓ Task completed: {data.get('task_id')}")
        elif event == "task_error":
            print(f"✗ Task failed: {data.get('task_id')} - {data.get('error')}")
        elif event == "task_started":
            print(f"→ Task started: {data.get('task_id')}")

    engine.add_listener(on_event)

    # Submit tasks
    await engine.submit_tasks(args.tasks)

    # Run
    print(f"\nStarting parallel execution with {args.max_workers} workers...")
    print(f"Tasks: {len(args.tasks)}")
    print("-" * 50)

    await engine.run(wait_for_completion=True)

    # Print results
    print("\n" + "=" * 50)
    print("RESULTS")
    print("=" * 50)

    stats = engine.get_stats()
    print(f"Total submitted: {stats['total_submitted']}")
    print(f"Total completed: {stats['total_completed']}")
    print(f"Total failed: {stats['total_failed']}")
    print(f"Total tokens used: {stats['total_tokens_used']}")
    print(f"Duration: {stats['duration']:.1f}s")

    print("\nTask Details:")
    for task in engine.get_tasks():
        status_icon = "✓" if task.status == TaskStatus.COMPLETED else "✗"
        print(f"  {status_icon} [{task.id}] {task.task_description[:50]}...")
        print(f"    Status: {task.status.value}")
        print(f"    Duration: {task.duration:.1f}s")
        if task.error:
            print(f"    Error: {task.error}")


if __name__ == "__main__":
    asyncio.run(main())
