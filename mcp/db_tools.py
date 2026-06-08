"""
Database Tools Module
Provides SQLite database operations: connect, query, list tables, describe schema.
"""

import sqlite3
import uuid
from typing import Dict, Any, List

from .server import ToolModule


# Connection pool keyed by conn_id
_connections: Dict[str, sqlite3.Connection] = {}


class DBTools(ToolModule):
    """Database tools as MCP tools."""

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "db_connect",
                "description": "Connect to a SQLite database. Returns a connection ID for subsequent queries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to SQLite database file"},
                    },
                    "required": ["path"],
                },
                "handler": self._db_connect,
            },
            {
                "name": "db_query",
                "description": "Execute a SQL query on a connected database",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conn_id": {"type": "string", "description": "Connection ID from db_connect"},
                        "sql": {"type": "string", "description": "SQL query to execute"},
                    },
                    "required": ["conn_id", "sql"],
                },
                "handler": self._db_query,
            },
            {
                "name": "db_tables",
                "description": "List all tables in a connected database",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conn_id": {"type": "string", "description": "Connection ID from db_connect"},
                    },
                    "required": ["conn_id"],
                },
                "handler": self._db_tables,
            },
            {
                "name": "db_schema",
                "description": "Show the schema (CREATE TABLE statement) of a specific table",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conn_id": {"type": "string", "description": "Connection ID from db_connect"},
                        "table": {"type": "string", "description": "Table name"},
                    },
                    "required": ["conn_id", "table"],
                },
                "handler": self._db_schema,
            },
        ]

    def _get_conn(self, conn_id: str) -> sqlite3.Connection:
        if conn_id not in _connections:
            raise ValueError(f"Unknown connection ID: {conn_id}. Call db_connect first.")
        return _connections[conn_id]

    def _db_connect(self, path: str) -> Dict:
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            conn_id = str(uuid.uuid4())[:8]
            _connections[conn_id] = conn
            return {"success": True, "conn_id": conn_id, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _db_query(self, conn_id: str, sql: str) -> Dict:
        try:
            conn = self._get_conn(conn_id)
            cursor = conn.execute(sql)
            if cursor.description:
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                data = [dict(zip(columns, row)) for row in rows[:1000]]
                return {
                    "success": True,
                    "columns": columns,
                    "rows": data,
                    "row_count": len(data),
                    "truncated": len(rows) > 1000,
                }
            else:
                conn.commit()
                return {"success": True, "rows_affected": cursor.rowcount}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _db_tables(self, conn_id: str) -> Dict:
        try:
            conn = self._get_conn(conn_id)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            return {"success": True, "tables": tables, "count": len(tables)}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _db_schema(self, conn_id: str, table: str) -> Dict:
        try:
            conn = self._get_conn(conn_id)
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            row = cursor.fetchone()
            if not row:
                return {"success": False, "error": f"Table not found: {table}"}
            # Also get column info
            col_cursor = conn.execute(f"PRAGMA table_info('{table}')")
            columns = [
                {"name": r[1], "type": r[2], "notnull": bool(r[3]), "pk": bool(r[5])}
                for r in col_cursor.fetchall()
            ]
            return {"success": True, "table": table, "create_sql": row[0], "columns": columns}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}
