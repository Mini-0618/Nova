"""
Tests for ParallelCodexLoop
Verifies parallel execution, failure isolation, and result aggregation.
"""

import sys
sys.path.insert(0, r'D:\codex-local')

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from runtime.parallel_loop import (
    ParallelCodexLoop, ParallelConfig, ParallelTask, TaskStatus,
    run_parallel,
)
from runtime.loop import LoopConfig


# ─── Helpers ──────────────────────────────────────────────────────────────

def make_config(**kwargs):
    """Create a ParallelConfig for testing."""
    defaults = {
        "max_workers": 3,
        "timeout_per_task": 30.0,
        "default_loop_config": LoopConfig(model="test-model"),
    }
    defaults.update(kwargs)
    return ParallelConfig(**defaults)


# ─── Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parallel_execute_three_tasks():
    """Three tasks should all complete and produce results."""
    config = make_config()
    engine = ParallelCodexLoop(config)

    call_count = 0
    original_execute = ParallelCodexLoop._execute_task

    async def mock_execute(self_inner, task: ParallelTask):
        """Simulate task execution without calling LLM."""
        nonlocal call_count
        call_count += 1
        task.status = TaskStatus.RUNNING
        task.start_time = asyncio.get_event_loop().time()
        await asyncio.sleep(0.05)  # simulate work
        task.result = f"result_{task.id}"
        task.status = TaskStatus.COMPLETED
        task.end_time = asyncio.get_event_loop().time()
        with self_inner._lock:
            self_inner.total_tasks_completed += 1
        self_inner._notify("task_completed", task.to_dict())

    with patch.object(ParallelCodexLoop, '_execute_task', mock_execute):
        ids = await engine.submit_tasks(["task A", "task B", "task C"])
        assert len(ids) == 3

        await engine.run(wait_for_completion=True)

    assert call_count == 3
    assert engine.total_tasks_completed == 3
    assert engine.total_tasks_failed == 0

    for tid in ids:
        task = engine.get_task(tid)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.result == f"result_{tid}"


@pytest.mark.asyncio
async def test_one_failure_does_not_affect_others():
    """If one task fails, the other tasks should still complete."""
    config = make_config()
    engine = ParallelCodexLoop(config)

    async def mock_execute(self_inner, task: ParallelTask):
        task.status = TaskStatus.RUNNING
        task.start_time = asyncio.get_event_loop().time()
        await asyncio.sleep(0.05)

        if "fail" in task.task_description:
            task.error = "Simulated failure"
            task.status = TaskStatus.FAILED
            task.end_time = asyncio.get_event_loop().time()
            with self_inner._lock:
                self_inner.total_tasks_failed += 1
            self_inner._notify("task_error", {"task_id": task.id, "error": task.error})
        else:
            task.result = f"ok_{task.id}"
            task.status = TaskStatus.COMPLETED
            task.end_time = asyncio.get_event_loop().time()
            with self_inner._lock:
                self_inner.total_tasks_completed += 1
            self_inner._notify("task_completed", task.to_dict())

    with patch.object(ParallelCodexLoop, '_execute_task', mock_execute):
        # Disable retry so the failed task doesn't get retried
        config.retry_failed_tasks = False
        engine.config = config

        ids = await engine.submit_tasks(["do something", "fail this one", "do another"])
        await engine.run(wait_for_completion=True)

    assert engine.total_tasks_completed == 2
    assert engine.total_tasks_failed == 1

    failed_tasks = engine.get_tasks(status=TaskStatus.FAILED)
    assert len(failed_tasks) == 1
    assert "fail" in failed_tasks[0].task_description

    completed_tasks = engine.get_tasks(status=TaskStatus.COMPLETED)
    assert len(completed_tasks) == 2


@pytest.mark.asyncio
async def test_result_aggregation():
    """get_stats() and get_progress() should aggregate results correctly."""
    config = make_config()
    engine = ParallelCodexLoop(config)

    completed_count = 0

    async def mock_execute(self_inner, task: ParallelTask):
        nonlocal completed_count
        task.status = TaskStatus.RUNNING
        task.start_time = asyncio.get_event_loop().time()
        await asyncio.sleep(0.02)
        task.result = f"done_{task.id}"
        task.status = TaskStatus.COMPLETED
        task.end_time = asyncio.get_event_loop().time()
        completed_count += 1
        with self_inner._lock:
            self_inner.total_tasks_completed += 1
        self_inner._notify("task_completed", task.to_dict())

    with patch.object(ParallelCodexLoop, '_execute_task', mock_execute):
        ids = await engine.submit_tasks(["t1", "t2", "t3", "t4", "t5"])
        await engine.run(wait_for_completion=True)

    assert completed_count == 5

    stats = engine.get_stats()
    assert stats["total_submitted"] == 5
    assert stats["total_completed"] == 5
    assert stats["total_failed"] == 0
    assert stats["duration"] >= 0

    progress = engine.get_progress()
    assert progress["total"] == 5
    assert progress["completed"] == 5
    assert progress["failed"] == 0
    assert progress["remaining"] == 0
    assert progress["progress_percent"] == 100.0


@pytest.mark.asyncio
async def test_task_status_transitions():
    """A task should go through PENDING -> RUNNING -> COMPLETED/FAILED."""
    config = make_config()
    engine = ParallelCodexLoop(config)

    async def mock_execute(self_inner, task: ParallelTask):
        # Verify it was PENDING when we start
        assert task.status == TaskStatus.PENDING or task.status == TaskStatus.RUNNING
        task.status = TaskStatus.RUNNING
        task.start_time = asyncio.get_event_loop().time()
        await asyncio.sleep(0.01)
        task.result = "ok"
        task.status = TaskStatus.COMPLETED
        task.end_time = asyncio.get_event_loop().time()
        with self_inner._lock:
            self_inner.total_tasks_completed += 1

    with patch.object(ParallelCodexLoop, '_execute_task', mock_execute):
        ids = await engine.submit_tasks(["test task"])
        task = engine.get_task(ids[0])
        assert task.status == TaskStatus.PENDING

        await engine.run(wait_for_completion=True)

        task = engine.get_task(ids[0])
        assert task.status == TaskStatus.COMPLETED
        assert task.duration >= 0


@pytest.mark.asyncio
async def test_get_tasks_with_filter():
    """get_tasks(status=...) should filter correctly."""
    config = make_config(retry_failed_tasks=False)
    engine = ParallelCodexLoop(config)

    async def mock_execute(self_inner, task: ParallelTask):
        task.status = TaskStatus.RUNNING
        task.start_time = asyncio.get_event_loop().time()
        await asyncio.sleep(0.02)
        if "bad" in task.task_description:
            task.error = "fail"
            task.status = TaskStatus.FAILED
            task.end_time = asyncio.get_event_loop().time()
            with self_inner._lock:
                self_inner.total_tasks_failed += 1
        else:
            task.result = "ok"
            task.status = TaskStatus.COMPLETED
            task.end_time = asyncio.get_event_loop().time()
            with self_inner._lock:
                self_inner.total_tasks_completed += 1

    with patch.object(ParallelCodexLoop, '_execute_task', mock_execute):
        await engine.submit_tasks(["good1", "bad task", "good2"])
        await engine.run(wait_for_completion=True)

    assert len(engine.get_tasks(status=TaskStatus.COMPLETED)) == 2
    assert len(engine.get_tasks(status=TaskStatus.FAILED)) == 1
    assert len(engine.get_tasks()) == 3  # all tasks


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
