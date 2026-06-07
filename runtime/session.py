"""
Codex-Local Session Manager
SQLite-backed session persistence with crash recovery
"""

import os
import json
import sqlite3
import uuid
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime


DATA_DIR = Path(os.environ.get("CODEX_DATA", "D:/codex-local/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "sessions.db"


@dataclass
class SessionMessage:
    role: str
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    annotations: Optional[List] = None


@dataclass
class Session:
    id: str
    created_at: int
    updated_at: int
    status: str  # active, completed, error
    model: str
    provider: str
    messages: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "model": self.model,
            "provider": self.provider,
            "messages": self.messages,
            "tool_results": self.tool_results,
            "metadata": self.metadata,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost": self.total_cost,
        }


class SessionManager:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=10000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                model TEXT NOT NULL,
                provider TEXT NOT NULL,
                messages TEXT NOT NULL DEFAULT '[]',
                tool_results TEXT NOT NULL DEFAULT '[]',
                metadata TEXT NOT NULL DEFAULT '{}',
                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                total_cost REAL DEFAULT 0.0
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
        """)
        conn.commit()

    def close(self):
        """Close the SQLite connection so Windows can release the DB file."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def create_session(self, model: str, provider: str, metadata: Optional[Dict] = None) -> Session:
        now = int(time.time())
        session = Session(
            id="sess_" + uuid.uuid4().hex[:12],
            created_at=now,
            updated_at=now,
            status="active",
            model=model,
            provider=provider,
            metadata=metadata or {},
        )
        conn = self._get_conn()
        with self._lock:
            conn.execute(
                """INSERT INTO sessions (id, created_at, updated_at, status, model, provider, messages, tool_results, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session.id, session.created_at, session.updated_at, session.status,
                 session.model, session.provider, "[]", "[]", "{}")
            )
            conn.commit()
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        conn = self._get_conn()
        with self._lock:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=row["status"],
            model=row["model"],
            provider=row["provider"],
            messages=json.loads(row["messages"]),
            tool_results=json.loads(row["tool_results"]),
            metadata=json.loads(row["metadata"]),
            total_input_tokens=row["total_input_tokens"],
            total_output_tokens=row["total_output_tokens"],
            total_cost=row["total_cost"],
        )

    @staticmethod
    def _truncate_oversized_messages(msgs: List[Dict]) -> List[Dict]:
        """Truncate only individual messages that exceed the size limit."""
        result = []
        for m in msgs:
            if len(json.dumps(m, ensure_ascii=False)) > 5000:
                result.append({"role": m.get("role"), "content": (m.get("content") or "")[:2000], "truncated": True})
            else:
                result.append(m)
        return result

    def update_session(self, session: Session):
        now = int(time.time())
        session.updated_at = now
        conn = self._get_conn()
        # Truncate oversized messages and tool_results before saving to avoid blob overflow
        # Make a deep copy to avoid mutating the caller's data
        msgs = self._truncate_oversized_messages(list(session.messages))
        tool_res = session.tool_results[-100:]  # keep last 100 only
        with self._lock:
            conn.execute(
                """UPDATE sessions SET
                    updated_at=?, status=?, messages=?, tool_results=?,
                    metadata=?, total_input_tokens=?, total_output_tokens=?, total_cost=?
                   WHERE id=?""",
                (session.updated_at, session.status,
                 json.dumps(msgs, ensure_ascii=False),
                 json.dumps(tool_res, ensure_ascii=False),
                 json.dumps(session.metadata, ensure_ascii=False),
                 session.total_input_tokens, session.total_output_tokens, session.total_cost,
                 session.id)
            )
            conn.commit()

    def append_message(self, session_id: str, message: Dict):
        conn = self._get_conn()
        # Truncate large tool message content to avoid SQLite blob overflow
        msg = dict(message)
        if msg.get("role") == "tool" and msg.get("content"):
            content = msg["content"]
            if len(content) > 10_000:
                msg["content"] = content[:10_000] + f"\n... [truncated {len(content)-10000} chars]"
        with self._lock:
            row = conn.execute("SELECT messages FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                return None
            existing = json.loads(row["messages"])
            existing.append(msg)
            # Only truncate messages that individually exceed the size limit
            msgs = self._truncate_oversized_messages(existing)
            now = int(time.time())
            conn.execute(
                "UPDATE sessions SET messages=?, updated_at=? WHERE id=?",
                (json.dumps(msgs, ensure_ascii=False), now, session_id)
            )
            conn.commit()
        return self.get_session(session_id)

    def append_tool_result(self, session_id: str, tool_result: Dict):
        conn = self._get_conn()
        safe = {
            "iteration": tool_result.get("iteration"),
            "tool": tool_result.get("tool"),
            "args": tool_result.get("args"),
            "success": tool_result.get("success"),
            "timestamp": tool_result.get("timestamp"),
        }
        with self._lock:
            row = conn.execute("SELECT tool_results FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                return None
            existing = json.loads(row["tool_results"])
            existing.append(safe)
            trimmed = existing[-100:]  # keep last 100 only
            now = int(time.time())
            conn.execute(
                "UPDATE sessions SET tool_results=?, updated_at=? WHERE id=?",
                (json.dumps(trimmed, ensure_ascii=False), now, session_id)
            )
            conn.commit()
        return self.get_session(session_id)

    def update_tokens(self, session_id: str, input_tokens: int, output_tokens: int, cost: float):
        conn = self._get_conn()
        with self._lock:
            conn.execute(
                "UPDATE sessions SET total_input_tokens=total_input_tokens+?, total_output_tokens=total_output_tokens+?, total_cost=total_cost+?, updated_at=? WHERE id=?",
                (input_tokens, output_tokens, cost, int(time.time()), session_id)
            )
            conn.commit()
        return self.get_session(session_id)

    def list_sessions(self, limit: int = 50, status: Optional[str] = None) -> List[Session]:
        conn = self._get_conn()
        with self._lock:
            if status:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def delete_session(self, session_id: str):
        conn = self._get_conn()
        with self._lock:
            conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            conn.commit()

    def get_stats(self) -> dict:
        conn = self._get_conn()
        with self._lock:
            row = conn.execute("""
                SELECT COUNT(*) as total, SUM(total_input_tokens) as input_tokens,
                       SUM(total_output_tokens) as output_tokens, SUM(total_cost) as cost
                FROM sessions
            """).fetchone()
        return {
            "total_sessions": row["total"] or 0,
            "total_input_tokens": row["input_tokens"] or 0,
            "total_output_tokens": row["output_tokens"] or 0,
            "total_cost_usd": row["cost"] or 0.0,
        }

    def checkpoint(self, session: Session):
        """Write a checkpoint file for crash recovery."""
        cp_path = DATA_DIR / f".checkpoint_{session.id}.json"
        cp_data = {
            "session": session.to_dict(),
            "checkpoint_at": int(time.time()),
        }
        cp_path.write_text(json.dumps(cp_data, ensure_ascii=False), encoding="utf-8")
        return cp_path

    def recover_from_checkpoint(self) -> Optional[Session]:
        """Find and recover the most recent checkpoint."""
        checkpoints = sorted(DATA_DIR.glob(".checkpoint_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not checkpoints:
            return None
        cp = checkpoints[0]
        data = json.loads(cp.read_text(encoding="utf-8"))
        session_data = data["session"]
        session = Session(**{k: v for k, v in session_data.items() if k in Session.__dataclass_fields__})
        # Re-insert into DB if needed
        existing = self.get_session(session.id)
        if not existing:
            conn = self._get_conn()
            with self._lock:
                conn.execute(
                    """INSERT OR REPLACE INTO sessions
                       (id, created_at, updated_at, status, model, provider, messages, tool_results, metadata,
                        total_input_tokens, total_output_tokens, total_cost)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session.id, session.created_at, session.updated_at, session.status,
                     session.model, session.provider,
                     json.dumps(session.messages), json.dumps(session.tool_results),
                     json.dumps(session.metadata),
                     session.total_input_tokens, session.total_output_tokens, session.total_cost)
                )
                conn.commit()
        # Remove checkpoint
        cp.unlink(missing_ok=True)
        return session


# ─── Global singleton ────────────────────────────────────────────────────────

_manager: Optional[SessionManager] = None


def get_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager


if __name__ == "__main__":
    m = SessionManager()
    s = m.create_session("deepseek-chat", "deepseek", {"task": "test"})
    print(f"Created: {s.id}")
    m.append_message(s.id, {"role": "user", "content": "hello"})
    print(m.list_sessions())
    print(m.get_stats())
