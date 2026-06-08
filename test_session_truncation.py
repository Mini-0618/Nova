"""Test that append_message only truncates the oversized message, not all messages."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use a temp DB
import tempfile
import json

tmpdir = tempfile.mkdtemp()
os.environ["CODEX_DATA"] = tmpdir

# Force reimport
import runtime.session as session_mod
import importlib
importlib.reload(session_mod)

from runtime.session import SessionManager

m = SessionManager()

# Create a session
s = m.create_session("test-model", "test-provider", {"task": "test"})
print(f"Created session: {s.id}")

# Add a small message
m.append_message(s.id, {"role": "user", "content": "hello"})

# Add a large message (>5000 chars)
large_content = "x" * 6000
m.append_message(s.id, {"role": "user", "content": large_content})

# Add another small message
m.append_message(s.id, {"role": "user", "content": "world"})

# Retrieve session
s2 = m.get_session(s.id)
print(f"Total messages: {len(s2.messages)}")

for i, msg in enumerate(s2.messages):
    content_len = len(msg.get("content", ""))
    truncated = msg.get("truncated", False)
    print(f"  Message {i}: role={msg['role']}, content_len={content_len}, truncated={truncated}")

# Verify
assert len(s2.messages) == 3, f"Expected 3 messages, got {len(s2.messages)}"
assert s2.messages[0]["content"] == "hello", f"First message should be 'hello', got {s2.messages[0]['content']}"
assert s2.messages[1].get("truncated") == True, "Large message should be truncated"
assert len(s2.messages[1]["content"]) == 2000, f"Large message content should be 2000 chars, got {len(s2.messages[1]['content'])}"
assert s2.messages[2]["content"] == "world", f"Third message should be 'world', got {s2.messages[2]['content']}"
assert s2.messages[2].get("truncated") is not True, "Small message should NOT be truncated"

print("\n✓ PASS: Only the oversized message was truncated, others kept intact.")
m.close()

# Cleanup
import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
