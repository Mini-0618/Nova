"""Test 5: Session create/save/read"""
import sys
sys.path.insert(0, r'D:\codex-local')

from runtime.session import SessionManager
import tempfile
import os

def test_session_create():
    db = tempfile.mktemp(suffix=".db")
    mgr = SessionManager(db_path=db)

    s = mgr.create_session("deepseek-chat", "deepseek", {"test": True})
    assert s.id.startswith("sess_"), f"id={s.id}"
    assert s.model == "deepseek-chat"
    assert s.status == "active"

    # Read back
    s2 = mgr.get_session(s.id)
    assert s2 is not None, "session not found"
    assert s2.id == s.id

    # Close connection before delete
    mgr._conn.close()
    mgr._conn = None

    os.unlink(db)
    print("PASS: session create/save/read")

if __name__ == "__main__":
    test_session_create()