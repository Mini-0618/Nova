"""Test that append_message only truncates oversized messages, not all messages."""
import sys
import os
import tempfile
import json

# Use a temp DB to avoid polluting the real one
os.environ["CODEX_DATA"] = tempfile.mkdtemp()

from runtime.session import SessionManager

def test_append_message_selective_truncation():
    """Verify that only the oversized message is truncated, others remain intact."""
    # Use a unique temp DB
    tmp_dir = tempfile.mkdtemp()
    from pathlib import Path
    db_path = Path(tmp_dir) / "test_sessions.db"
    
    mgr = SessionManager(db_path=db_path)
    try:
        s = mgr.create_session("test-model", "test-provider")
        
        # Add several normal-sized messages
        mgr.append_message(s.id, {"role": "user", "content": "Hello!"})
        mgr.append_message(s.id, {"role": "assistant", "content": "Hi there! How can I help?"})
        mgr.append_message(s.id, {"role": "user", "content": "What's 2+2?"})
        mgr.append_message(s.id, {"role": "assistant", "content": "4"})
        
        # Now add one oversized message (>5000 chars when serialized)
        oversized_content = "A" * 8000
        mgr.append_message(s.id, {"role": "user", "content": oversized_content})
        
        # Add more normal messages after
        mgr.append_message(s.id, {"role": "assistant", "content": "The answer is 4."})
        mgr.append_message(s.id, {"role": "user", "content": "Thanks!"})
        
        # Retrieve and check
        session = mgr.get_session(s.id)
        messages = session.messages
        
        print(f"Total messages: {len(messages)}")
        for i, m in enumerate(messages):
            truncated_flag = " [TRUNCATED]" if m.get("truncated") else ""
            content_preview = (m.get("content") or "")[:60]
            print(f"  [{i}] role={m.get('role')}, content_len={len(m.get('content',''))}, truncated={m.get('truncated', False)}{truncated_flag}")
        
        # Assertions
        assert len(messages) == 7, f"Expected 7 messages, got {len(messages)}"
        
        # The oversized message (index 4) should be truncated
        oversized_msg = messages[4]
        assert oversized_msg.get("truncated") is True, "Oversized message should be marked truncated"
        assert len(oversized_msg.get("content", "")) <= 2000, f"Oversized message content should be <= 2000 chars, got {len(oversized_msg.get('content', ''))}"
        
        # All other messages should NOT be truncated and should have their full content
        for i in [0, 1, 2, 3, 5, 6]:
            msg = messages[i]
            assert msg.get("truncated") is not True, f"Message [{i}] should NOT be truncated"
        
        # Check specific content preservation
        assert messages[0]["content"] == "Hello!", f"Message 0 content should be 'Hello!', got '{messages[0]['content']}'"
        assert messages[1]["content"] == "Hi there! How can I help?", f"Message 1 content mismatch"
        assert messages[2]["content"] == "What's 2+2?", f"Message 2 content mismatch"
        assert messages[3]["content"] == "4", f"Message 3 content mismatch"
        assert messages[5]["content"] == "The answer is 4.", f"Message 5 content mismatch"
        assert messages[6]["content"] == "Thanks!", f"Message 6 content mismatch"
        
        print("\n✅ PASS: Only the oversized message was truncated. All other messages preserved intact.")
        
    finally:
        mgr.close()
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_update_session_selective_truncation():
    """Verify that update_session also only truncates oversized messages."""
    tmp_dir = tempfile.mkdtemp()
    from pathlib import Path
    db_path = Path(tmp_dir) / "test_sessions.db"
    
    mgr = SessionManager(db_path=db_path)
    try:
        s = mgr.create_session("test-model", "test-provider")
        
        # Build messages list manually with one oversized
        s.messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "A" * 8000},  # oversized
            {"role": "assistant", "content": "Sure, let me help."},
        ]
        
        mgr.update_session(s)
        
        session = mgr.get_session(s.id)
        messages = session.messages
        
        print(f"\nTotal messages after update_session: {len(messages)}")
        for i, m in enumerate(messages):
            truncated_flag = " [TRUNCATED]" if m.get("truncated") else ""
            print(f"  [{i}] role={m.get('role')}, content_len={len(m.get('content',''))}, truncated={m.get('truncated', False)}{truncated_flag}")
        
        assert len(messages) == 4, f"Expected 4 messages, got {len(messages)}"
        
        # Message 2 (oversized) should be truncated
        assert messages[2].get("truncated") is True, "Oversized message should be truncated"
        assert len(messages[2].get("content", "")) <= 2000
        
        # Others should be intact
        assert messages[0]["content"] == "Hello!"
        assert messages[1]["content"] == "Hi there!"
        assert messages[3]["content"] == "Sure, let me help."
        
        print("\n✅ PASS: update_session also correctly truncates only oversized messages.")
        
    finally:
        mgr.close()
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_append_message_selective_truncation()
    test_update_session_selective_truncation()
    print("\n🎉 All tests passed!")
