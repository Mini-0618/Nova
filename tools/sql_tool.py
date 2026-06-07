"""
Codex-Local SQL Tool
执行 SQL 查询，支持 SQLite / MySQL / PostgreSQL / DuckDB。
纯 Python 实现，不需要额外依赖（除目标数据库驱动）。
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ─── DB Connection ───────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    success: bool
    columns: List[str]
    rows: List[tuple]
    row_count: int
    affected_rows: int = 0
    error: Optional[str] = None
    query: str = ""
    duration_ms: int = 0


class DBConnection:
    """
    统一数据库连接管理器。
    自动识别连接字符串类型并路由到对应驱动。
    """

    DRIVER_MAP = {
        ".db": "sqlite",
        ".sqlite": "sqlite",
        ".sqlite3": "sqlite",
    }

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._conn = None
        self.db_type = self._detect_type(connection_string)

    def _detect_type(self, conn_str: str) -> str:
        if conn_str.endswith((".db", ".sqlite", ".sqlite3")):
            return "sqlite"
        if "mysql" in conn_str.lower() or "mariadb" in conn_str.lower():
            return "mysql"
        if "postgresql" in conn_str.lower() or "postgres" in conn_str.lower():
            return "postgresql"
        if "duckdb" in conn_str.lower():
            return "duckdb"
        if conn_str.startswith("mysql://"):
            return "mysql"
        if conn_str.startswith("postgresql://"):
            return "postgresql"
        if conn_str.startswith("sqlite://"):
            return "sqlite"
        # 默认为SQLite
        if os.path.exists(conn_str):
            return "sqlite"
        return "sqlite"

    def connect(self):
        """建立连接"""
        try:
            if self.db_type == "sqlite":
                # SQLite：connection_string 是文件路径
                path = self.connection_string
                if not path.endswith((".db", ".sqlite", ".sqlite3")):
                    path = path + ".db"
                self._conn = sqlite3.connect(path)
                self._conn.row_factory = sqlite3.Row
            elif self.db_type == "mysql":
                import pymysql
                # 需要 pymysql: pip install pymysql
                # 解析连接字符串 mysql://user:pass@host:port/dbname
                parsed = self._parse_uri(self.connection_string, "mysql")
                self._conn = pymysql.connect(**parsed)
            elif self.db_type == "postgresql":
                import psycopg2
                parsed = self._parse_uri(self.connection_string, "postgresql")
                self._conn = psycopg2.connect(**parsed)
            elif self.db_type == "duckdb":
                import duckdb
                self._conn = duckdb.connect(self.connection_string)
            return self
        except ImportError as e:
            raise ImportError(f"需要安装 {self.db_type} 驱动: pip install {self.db_type}") from e
        except Exception as e:
            raise ConnectionError(f"连接失败 [{self.db_type}]: {e}") from e

    def _parse_uri(self, uri: str, driver: str) -> Dict[str, Any]:
        """简单 URI 解析 user:pass@host:port/db"""
        import re
        match = re.match(rf"{driver}://(.+?):(.+?)@(.+?):(\d+)/(.+)", uri)
        if match:
            user, password, host, port, db = match.groups()
            return {"host": host, "port": int(port), "user": user,
                    "password": password, "database": db}
        return {"database": self.connection_string}

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.close()


# ─── SQL Query Tool ────────────────────────────────────────────────────────

def sql_query(
    connection_string: str,
    query: str,
    params: Optional[List] = None,
    timeout: int = 30,
) -> QueryResult:
    """
    执行 SQL 查询。

    支持：SQLite, MySQL, PostgreSQL, DuckDB

    Args:
        connection_string: 连接字符串或数据库文件路径
            - SQLite: "D:/data/mydb.db" 或 "sqlite:///data/mydb.db"
            - MySQL: "mysql://user:pass@localhost:3306/mydb"
            - PostgreSQL: "postgresql://user:pass@localhost:5432/mydb"
        query: SQL 语句
        params: 参数化查询参数（防注入）
        timeout: 查询超时（秒）

    Returns:
        QueryResult: {
            success: bool,
            columns: ["col1", "col2"],
            rows: [(val1, val2), ...],
            row_count: 10,
            affected_rows: 0,
            error: None
        }
    """
    import time
    start = time.perf_counter()

    try:
        conn = DBConnection(connection_string).connect()
    except Exception as e:
        return QueryResult(
            success=False, columns=[], rows=[], row_count=0,
            error=str(e), query=query, duration_ms=0
        )

    try:
        cursor = conn._conn.cursor()

        # 执行查询
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # 获取结果
        if cursor.description:
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            # 转换 Row 为 tuple（兼容性）
            rows = [tuple(r) for r in rows]
            row_count = len(rows)
            affected_rows = 0
        else:
            # 非查询语句（INSERT/UPDATE/DELETE）
            columns = []
            rows = []
            row_count = 0
            affected_rows = cursor.rowcount

        duration_ms = int((time.perf_counter() - start) * 1000)

        return QueryResult(
            success=True,
            columns=columns,
            rows=rows,
            row_count=row_count,
            affected_rows=affected_rows,
            query=query,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return QueryResult(
            success=False, columns=[], rows=[], row_count=0,
            error=str(e), query=query, duration_ms=duration_ms
        )

    finally:
        conn.close()


def sql_tables(connection_string: str) -> QueryResult:
    """列出数据库中所有表"""
    query = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name NOT LIKE 'sqlite_%'
    UNION ALL
    SELECT name FROM sqlite_master
    WHERE type='view'
    ORDER BY name
    """
    # 检测类型
    if ".db" in connection_string or ".sqlite" in connection_string:
        return sql_query(connection_string, query)
    # MySQL
    if "mysql" in connection_string.lower():
        return sql_query(connection_string, "SHOW TABLES")
    # PostgreSQL
    if "postgresql" in connection_string.lower():
        return sql_query(connection_string,
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
    return sql_query(connection_string, query)


def sql_describe(connection_string: str, table: str) -> QueryResult:
    """获取表结构"""
    # SQLite
    if ".db" in connection_string or ".sqlite" in connection_string:
        query = f"PRAGMA table_info({table})"
        return sql_query(connection_string, query)
    # MySQL
    if "mysql" in connection_string.lower():
        return sql_query(connection_string, f"DESCRIBE {table}")
    # PostgreSQL
    if "postgresql" in connection_string.lower():
        return sql_query(connection_string,
            f"""SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position""")
    return sql_query(connection_string, f"SELECT * FROM {table} LIMIT 0")


# ─── Tool 格式输出 ─────────────────────────────────────────────────────────

def format_query_result(result: QueryResult) -> str:
    """把 QueryResult 格式化成易读的文本"""
    if not result.success:
        return f"❌ 查询失败：{result.error}"

    lines = []
    lines.append(f"✅ 成功 | {result.row_count} 行 | {result.duration_ms}ms")

    if result.affected_rows > 0:
        lines.append(f"📝 影响行数：{result.affected_rows}")

    if result.columns:
        lines.append("")
        # 表头
        col_widths = []
        for i, col in enumerate(result.columns):
            max_w = max(len(str(col)), max((len(str(row[i])) for row in result.rows[:100] if row[i] is not None), default=0))
            col_widths.append(min(max_w + 2, 30))
        widths = col_widths[:8]  # 最多8列

        # 表头
        header = " | ".join(result.columns[i].ljust(widths[i]) for i in range(len(result.columns)))
        lines.append(header)
        lines.append("-" * len(header))

        # 数据行
        for row in result.rows[:50]:  # 最多50行
            cols = []
            for i in range(len(result.columns)):
                val = str(row[i]) if row[i] is not None else "NULL"
                val = val[:widths[i]].ljust(widths[i])
                cols.append(val)
            lines.append(" | ".join(cols))

        if result.row_count > 50:
            lines.append(f"... 还有 {result.row_count - 50} 行")

    return "\n".join(lines)


# ─── Tool wrapper ─────────────────────────────────────────────────────────

def sql_tool(operation: str, connection_string: str = "", query: str = "",
             table: str = "", params: Optional[List] = None) -> Dict[str, Any]:
    """
    SQL 工具的统一入口。
    用于 executor.execute_tool("SqlQuery", {...})
    """
    ops = {
        "query": lambda: sql_query(connection_string, query, params),
        "tables": lambda: sql_tables(connection_string),
        "describe": lambda: sql_describe(connection_string, table),
    }

    if operation not in ops:
        return {"success": False, "error": f"未知操作：{operation}，可用：query/tables/describe"}

    try:
        result = ops[operation]()
        return {
            "success": result.success,
            "columns": result.columns,
            "rows": [list(r) for r in result.rows],
            "row_count": result.row_count,
            "affected_rows": result.affected_rows,
            "error": result.error,
            "query": result.query,
            "duration_ms": result.duration_ms,
            "formatted": format_query_result(result),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── 快速测试 ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 用内存SQLite测试
    print("=== SQL Tool 测试（SQLite内存）===")

    # 先建表
    setup = sql_query(":memory:",
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);"
        "INSERT INTO users VALUES (1, 'Alice', 30), (2, 'Bob', 25), (3, 'Charlie', 35);")
    print(f"建表: {setup.success}")

    # 查询
    result = sql_query(":memory:", "SELECT * FROM users WHERE age > 25 ORDER BY age")
    print(f"\n查询结果：")
    print(format_query_result(result))

    # 表列表
    print("\n表列表：")
    # 内存数据库没有表，跳过

    # 真实文件数据库测试
    test_db = "D:/codex-local/data/test.db"
    os.makedirs(os.path.dirname(test_db), exist_ok=True)

    setup2 = sql_query(test_db,
        "CREATE TABLE IF NOT EXISTS products (id INTEGER, name TEXT, price REAL);"
        "INSERT INTO products VALUES (1, 'Apple', 3.5), (2, 'Banana', 1.2);")
    print(f"\n建表2: {setup2.success}")

    result2 = sql_query(test_db, "SELECT * FROM products")
    print(format_query_result(result2))

    print("\n=== 测试完成 ===")