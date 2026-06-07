"""
Codex-Local Web Console
Flask-based web UI for monitoring loop status, sessions, and token usage.
"""

import os
import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from flask import Flask, render_template, jsonify, request
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    Flask = None
    render_template = None
    jsonify = None
    request = None

import os, sys as _sys
_root = Path(__file__).parent.parent
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from runtime.session import get_manager, DB_PATH  # noqa: E402
from runtime.loop import CodexLoop, LoopConfig  # noqa: E402


DATA_DIR = Path(os.environ.get("CODEX_DATA", "D:/codex-local/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR = Path(os.environ.get("CODEX_LOGS", "D:/codex-local/logs"))
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ─── App Setup ──────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder=str(DATA_DIR / "templates")) if HAS_FLASK else None


# ─── Routes (only defined when Flask is available) ──────────────────────────

if HAS_FLASK:

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/status")
    def status():
        """Return current loop status and stats."""
        mgr = get_manager()
        stats = mgr.get_stats()
        recent = mgr.list_sessions(limit=10)
        recent_data = [
            {
                "id": s.id,
                "model": s.model,
                "status": s.status,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "total_cost": s.total_cost,
            }
            for s in recent
        ]
        return jsonify({
            "stats": stats,
            "recent_sessions": recent_data,
            "timestamp": int(time.time()),
        })

    @app.route("/sessions")
    def sessions():
        """List all sessions."""
        mgr = get_manager()
        limit = int(request.args.get("limit", 50))
        status_filter = request.args.get("status", None)
        sessions_list = mgr.list_sessions(limit=limit, status=status_filter)
        return jsonify({
            "sessions": [s.to_dict() for s in sessions_list],
            "count": len(sessions_list),
        })

    @app.route("/session/<session_id>")
    def get_session(session_id: str):
        mgr = get_manager()
        s = mgr.get_session(session_id)
        if not s:
            return jsonify({"error": "not found"}), 404
        return jsonify(s.to_dict())

    @app.route("/run", methods=["POST"])
    def run_task():
        """Submit a task to the auto-loop."""
        data = request.get_json() or {}
        task = data.get("task", "")
        if not task:
            return jsonify({"error": "task is required"}), 400

        model = data.get("model", os.environ.get("CODEX_MODEL", "deepseek-chat"))
        provider = data.get("provider", os.environ.get("CODEX_PROVIDER", "deepseek"))
        max_iter = int(data.get("max_iterations", 50))

        config = LoopConfig(
            model=model,
            provider=provider,
            max_iterations=max_iter,
            trust_code_execution=True,
            trust_file_writes=True,
            trust_shell_commands=False,
        )

        loop = CodexLoop(config)

        # Run in background thread
        import threading
        import asyncio

        def run_async():
            asyncio.run(loop.run_task(task))

        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()

        return jsonify({
            "status": "started",
            "session_id": loop._current_session.id if loop._current_session else None,
            "task": task,
        })

    @app.route("/stop", methods=["POST"])
    def stop_loop():
        """Stop the running loop."""
        return jsonify({"status": "stopped"})

    @app.route("/stats")
    def stats():
        """Detailed token/cost statistics."""
        mgr = get_manager()
        stats = mgr.get_stats()

        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT MIN(created_at) as first_session,
                   MAX(created_at) as last_session
            FROM sessions
        """).fetchone()
        conn.close()

        return jsonify({
            **stats,
            "first_session_at": row["first_session"],
            "last_session_at": row["last_session"],
        })

    @app.route("/logs")
    def logs():
        """Return recent log entries."""
        log_file = LOGS_DIR / "loop.log"
        if not log_file.exists():
            return jsonify({"logs": []})

        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return jsonify({"logs": lines[-100:], "count": len(lines)})


# ─── HTML Template (inline) ─────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Codex-Local Console</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { color: #58a6ff; margin-bottom: 20px; font-size: 24px; }
        h2 { color: #8b949e; margin: 20px 0 10px; font-size: 16px; text-transform: uppercase; letter-spacing: 1px; }
        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
        .stat { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px; }
        .stat .label { color: #8b949e; font-size: 12px; text-transform: uppercase; }
        .stat .value { font-size: 28px; color: #58a6ff; margin-top: 4px; font-weight: bold; }
        .sessions { display: grid; gap: 8px; }
        .session { background: #0d1117; border: 1px solid #21262d; border-radius: 4px; padding: 10px 14px;
                   display: flex; justify-content: space-between; align-items: center; }
        .session:hover { border-color: #30363d; }
        .session .id { color: #58a6ff; font-family: monospace; font-size: 12px; }
        .session .model { color: #8b949e; font-size: 12px; }
        .session .status { padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }
        .status.active { background: #238636; color: white; }
        .status.completed { background: #1f6feb; color: white; }
        .status.error { background: #da3633; color: white; }
        .task-form { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px; margin-bottom: 20px; }
        .task-form textarea { width: 100%; background: #0d1117; border: 1px solid #30363d; border-radius: 4px;
                              color: #e6edf3; padding: 10px; font-size: 14px; min-height: 80px; resize: vertical; }
        .task-form input, .task-form select { background: #0d1117; border: 1px solid #30363d; border-radius: 4px;
                                               color: #e6edf3; padding: 6px 10px; font-size: 13px; }
        .task-form button { background: #238636; color: white; border: none; border-radius: 4px; padding: 8px 20px;
                            font-size: 14px; cursor: pointer; }
        .task-form button:hover { background: #2ea043; }
        .task-form .row { display: flex; gap: 10px; margin-bottom: 10px; }
        .task-form .row input { flex: 1; }
        .refresh-btn { background: #21262d; color: #8b949e; border: 1px solid #30363d; border-radius: 4px;
                       padding: 4px 12px; font-size: 12px; cursor: pointer; }
        .refresh-btn:hover { color: #e6edf3; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .header h1 { margin: 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Codex-Local Console</h1>
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
        </div>

        <h2>📊 Statistics</h2>
        <div class="stat-grid" id="stats-grid">
            <div class="stat"><div class="label">Total Sessions</div><div class="value" id="total-sessions">-</div></div>
            <div class="stat"><div class="label">Input Tokens</div><div class="value" id="input-tokens">-</div></div>
            <div class="stat"><div class="label">Output Tokens</div><div class="value" id="output-tokens">-</div></div>
            <div class="stat"><div class="label">Total Cost (USD)</div><div class="value" id="total-cost">-</div></div>
        </div>

        <h2>🚀 Run Task</h2>
        <div class="task-form">
            <textarea id="task-input" placeholder="Describe what you want the AI to do..."></textarea>
            <div class="row">
                <input type="text" id="model-input" value="deepseek-chat" placeholder="Model">
                <input type="text" id="provider-input" value="deepseek" placeholder="Provider">
                <input type="number" id="maxiter-input" value="50" placeholder="Max iterations" style="width:120px">
                <button onclick="submitTask()">▶ Run</button>
            </div>
            <div id="task-status" style="color:#8b949e;font-size:12px;margin-top:6px;"></div>
        </div>

        <h2>📋 Recent Sessions</h2>
        <div class="sessions" id="sessions-list">
            <div style="color:#8b949e;padding:10px;">Loading...</div>
        </div>
    </div>

    <script>
        async function loadStatus() {
            try {
                const r = await fetch('/status');
                const d = await r.json();
                document.getElementById('total-sessions').textContent = d.stats.total_sessions || 0;
                document.getElementById('input-tokens').textContent = (d.stats.total_input_tokens || 0).toLocaleString();
                document.getElementById('output-tokens').textContent = (d.stats.total_output_tokens || 0).toLocaleString();
                document.getElementById('total-cost').textContent = '$' + (d.stats.total_cost_usd || 0).toFixed(4);

                const list = document.getElementById('sessions-list');
                if (d.recent_sessions.length === 0) {
                    list.innerHTML = '<div style="color:#8b949e;padding:10px;">No sessions yet</div>';
                } else {
                    list.innerHTML = d.recent_sessions.map(s => `
                        <div class="session">
                            <div>
                                <span class="id">${s.id}</span>
                                <span class="model">${s.model}</span>
                            </div>
                            <div style="display:flex;gap:10px;align-items:center;">
                                <span class="status ${s.status}">${s.status}</span>
                                <span style="color:#8b949e;font-size:11px;">$${s.total_cost.toFixed(4)}</span>
                            </div>
                        </div>
                    `).join('');
                }
            } catch(e) { console.error(e); }
        }

        async function submitTask() {
            const task = document.getElementById('task-input').value;
            const model = document.getElementById('model-input').value;
            const provider = document.getElementById('provider-input').value;
            const maxiter = parseInt(document.getElementById('maxiter-input').value);
            const status = document.getElementById('task-status');
            status.textContent = 'Starting...';
            try {
                const r = await fetch('/run', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({task, model, provider, max_iterations: maxiter})
                });
                const d = await r.json();
                status.textContent = 'Task started: ' + d.session_id;
                setTimeout(loadStatus, 1000);
            } catch(e) { status.textContent = 'Error: ' + e.message; }
        }

        loadStatus();
        setInterval(loadStatus, 5000);
    </script>
</body>
</html>
"""


def ensure_templates():
    """Create the templates directory and write the HTML template."""
    templates_dir = DATA_DIR / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    index_path = templates_dir / "index.html"
    if not index_path.exists() or index_path.stat().st_size < 100:
        index_path.write_text(HTML_TEMPLATE, encoding="utf-8")


def run_console(host: str = "127.0.0.1", port: int = 5000):
    """Start the web console."""
    if not HAS_FLASK:
        print("[codex-local] Flask not installed. Web console unavailable.")
        print("[codex-local] Install with: pip install flask")
        return
    ensure_templates()
    print(f"[codex-local] Web console at http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_console()