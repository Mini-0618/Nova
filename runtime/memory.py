"""
RootCode Memory System
======================
Short-term memory (in-session) + Long-term memory (cross-session, SQLite-backed).

Inspired by MCR's layered memory architecture:
- Working Memory: Current session context (in-memory)
- Episodic Memory: Session summaries and events (SQLite)
- Semantic Memory: Learned knowledge and facts (SQLite)
- Archive: Historical memories with decay (SQLite)

Features:
- Store, retrieve, update, delete memories
- Importance scoring and decay over time
- Tag-based and semantic search
- Memory consolidation (merge related memories)
- Session-aware memory isolation
"""

import os
import json
import sqlite3
import uuid
import time
import hashlib
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum


# ─── Configuration ─────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("CODEX_DATA", "D:/codex-local/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_DB_PATH = DATA_DIR / "memory.db"

# Memory tiers (from MCR architecture)
class MemoryTier(str, Enum):
    WORKING = "working"      # Current session context
    EPISODIC = "episodic"    # Session events and summaries
    SEMANTIC = "semantic"    # Learned knowledge and facts
    ARCHIVE = "archive"      # Historical memories with decay


# Default importance scores by tier
TIER_IMPORTANCE = {
    MemoryTier.WORKING: 0.5,
    MemoryTier.EPISODIC: 0.6,
    MemoryTier.SEMANTIC: 0.8,
    MemoryTier.ARCHIVE: 0.3,
}

# Importance decay rate (per day)
DECAY_RATE = {
    MemoryTier.WORKING: 0.0,     # No decay (session-scoped)
    MemoryTier.EPISODIC: 0.01,   # Slow decay
    MemoryTier.SEMANTIC: 0.005,  # Very slow decay
    MemoryTier.ARCHIVE: 0.02,    # Faster decay
}


# ─── Data Models ───────────────────────────────────────────────────────────

@dataclass
class Memory:
    """A single memory entry."""
    id: str
    content: str
    tier: str
    importance: float
    tags: List[str]
    source: str
    title: str
    created_at: str
    accessed_at: str
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "tier": self.tier,
            "importance": self.importance,
            "tags": self.tags,
            "source": self.source,
            "title": self.title,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "access_count": self.access_count,
            "metadata": self.metadata,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Memory':
        return cls(
            id=data.get("id", ""),
            content=data.get("content", ""),
            tier=data.get("tier", MemoryTier.EPISODIC.value),
            importance=data.get("importance", 0.5),
            tags=data.get("tags", []),
            source=data.get("source", ""),
            title=data.get("title", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            accessed_at=data.get("accessed_at", datetime.now().isoformat()),
            access_count=data.get("access_count", 0),
            metadata=data.get("metadata", {}),
            session_id=data.get("session_id"),
        )


@dataclass
class MemorySearchResult:
    """Search result with relevance score."""
    memory: Memory
    score: float
    match_reason: str


# ─── Working Memory (In-Session) ──────────────────────────────────────────

class WorkingMemory:
    """
    Short-term, in-session memory.
    Stores context for the current conversation/task.
    Automatically cleared when session ends.
    """

    def __init__(self, max_items: int = 100):
        self.items: List[Dict[str, Any]] = []
        self.max_items = max_items
        self._lock = threading.Lock()

    def store(self, content: str, importance: float = 0.5,
              tags: Optional[List[str]] = None, source: str = "session") -> str:
        """Store a working memory item."""
        item_id = f"wm_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        item = {
            "id": item_id,
            "content": content,
            "importance": importance,
            "tags": tags or [],
            "source": source,
            "created_at": now,
            "accessed_at": now,
            "access_count": 0,
        }

        with self._lock:
            self.items.append(item)
            # Evict oldest if over limit
            if len(self.items) > self.max_items:
                self.items = self.items[-self.max_items:]

        return item_id

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant working memories by keyword matching."""
        with self._lock:
            if not self.items:
                return []

            # Simple keyword matching
            scored = []
            query_lower = query.lower()
            for item in self.items:
                content_lower = item["content"].lower()
                # Calculate relevance score
                score = 0.0
                if query_lower in content_lower:
                    score = 1.0
                else:
                    # Word overlap
                    query_words = set(query_lower.split())
                    content_words = set(content_lower.split())
                    overlap = query_words & content_words
                    if overlap:
                        score = len(overlap) / max(len(query_words), 1)

                if score > 0:
                    # Boost by importance and recency
                    score *= item.get("importance", 0.5)
                    scored.append((score, item))

            # Sort by score descending
            scored.sort(key=lambda x: x[0], reverse=True)

            # Update access stats
            results = []
            for score, item in scored[:top_k]:
                item["accessed_at"] = datetime.now().isoformat()
                item["access_count"] = item.get("access_count", 0) + 1
                results.append({**item, "score": score})

            return results

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all working memory items."""
        with self._lock:
            return list(self.items)

    def clear(self):
        """Clear all working memory."""
        with self._lock:
            self.items.clear()

    def size(self) -> int:
        """Get current number of items."""
        with self._lock:
            return len(self.items)


# ─── Long-Term Memory (SQLite-Backed) ─────────────────────────────────────

class LongTermMemory:
    """
    Persistent, cross-session memory stored in SQLite.
    Supports episodic, semantic, and archive tiers.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or MEMORY_DB_PATH
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
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'episodic',
                importance REAL NOT NULL DEFAULT 0.5,
                tags TEXT NOT NULL DEFAULT '[]',
                source TEXT DEFAULT '',
                title TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                accessed_at TEXT NOT NULL,
                access_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                session_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_memories_tier ON memories(tier);
            CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_memories_accessed ON memories(accessed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);

            CREATE TABLE IF NOT EXISTS memory_tags (
                memory_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (memory_id, tag),
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_tags_tag ON memory_tags(tag);
        """)
        conn.commit()

    def store(self, content: str, tier: str = "episodic",
              importance: Optional[float] = None, tags: Optional[List[str]] = None,
              source: str = "", title: str = "", session_id: Optional[str] = None,
              metadata: Optional[Dict] = None) -> str:
        """Store a long-term memory."""
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        if importance is None:
            importance = TIER_IMPORTANCE.get(MemoryTier(tier), 0.5)

        tags = tags or []
        metadata = metadata or {}

        conn = self._get_conn()
        with self._lock:
            conn.execute(
                """INSERT INTO memories (id, content, tier, importance, tags, source, title,
                   created_at, accessed_at, access_count, metadata, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, content, tier, importance, json.dumps(tags),
                 source, title, now, now, 0, json.dumps(metadata), session_id)
            )

            # Insert tags into separate table for efficient querying
            for tag in tags:
                conn.execute(
                    "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                    (memory_id, tag.lower())
                )

            conn.commit()

        return memory_id

    def retrieve(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a specific memory by ID."""
        conn = self._get_conn()
        with self._lock:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if not row:
                return None

            # Update access stats
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE memories SET accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
                (now, memory_id)
            )
            conn.commit()

            return self._row_to_memory(row)

    def search(self, query: str = "", tags: Optional[List[str]] = None,
               tier: Optional[str] = None, min_importance: float = 0.0,
               session_id: Optional[str] = None, limit: int = 10,
               time_decay: bool = True) -> List[MemorySearchResult]:
        """
        Search memories with multiple filters and relevance scoring.

        Args:
            query: Text to search in content and title
            tags: Filter by tags (AND logic)
            tier: Filter by memory tier
            min_importance: Minimum importance threshold
            session_id: Filter by session ID
            limit: Maximum results
            time_decay: Apply time-based importance decay

        Returns:
            List of MemorySearchResult with relevance scores
        """
        conn = self._get_conn()

        # Build SQL query
        conditions = []
        params = []

        if tier:
            conditions.append("tier = ?")
            params.append(tier)

        if min_importance > 0:
            conditions.append("importance >= ?")
            params.append(min_importance)

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if tags:
            # Must have ALL specified tags
            for tag in tags:
                conditions.append("id IN (SELECT memory_id FROM memory_tags WHERE tag = ?)")
                params.append(tag.lower())

        if query:
            conditions.append("(content LIKE ? OR title LIKE ?)")
            query_param = f"%{query}%"
            params.extend([query_param, query_param])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._lock:
            rows = conn.execute(
                f"""SELECT * FROM memories
                    WHERE {where_clause}
                    ORDER BY importance DESC, accessed_at DESC
                    LIMIT ?""",
                params + [limit * 3]  # Fetch extra for scoring
            ).fetchall()

        # Score and rank results
        results = []
        now = datetime.now()

        for row in rows:
            memory = self._row_to_memory(row)
            score = memory.importance
            match_reason = "importance"

            # Time decay
            if time_decay:
                try:
                    created = datetime.fromisoformat(memory.created_at)
                    days_old = (now - created).total_seconds() / 86400
                    decay = DECAY_RATE.get(MemoryTier(memory.tier), 0.01)
                    score *= max(0.1, 1.0 - (decay * days_old))
                except (ValueError, TypeError):
                    pass

            # Recency boost
            try:
                accessed = datetime.fromisoformat(memory.accessed_at)
                hours_since_access = (now - accessed).total_seconds() / 3600
                recency_boost = max(0, 1.0 - (hours_since_access / 168))  # 1 week
                score *= (1.0 + recency_boost * 0.2)
            except (ValueError, TypeError):
                pass

            # Access frequency boost
            if memory.access_count > 0:
                score *= (1.0 + min(0.3, memory.access_count * 0.05))

            # Query relevance
            if query:
                query_lower = query.lower()
                content_lower = memory.content.lower()
                title_lower = memory.title.lower()

                if query_lower in title_lower:
                    score *= 2.0
                    match_reason = "title_match"
                elif query_lower in content_lower:
                    score *= 1.5
                    match_reason = "content_match"
                else:
                    # Word overlap
                    query_words = set(query_lower.split())
                    content_words = set(content_lower.split())
                    overlap = query_words & content_words
                    if overlap:
                        score *= (1.0 + len(overlap) / max(len(query_words), 1))
                        match_reason = "word_overlap"

            results.append(MemorySearchResult(
                memory=memory,
                score=round(score, 4),
                match_reason=match_reason,
            ))

        # Sort by score and limit
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def update(self, memory_id: str, **kwargs) -> bool:
        """Update a memory's fields."""
        conn = self._get_conn()

        allowed_fields = {"content", "tier", "importance", "tags", "source", "title", "metadata"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            return False

        # Handle tags separately
        tags = updates.pop("tags", None)

        with self._lock:
            # Update main fields
            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                params = []
                for k, v in updates.items():
                    if isinstance(v, (dict, list)):
                        params.append(json.dumps(v))
                    else:
                        params.append(v)
                params.append(memory_id)

                conn.execute(
                    f"UPDATE memories SET {set_clause}, accessed_at = ? WHERE id = ?",
                    params[:-1] + [datetime.now().isoformat(), memory_id]
                )

            # Update tags if provided
            if tags is not None:
                conn.execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
                for tag in tags:
                    conn.execute(
                        "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                        (memory_id, tag.lower())
                    )
                conn.execute(
                    "UPDATE memories SET tags = ? WHERE id = ?",
                    (json.dumps(tags), memory_id)
                )

            conn.commit()
        return True

    def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        conn = self._get_conn()
        with self._lock:
            conn.execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    def consolidate(self, memory_ids: List[str], new_content: str,
                    new_title: str = "", new_tags: Optional[List[str]] = None) -> str:
        """
        Consolidate multiple memories into one.
        Original memories are archived, new consolidated memory is created.
        """
        if len(memory_ids) < 2:
            raise ValueError("Need at least 2 memories to consolidate")

        conn = self._get_conn()
        now = datetime.now().isoformat()

        with self._lock:
            # Get original memories
            placeholders = ",".join("?" for _ in memory_ids)
            rows = conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})",
                memory_ids
            ).fetchall()

            if not rows:
                raise ValueError("No memories found to consolidate")

            # Calculate average importance and merge tags
            total_importance = 0
            all_tags = set()
            sources = []

            for row in rows:
                total_importance += row["importance"]
                try:
                    all_tags.update(json.loads(row["tags"]))
                except (json.JSONDecodeError, TypeError):
                    pass
                sources.append(row["source"])

            avg_importance = total_importance / len(rows)
            if new_tags:
                all_tags.update(new_tags)

            # Create consolidated memory
            consolidated_id = f"mem_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO memories (id, content, tier, importance, tags, source, title,
                   created_at, accessed_at, access_count, metadata)
                   VALUES (?, ?, 'semantic', ?, ?, ?, ?, ?, ?, 0, ?)""",
                (consolidated_id, new_content, min(1.0, avg_importance * 1.2),
                 json.dumps(sorted(all_tags)), "consolidated",
                 new_title or "Consolidated Memory", now, now,
                 json.dumps({"consolidated_from": memory_ids}))
            )

            # Insert tags
            for tag in all_tags:
                conn.execute(
                    "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                    (consolidated_id, tag.lower())
                )

            # Archive original memories
            for mid in memory_ids:
                conn.execute(
                    "UPDATE memories SET tier = 'archive', importance = importance * 0.5 WHERE id = ?",
                    (mid,)
                )

            conn.commit()

        return consolidated_id

    def get_stats(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        conn = self._get_conn()
        with self._lock:
            tier_counts = {}
            for row in conn.execute("SELECT tier, COUNT(*) as cnt FROM memories GROUP BY tier"):
                tier_counts[row["tier"]] = row["cnt"]

            total = conn.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()["cnt"]
            avg_importance = conn.execute("SELECT AVG(importance) as avg FROM memories").fetchone()["avg"]

            # Recent activity
            recent = conn.execute(
                "SELECT COUNT(*) as cnt FROM memories WHERE created_at > ?",
                ((datetime.now() - timedelta(days=7)).isoformat(),)
            ).fetchone()["cnt"]

        return {
            "total_memories": total,
            "by_tier": tier_counts,
            "avg_importance": round(avg_importance or 0, 3),
            "recent_7_days": recent,
        }

    def cleanup(self, days_threshold: int = 90, min_importance: float = 0.1) -> int:
        """
        Clean up old, low-importance archive memories.
        Returns number of deleted memories.
        """
        conn = self._get_conn()
        threshold_date = (datetime.now() - timedelta(days=days_threshold)).isoformat()

        with self._lock:
            cursor = conn.execute(
                """DELETE FROM memories
                   WHERE tier = 'archive'
                   AND importance < ?
                   AND accessed_at < ?""",
                (min_importance, threshold_date)
            )
            deleted = cursor.rowcount

            # Clean orphaned tags
            conn.execute(
                """DELETE FROM memory_tags
                   WHERE memory_id NOT IN (SELECT id FROM memories)"""
            )

            conn.commit()
        return deleted

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """Convert a database row to Memory object."""
        try:
            tags = json.loads(row["tags"])
        except (json.JSONDecodeError, TypeError):
            tags = []

        try:
            metadata = json.loads(row["metadata"])
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        return Memory(
            id=row["id"],
            content=row["content"],
            tier=row["tier"],
            importance=row["importance"],
            tags=tags,
            source=row["source"],
            title=row["title"],
            created_at=row["created_at"],
            accessed_at=row["accessed_at"],
            access_count=row["access_count"],
            metadata=metadata,
            session_id=row["session_id"],
        )


# ─── Unified Memory Manager ───────────────────────────────────────────────

class MemoryManager:
    """
    Unified memory interface combining working memory and long-term memory.
    Provides high-level memory operations for the CodexLoop.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.working = WorkingMemory()
        self.long_term = LongTermMemory(db_path)
        self._session_id: Optional[str] = None

    def set_session(self, session_id: str):
        """Set the current session ID for memory operations."""
        self._session_id = session_id

    def store(self, content: str, tier: str = "working",
              importance: float = 0.5, tags: Optional[List[str]] = None,
              source: str = "", title: str = "",
              promote_to_long_term: bool = False) -> str:
        """
        Store a memory.

        Args:
            content: Memory content
            tier: Memory tier (working, episodic, semantic, archive)
            importance: Importance score (0-1)
            tags: Optional tags for categorization
            source: Source of the memory
            title: Optional title
            promote_to_long_term: If True, also store in long-term memory

        Returns:
            Memory ID
        """
        if tier == "working" or not promote_to_long_term:
            # Store in working memory
            return self.working.store(content, importance, tags, source)
        else:
            # Store in long-term memory
            return self.long_term.store(
                content=content,
                tier=tier,
                importance=importance,
                tags=tags,
                source=source,
                title=title,
                session_id=self._session_id,
            )

    def remember(self, content: str, importance: float = 0.7,
                 tags: Optional[List[str]] = None, title: str = "") -> str:
        """
        High-level: Remember something important.
        Stores in both working and long-term memory.
        """
        memory_id = self.long_term.store(
            content=content,
            tier="episodic",
            importance=importance,
            tags=tags,
            title=title or content[:50],
            session_id=self._session_id,
        )

        # Also keep in working memory for current session
        self.working.store(content, importance, tags, "remember")

        return memory_id

    def recall(self, query: str, top_k: int = 5,
               include_working: bool = True,
               include_long_term: bool = True) -> List[Dict[str, Any]]:
        """
        High-level: Recall memories related to a query.
        Searches both working and long-term memory.
        """
        results = []

        # Search working memory
        if include_working:
            working_results = self.working.retrieve(query, top_k)
            for r in working_results:
                results.append({
                    "source": "working",
                    "content": r["content"],
                    "score": r.get("score", 0),
                    "importance": r.get("importance", 0.5),
                    "created_at": r.get("created_at", ""),
                })

        # Search long-term memory
        if include_long_term:
            lt_results = self.long_term.search(query=query, limit=top_k)
            for r in lt_results:
                results.append({
                    "source": "long_term",
                    "memory_id": r.memory.id,
                    "content": r.memory.content,
                    "title": r.memory.title,
                    "tier": r.memory.tier,
                    "score": r.score,
                    "importance": r.memory.importance,
                    "tags": r.memory.tags,
                    "created_at": r.memory.created_at,
                    "match_reason": r.match_reason,
                })

        # Sort by score and return top_k
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:top_k]

    def learn(self, content: str, tags: Optional[List[str]] = None,
              title: str = "", importance: float = 0.8) -> str:
        """
        High-level: Learn a new fact or knowledge.
        Stores as semantic memory (high importance, slow decay).
        """
        return self.long_term.store(
            content=content,
            tier="semantic",
            importance=importance,
            tags=tags,
            title=title or content[:50],
            session_id=self._session_id,
        )

    def forget(self, memory_id: str) -> bool:
        """Delete a memory from long-term storage."""
        return self.long_term.delete(memory_id)

    def update_memory(self, memory_id: str, **kwargs) -> bool:
        """Update a long-term memory."""
        return self.long_term.update(memory_id, **kwargs)

    def get_context_summary(self, max_items: int = 10) -> str:
        """
        Get a summary of current working memory context.
        Useful for injecting into LLM prompts.
        """
        items = self.working.get_all()
        if not items:
            return ""

        # Sort by importance and recency
        items.sort(key=lambda x: (x.get("importance", 0), x.get("created_at", "")), reverse=True)

        summary_parts = []
        for item in items[:max_items]:
            content = item.get("content", "")
            if len(content) > 200:
                content = content[:200] + "..."
            summary_parts.append(f"- [{item.get('source', 'unknown')}] {content}")

        return "Working Memory Context:\n" + "\n".join(summary_parts)

    def get_relevant_memories_for_task(self, task: str, max_memories: int = 5) -> str:
        """
        Get memories relevant to a task for LLM context.
        Returns formatted string for system prompt injection.
        """
        results = self.recall(task, top_k=max_memories, include_working=True, include_long_term=True)

        if not results:
            return ""

        parts = ["Relevant memories for this task:"]
        for i, r in enumerate(results, 1):
            source = r.get("source", "unknown")
            content = r.get("content", "")
            if len(content) > 300:
                content = content[:300] + "..."

            title = r.get("title", "")
            tier = r.get("tier", "")

            header = f"{i}. "
            if title:
                header += f"[{title}] "
            if tier:
                header += f"({tier}) "

            parts.append(f"{header}{content}")

        return "\n".join(parts)

    def end_session(self, promote_important: bool = True):
        """
        End current session. Optionally promote important working memories to long-term.
        """
        if promote_important:
            # Promote high-importance working memories to episodic
            for item in self.working.get_all():
                if item.get("importance", 0) >= 0.7:
                    self.long_term.store(
                        content=item["content"],
                        tier="episodic",
                        importance=item["importance"],
                        tags=item.get("tags", []),
                        source=item.get("source", "session"),
                        session_id=self._session_id,
                    )

        # Clear working memory
        self.working.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics."""
        lt_stats = self.long_term.get_stats()
        return {
            "working_memory": {
                "items": self.working.size(),
                "max_items": self.working.max_items,
            },
            "long_term_memory": lt_stats,
        }


# ─── Global Singleton ─────────────────────────────────────────────────────

_manager: Optional[MemoryManager] = None


def get_memory_manager(db_path: Optional[Path] = None) -> MemoryManager:
    """Get or create the global memory manager instance."""
    global _manager
    if _manager is None:
        _manager = MemoryManager(db_path)
    return _manager


# ─── Convenience Functions ─────────────────────────────────────────────────

def remember(content: str, **kwargs) -> str:
    """Quick remember: store in both working and long-term memory."""
    return get_memory_manager().remember(content, **kwargs)


def recall(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Quick recall: search all memories."""
    return get_memory_manager().recall(query, top_k)


def learn(content: str, **kwargs) -> str:
    """Quick learn: store as semantic knowledge."""
    return get_memory_manager().learn(content, **kwargs)


def forget(memory_id: str) -> bool:
    """Quick forget: delete a memory."""
    return get_memory_manager().forget(memory_id)


# ─── CLI Test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def test_memory_system():
        print("=" * 60)
        print("RootCode Memory System Test")
        print("=" * 60)

        # Initialize
        manager = get_memory_manager()
        manager.set_session("test_session_001")

        # Test 1: Store working memory
        print("\n1. Storing working memories...")
        manager.store("User wants to create a Python web server", importance=0.6, tags=["task", "python"])
        manager.store("Using FastAPI framework", importance=0.7, tags=["framework", "python"])
        manager.store("Need to implement REST API endpoints", importance=0.8, tags=["api", "task"])
        print(f"   Working memory size: {manager.working.size()}")

        # Test 2: Learn semantic knowledge
        print("\n2. Learning semantic knowledge...")
        mid1 = manager.learn(
            "FastAPI is a modern Python web framework for building APIs",
            tags=["python", "framework", "web"],
            title="FastAPI Framework"
        )
        mid2 = manager.learn(
            "SQLite is a lightweight embedded database",
            tags=["database", "sqlite"],
            title="SQLite Database"
        )
        print(f"   Learned: {mid1}, {mid2}")

        # Test 3: Remember episodic events
        print("\n3. Remembering episodic events...")
        mid3 = manager.remember(
            "Started working on REST API project",
            importance=0.7,
            tags=["project", "start"],
            title="Project Start"
        )
        print(f"   Remembered: {mid3}")

        # Test 4: Recall memories
        print("\n4. Recalling memories about 'Python'...")
        results = manager.recall("Python", top_k=5)
        for r in results:
            print(f"   [{r['source']}] {r.get('title', 'N/A')}: {r['content'][:80]}...")

        # Test 5: Search long-term memory
        print("\n5. Searching long-term memory for 'API'...")
        lt_results = manager.long_term.search(query="API", limit=5)
        for r in lt_results:
            print(f"   [{r.memory.tier}] {r.memory.title}: score={r.score:.3f}")

        # Test 6: Update memory
        print("\n6. Updating memory...")
        success = manager.update_memory(mid1, importance=0.9, tags=["python", "framework", "web", "updated"])
        print(f"   Update success: {success}")

        # Test 7: Get context summary
        print("\n7. Context summary:")
        summary = manager.get_context_summary()
        print(f"   {summary[:200]}...")

        # Test 8: Get relevant memories for task
        print("\n8. Relevant memories for task 'Build a web API':")
        task_context = manager.get_relevant_memories_for_task("Build a web API")
        print(f"   {task_context[:300]}...")

        # Test 9: Get stats
        print("\n9. Memory statistics:")
        stats = manager.get_stats()
        print(f"   Working memory: {stats['working_memory']['items']} items")
        print(f"   Long-term: {stats['long_term_memory']['total_memories']} memories")
        print(f"   By tier: {stats['long_term_memory']['by_tier']}")

        # Test 10: End session
        print("\n10. Ending session (promoting important memories)...")
        manager.end_session(promote_important=True)
        print(f"    Working memory cleared: {manager.working.size()} items")

        # Verify promotion
        print("\n11. Verifying promoted memories...")
        promoted = manager.long_term.search(tier="episodic", limit=5)
        for r in promoted:
            print(f"    Promoted: {r.memory.title} (importance: {r.memory.importance})")

        print("\n" + "=" * 60)
        print("Memory system test complete!")
        print("=" * 60)

    asyncio.run(test_memory_system())
