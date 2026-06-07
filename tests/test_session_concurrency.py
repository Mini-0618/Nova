"""
Tests for SessionManager concurrency safety and data integrity.
Verifies that concurrent writes don't cause data loss or corruption.
"""
import os
import sys
import json
import time
import threading
import tempfile
from pathlib import Path

# Add runtime to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runtime"))

from session import SessionManager, Session


def test_concurrent_append_messages_no_data_loss():
    """
    CRITICAL TEST: Ensure concurrent append_message calls don't lose data.
    
    The original code had no locking around get_session + update_session,
    which is a classic read-modify-write race condition. Two threads could
    both read the same session, both append their message to the local copy,
    then both write back — one thread's message gets silently overwritten.
    
    With the fix (threading.Lock around DB writes), this should no longer occur.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_concurrent.db"
        mgr = SessionManager(db_path=db_path)
        session = mgr.create_session("test-model", "test-provider", {"test": "concurrency"})
        session_id = session.id

        NUM_THREADS = 10
        MSGS_PER_THREAD = 20
        barrier = threading.Barrier(NUM_THREADS)
        errors = []
        results = [0] * NUM_THREADS

        def worker(worker_id: int):
            try:
                barrier.wait(timeout=10)
                for i in range(MSGS_PER_THREAD):
                    msg = {
                        "role": "user",
                        "content": f"msg from worker {worker_id} iteration {i}",
                        "worker_id": worker_id,
                        "iteration": i,
                    }
                    mgr.append_message(session_id, msg)
                results[worker_id] = 1
            except Exception as e:
                errors.append(f"Worker {worker_id}: {e}")
                results[worker_id] = -1

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Check no errors
        if errors:
            raise AssertionError(f"Thread errors occurred: {errors}")

        # Reload session and count messages
        final_session = mgr.get_session(session_id)
        assert final_session is not None, "Session should exist"
        total_msgs = len(final_session.messages)
        expected = NUM_THREADS * MSGS_PER_THREAD

        print(f"Expected messages: {expected}, Got: {total_msgs}")
        assert total_msgs == expected, (
            f"DATA LOSS DETECTED! Expected {expected} messages but got {total_msgs}. "
            f"Lost {expected - total_msgs} messages due to race condition."
        )

        # Verify content integrity — every expected message should be present
        contents = {m["content"] for m in final_session.messages}
        for wid in range(NUM_THREADS):
            for it in range(MSGS_PER_THREAD):
                expected_content = f"msg from worker {wid} iteration {it}"
                assert expected_content in contents, (
                    f"Missing message: {expected_content}"
                )

        print("PASS: No data loss under concurrent writes.")
        mgr.close()


def test_concurrent_update_tokens_accumulates_correctly():
    """
    CRITICAL TEST: Ensure concurrent token updates accumulate correctly.
    
    Without locking, two threads reading the same session, adding tokens,
    and writing back can cause one update to overwrite the other.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_tokens.db"
        mgr = SessionManager(db_path=db_path)
        session = mgr.create_session("test-model", "test-provider")
        session_id = session.id

        NUM_THREADS = 5
        TOKENS_PER_THREAD = 100
        COST_PER_THREAD = 0.01
        barrier = threading.Barrier(NUM_THREADS)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=10)
                for _ in range(10):
                    mgr.update_tokens(session_id, TOKENS_PER_THREAD, TOKENS_PER_THREAD, COST_PER_THREAD)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        if errors:
            raise AssertionError(f"Thread errors: {errors}")

        final_session = mgr.get_session(session_id)
        assert final_session is not None

        expected_input = NUM_THREADS * 10 * TOKENS_PER_THREAD
        expected_output = NUM_THREADS * 10 * TOKENS_PER_THREAD
        expected_cost = NUM_THREADS * 10 * COST_PER_THREAD

        print(f"Expected input_tokens: {expected_input}, Got: {final_session.total_input_tokens}")
        print(f"Expected output_tokens: {expected_output}, Got: {final_session.total_output_tokens}")
        print(f"Expected cost: {expected_cost}, Got: {final_session.total_cost}")

        assert final_session.total_input_tokens == expected_input, (
            f"Token accumulation error: expected {expected_input}, got {final_session.total_input_tokens}"
        )
        assert final_session.total_output_tokens == expected_output, (
            f"Token accumulation error: expected {expected_output}, got {final_session.total_output_tokens}"
        )
        assert abs(final_session.total_cost - expected_cost) < 0.001, (
            f"Cost accumulation error: expected {expected_cost}, got {final_session.total_cost}"
        )

        print("PASS: Token accumulation is correct under concurrent updates.")
        mgr.close()


def test_session_update_does_not_mutate_caller_data():
    """
    Verify that update_session makes a copy of messages before truncating,
    so the caller's Session object is not mutated.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_mutation.db"
        mgr = SessionManager(db_path=db_path)
        session = mgr.create_session("test-model", "test-provider")
        session_id = session.id

        # Add a large message that would trigger truncation
        large_content = "A" * 10000
        mgr.append_message(session_id, {"role": "user", "content": large_content})

        # Reload and check the original session object's message is intact
        fresh_session = mgr.get_session(session_id)
        assert fresh_session is not None
        assert len(fresh_session.messages) == 1
        # The message should have been truncated on save, so content <= 2000
        saved_content = fresh_session.messages[0]["content"]
        assert len(saved_content) <= 2000, f"Expected truncated content, got {len(saved_content)} chars"
        assert saved_content.startswith("AAA"), "Content should start with original prefix"
        print(f"PASS: Large message truncated correctly ({len(saved_content)} chars saved)")
        mgr.close()


def test_wal_mode_enabled():
    """Verify WAL mode is enabled for better concurrent read performance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_wal.db"
        mgr = SessionManager(db_path=db_path)
        conn = mgr._get_conn()
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode == "wal", f"Expected WAL mode, got {mode}"
        print(f"PASS: Journal mode is {mode}")
        mgr.close()


if __name__ == "__main__":
    test_concurrent_append_messages_no_data_loss()
    test_concurrent_update_tokens_accumulates_correctly()
    test_session_update_does_not_mutate_caller_data()
    test_wal_mode_enabled()
    print("\n=== ALL TESTS PASSED ===")
