"""
RootCode Chatbot API
RESTful API for the Chatbot web interface.
Integrates SmartRouter and CodexLoop for intelligent responses.
Features: user auth, persistent sessions, history, memory integration.
"""

import os
import sys
import json
import time
import asyncio
import uuid
import hashlib
import secrets
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict, field
from functools import wraps

# Add parent directory to path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from flask import Flask, request, jsonify, render_template, send_from_directory, g
from flask_cors import CORS

# ─── Data directories ───────────────────────────────────────────────────────

DATA_DIR = _root / "data" / "chatbot"
SESSIONS_DIR = DATA_DIR / "sessions"
USERS_DIR = DATA_DIR / "users"
MEMORY_DIR = DATA_DIR / "memory"

for d in [DATA_DIR, SESSIONS_DIR, USERS_DIR, MEMORY_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: float
    model: Optional[str] = None
    complexity: Optional[str] = None
    cost: Optional[float] = None


@dataclass
class ChatSession:
    id: str
    user_id: str
    title: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    total_cost: float = 0.0
    model_used: Optional[str] = None


@dataclass
class User:
    id: str
    username: str
    password_hash: str
    salt: str
    created_at: float
    token: str


# ─── Persistence helpers ─────────────────────────────────────────────────────

def _hash_password(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def _save_json(path: Path, data: Any):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ─── User Store ──────────────────────────────────────────────────────────────

class UserStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _user_file(self, user_id: str) -> Path:
        return self.base_dir / f"{user_id}.json"

    def create_user(self, username: str, password: str) -> User:
        # Check duplicate
        for existing in self.list_users():
            if existing.username == username:
                raise ValueError("Username already exists")

        user_id = uuid.uuid4().hex[:12]
        salt = secrets.token_hex(16)
        password_hash = _hash_password(password, salt)
        token = secrets.token_hex(32)

        user = User(
            id=user_id,
            username=username,
            password_hash=password_hash,
            salt=salt,
            created_at=time.time(),
            token=token,
        )
        _save_json(self._user_file(user_id), asdict(user))
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        data = _load_json(self._user_file(user_id))
        if data:
            return User(**data)
        return None

    def get_user_by_token(self, token: str) -> Optional[User]:
        for user in self.list_users():
            if user.token == token:
                return user
        return None

    def verify_login(self, username: str, password: str) -> Optional[User]:
        for user in self.list_users():
            if user.username == username:
                computed = _hash_password(password, user.salt)
                if computed == user.password_hash:
                    return user
        return None

    def list_users(self) -> List[User]:
        users = []
        for f in self.base_dir.glob("*.json"):
            data = _load_json(f)
            if data:
                try:
                    users.append(User(**data))
                except Exception:
                    pass
        return users

    def user_count(self) -> int:
        return len(list(self.base_dir.glob("*.json")))


# ─── Session Store (file-backed) ─────────────────────────────────────────────

class SessionStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, ChatSession] = {}

    def _session_file(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.json"

    def _serialize_session(self, session: ChatSession) -> dict:
        return {
            "id": session.id,
            "user_id": session.user_id,
            "title": session.title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "total_cost": session.total_cost,
            "model_used": session.model_used,
            "messages": [asdict(m) for m in session.messages],
        }

    def _deserialize_session(self, data: dict) -> ChatSession:
        messages = [ChatMessage(**m) for m in data.get("messages", [])]
        return ChatSession(
            id=data["id"],
            user_id=data.get("user_id", ""),
            title=data.get("title", "New Chat"),
            messages=messages,
            created_at=data.get("created_at", 0),
            updated_at=data.get("updated_at", 0),
            total_cost=data.get("total_cost", 0.0),
            model_used=data.get("model_used"),
        )

    def create_session(self, user_id: str, title: str = "New Chat") -> ChatSession:
        session_id = uuid.uuid4().hex[:12]
        session = ChatSession(
            id=session_id,
            user_id=user_id,
            title=title,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._cache[session_id] = session
        self._persist(session)
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        if session_id in self._cache:
            return self._cache[session_id]
        data = _load_json(self._session_file(session_id))
        if data:
            session = self._deserialize_session(data)
            self._cache[session_id] = session
            return session
        return None

    def save_session(self, session: ChatSession):
        session.updated_at = time.time()
        self._cache[session.id] = session
        self._persist(session)

    def _persist(self, session: ChatSession):
        _save_json(self._session_file(session.id), self._serialize_session(session))

    def list_user_sessions(self, user_id: str, limit: int = 100) -> List[ChatSession]:
        sessions = []
        for f in self.base_dir.glob("*.json"):
            data = _load_json(f)
            if data and data.get("user_id") == user_id:
                try:
                    sessions.append(self._deserialize_session(data))
                except Exception:
                    pass
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions[:limit]

    def delete_session(self, session_id: str) -> bool:
        path = self._session_file(session_id)
        if path.exists():
            path.unlink()
            self._cache.pop(session_id, None)
            return True
        return False

    def add_message(self, session_id: str, message: ChatMessage):
        session = self.get_session(session_id)
        if session:
            session.messages.append(message)
            session.updated_at = time.time()
            # Auto-title from first user message
            if session.title == "New Chat" and message.role == "user":
                session.title = message.content[:40] + ("..." if len(message.content) > 40 else "")
            self.save_session(session)


# ─── Memory Store ─────────────────────────────────────────────────────────────

class MemoryStore:
    """Simple key-value memory per user for context persistence."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _user_memory_file(self, user_id: str) -> Path:
        return self.base_dir / f"{user_id}.json"

    def get_memories(self, user_id: str) -> Dict[str, Any]:
        return _load_json(self._user_memory_file(user_id)) or {}

    def set_memory(self, user_id: str, key: str, value: Any):
        memories = self.get_memories(user_id)
        memories[key] = {"value": value, "updated_at": time.time()}
        _save_json(self._user_memory_file(user_id), memories)

    def delete_memory(self, user_id: str, key: str) -> bool:
        memories = self.get_memories(user_id)
        if key in memories:
            del memories[key]
            _save_json(self._user_memory_file(user_id), memories)
            return True
        return False

    def get_context_summary(self, user_id: str) -> str:
        """Build a context string from user memories for LLM prompt."""
        memories = self.get_memories(user_id)
        if not memories:
            return ""
        lines = []
        for key, entry in memories.items():
            val = entry.get("value", "")
            lines.append(f"- {key}: {val}")
        return "用户记忆:\n" + "\n".join(lines)


# ─── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)
app.secret_key = secrets.token_hex(32)

# ─── Global Instances ─────────────────────────────────────────────────────────

user_store = UserStore(USERS_DIR)
session_store = SessionStore(SESSIONS_DIR)
memory_store = MemoryStore(MEMORY_DIR)

# Try importing SmartRouter (optional)
try:
    from runtime.smart_router import SmartRouter, TaskComplexity
    smart_router = SmartRouter(monthly_budget=50.0)
    HAS_ROUTER = True
except ImportError:
    smart_router = None
    HAS_ROUTER = False


# ─── Auth Middleware ──────────────────────────────────────────────────────────

def require_auth(f):
    """Decorator: require valid auth token in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else request.args.get("token", "")

        if not token:
            return jsonify({"success": False, "error": "Missing auth token"}), 401

        user = user_store.get_user_by_token(token)
        if not user:
            return jsonify({"success": False, "error": "Invalid token"}), 401

        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def optional_auth(f):
    """Decorator: attach user if token present, but don't require it."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else request.args.get("token", "")
        g.current_user = None
        if token:
            g.current_user = user_store.get_user_by_token(token)
        return f(*args, **kwargs)
    return decorated


# ─── System Prompts ───────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "default": """你是RootCode AI助手，一个智能编程助手。你可以帮助用户：
- 写代码、改bug、解释代码
- 学习编程、解答技术问题
- 代码审查、安全检查
- 技术方案设计

请用友好、专业的方式回答问题。如果涉及代码，请使用代码块格式。""",

    "code": """你是一个专业的编程助手。请专注于代码相关的问题：
- 写出高质量、可维护的代码
- 提供清晰的代码解释
- 给出最佳实践建议
- 检查代码问题和安全隐患

请用代码块格式展示代码，并添加必要的注释。""",

    "learning": """你是一个耐心的编程教师。请帮助用户学习编程：
- 用简单易懂的语言解释概念
- 提供循序渐进的学习路径
- 给出练习题目和示例
- 鼓励用户动手实践

请用友好的方式教学，避免使用过于专业的术语。""",

    "review": """你是一个严格的代码审查专家。请帮助用户检查代码：
- 发现潜在的bug和安全隐患
- 检查代码风格和规范
- 提供优化建议
- 评估代码质量

请用专业的方式指出问题，并提供改进建议。""",
}


# ─── API Routes: Auth ─────────────────────────────────────────────────────────

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """Check if any users exist (public)."""
    return jsonify({
        "success": True,
        "has_users": user_store.user_count() > 0,
    })


@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user (public)."""
    data = request.json
    username = (data or {}).get("username", "").strip()
    password = (data or {}).get("password", "")

    if not username or len(username) < 2:
        return jsonify({"success": False, "error": "Username must be at least 2 characters"}), 400
    if not password or len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

    try:
        user = user_store.create_user(username, password)
        return jsonify({"success": True, "token": user.token, "username": user.username, "user_id": user.id})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 409


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login with username/password (public)."""
    data = request.json
    username = (data or {}).get("username", "").strip()
    password = (data or {}).get("password", "")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    user = user_store.verify_login(username, password)
    if not user:
        return jsonify({"success": False, "error": "Invalid username or password"}), 401

    return jsonify({"success": True, "token": user.token, "username": user.username, "user_id": user.id})


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me():
    """Get current user info."""
    user = g.current_user
    return jsonify({
        "success": True,
        "user_id": user.id,
        "username": user.username,
        "created_at": user.created_at,
    })


# ─── API Routes: Chat ─────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Serve the chatbot interface"""
    return render_template('chatbot.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory(app.static_folder, filename)


@app.route('/api/chat', methods=['POST'])
@require_auth
def chat():
    """Main chat endpoint with auth."""
    try:
        data = request.json
        if not data or 'message' not in data:
            return jsonify({"success": False, "error": "Missing 'message' field"}), 400

        user = g.current_user
        user_message = data['message']
        session_id = data.get('session_id')
        mode = data.get('mode', 'default')

        # Get or create session
        if session_id:
            session = session_store.get_session(session_id)
            if not session or session.user_id != user.id:
                session = session_store.create_session(user.id)
        else:
            session = session_store.create_session(user.id)

        # Add user message
        user_msg = ChatMessage(
            id=uuid.uuid4().hex[:12],
            role="user",
            content=user_message,
            timestamp=time.time(),
        )
        session_store.add_message(session.id, user_msg)

        # Smart routing
        if HAS_ROUTER:
            routing_result = smart_router.route(task=user_message, require_tools=False)
            model_key = routing_result["model_key"]
            complexity = routing_result["complexity"]
            estimated_cost = routing_result["estimated_cost"]
        else:
            model_key = "local/default"
            complexity = type("C", (), {"value": "simple"})()
            estimated_cost = 0.0

        # Build context
        history = session.messages[-11:-1]  # last 10 excluding the one we just added
        context_parts = [f"{m.role}: {m.content}" for m in history]
        memory_context = memory_store.get_context_summary(user.id)
        if memory_context:
            context_parts.insert(0, memory_context)
        context = "\n".join(context_parts)

        # Generate response
        response_text = generate_response(user_message, mode=mode, context=context)

        # Add assistant message
        assistant_msg = ChatMessage(
            id=uuid.uuid4().hex[:12],
            role="assistant",
            content=response_text,
            timestamp=time.time(),
            model=model_key,
            complexity=complexity.value if hasattr(complexity, 'value') else str(complexity),
            cost=estimated_cost,
        )
        session_store.add_message(session.id, assistant_msg)

        # Update session stats
        session.total_cost += estimated_cost
        session.model_used = model_key
        session_store.save_session(session)

        return jsonify({
            "success": True,
            "response": response_text,
            "session_id": session.id,
            "model": model_key,
            "complexity": complexity.value if hasattr(complexity, 'value') else str(complexity),
            "cost": estimated_cost,
            "total_cost": session.total_cost,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── API Routes: Sessions ─────────────────────────────────────────────────────

@app.route('/api/sessions', methods=['GET'])
@require_auth
def list_sessions():
    """List sessions for the current user."""
    try:
        user = g.current_user
        sessions = session_store.list_user_sessions(user.id)
        return jsonify({
            "success": True,
            "sessions": [{
                "id": s.id,
                "title": s.title,
                "message_count": len(s.messages),
                "total_cost": s.total_cost,
                "model_used": s.model_used,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            } for s in sessions],
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/sessions/<session_id>', methods=['GET'])
@require_auth
def get_session_detail(session_id: str):
    """Get full session with messages."""
    try:
        user = g.current_user
        session = session_store.get_session(session_id)
        if not session or session.user_id != user.id:
            return jsonify({"success": False, "error": "Session not found"}), 404

        return jsonify({
            "success": True,
            "session": {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "total_cost": session.total_cost,
                "model_used": session.model_used,
                "messages": [asdict(m) for m in session.messages],
            },
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
@require_auth
def delete_session(session_id: str):
    """Delete a session."""
    try:
        user = g.current_user
        session = session_store.get_session(session_id)
        if not session or session.user_id != user.id:
            return jsonify({"success": False, "error": "Session not found"}), 404

        session_store.delete_session(session_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/sessions/<session_id>/rename', methods=['POST'])
@require_auth
def rename_session(session_id: str):
    """Rename a session."""
    try:
        user = g.current_user
        session = session_store.get_session(session_id)
        if not session or session.user_id != user.id:
            return jsonify({"success": False, "error": "Session not found"}), 404

        data = request.json
        new_title = (data or {}).get("title", "").strip()
        if not new_title:
            return jsonify({"success": False, "error": "Title is required"}), 400

        session.title = new_title
        session_store.save_session(session)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── API Routes: Memory ───────────────────────────────────────────────────────

@app.route('/api/memory', methods=['GET'])
@require_auth
def get_memory():
    """Get all memories for current user."""
    try:
        user = g.current_user
        memories = memory_store.get_memories(user.id)
        return jsonify({"success": True, "memories": memories})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/memory', methods=['POST'])
@require_auth
def set_memory():
    """Set a memory key-value pair."""
    try:
        user = g.current_user
        data = request.json
        key = (data or {}).get("key", "").strip()
        value = (data or {}).get("value", "")
        if not key:
            return jsonify({"success": False, "error": "Key is required"}), 400

        memory_store.set_memory(user.id, key, value)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/memory/<key>', methods=['DELETE'])
@require_auth
def delete_memory(key: str):
    """Delete a memory entry."""
    try:
        user = g.current_user
        deleted = memory_store.delete_memory(user.id, key)
        if not deleted:
            return jsonify({"success": False, "error": "Key not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── API Routes: Models & Stats ───────────────────────────────────────────────

@app.route('/api/models', methods=['GET'])
def list_models():
    """List available models."""
    try:
        if HAS_ROUTER:
            from runtime.smart_router import MODEL_REGISTRY
            models = []
            for key, config in MODEL_REGISTRY.items():
                models.append({
                    "key": key,
                    "provider": config.provider,
                    "model": config.model,
                    "tier": config.tier.value,
                    "cost_per_1k_input": config.cost_per_1k_input,
                    "cost_per_1k_output": config.cost_per_1k_output,
                    "quality_score": config.quality_score,
                    "avg_latency_ms": config.avg_latency_ms,
                })
            return jsonify({"success": True, "models": models})
        else:
            return jsonify({"success": True, "models": [{"key": "local/default", "provider": "local", "model": "default"}]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/stats', methods=['GET'])
@require_auth
def get_stats():
    """Get user stats."""
    try:
        user = g.current_user
        sessions = session_store.list_user_sessions(user.id)
        total_messages = sum(len(s.messages) for s in sessions)
        total_cost = sum(s.total_cost for s in sessions)
        return jsonify({
            "success": True,
            "stats": {
                "total_sessions": len(sessions),
                "total_messages": total_messages,
                "total_cost": total_cost,
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Response Generation ──────────────────────────────────────────────────────

def generate_response(
    user_message: str,
    mode: str = "default",
    context: str = "",
) -> str:
    """Generate AI response based on user message and context."""
    message_lower = user_message.lower()

    code_keywords = ["代码", "函数", "bug", "错误", "实现", "写", "code", "function", "error", "implement", "def ", "class ", "import "]
    is_code_request = any(kw in message_lower for kw in code_keywords)

    learn_keywords = ["学习", "教程", "怎么", "什么是", "解释", "learn", "tutorial", "how", "what is"]
    is_learning_request = any(kw in message_lower for kw in learn_keywords)

    if mode == "code" or is_code_request:
        return generate_code_response(user_message)
    elif mode == "learning" or is_learning_request:
        return generate_learning_response(user_message)
    elif mode == "review":
        return generate_review_response(user_message)
    else:
        return generate_general_response(user_message)


def generate_code_response(message: str) -> str:
    """Generate code-related response."""
    if "斐波那契" in message or "fibonacci" in message.lower():
        return (
            "好嘞！这是一个计算斐波那契数列的函数：\n\n"
            "```python\n"
            "def fibonacci(n):\n"
            "    if n <= 1:\n"
            "        return n\n"
            "    a, b = 0, 1\n"
            "    for _ in range(2, n + 1):\n"
            "        a, b = b, a + b\n"
            "    return b\n\n"
            "# 测试\n"
            "for i in range(10):\n"
            "    print(f'fibonacci({i}) = {fibonacci(i)}')\n"
            "```\n\n"
            "要我加个递归版本不？或者解释一下这个算法的原理？"
        )
    elif "排序" in message or "sort" in message.lower():
        return (
            "好嘞！这是几种常见嘞排序算法：\n\n"
            "**1. 冒泡排序（简单但慢）**\n"
            "```python\n"
            "def bubble_sort(arr):\n"
            "    n = len(arr)\n"
            "    for i in range(n):\n"
            "        for j in range(0, n-i-1):\n"
            "            if arr[j] > arr[j+1]:\n"
            "                arr[j], arr[j+1] = arr[j+1], arr[j]\n"
            "    return arr\n"
            "```\n\n"
            "**2. 快速排序（常用）**\n"
            "```python\n"
            "def quick_sort(arr):\n"
            "    if len(arr) <= 1:\n"
            "        return arr\n"
            "    pivot = arr[len(arr) // 2]\n"
            "    left = [x for x in arr if x < pivot]\n"
            "    middle = [x for x in arr if x == pivot]\n"
            "    right = [x for x in arr if x > pivot]\n"
            "    return quick_sort(left) + middle + quick_sort(right)\n"
            "```\n\n"
            "要我解释一下它们的时间复杂度不？"
        )
    else:
        return (
            "好嘞！根据你嘞需求，这是一个示例代码：\n\n"
            "```python\n"
            "# 示例代码\n"
            "def main():\n"
            "    print('Hello, RootCode!')\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
            "```\n\n"
            "你可以告诉我更具体嘞需求，比如：\n"
            "- 要实现什么功能？\n"
            "- 用什么语言？\n"
            "- 有什么特殊要求？\n\n"
            "我来给你写更准确嘞代码~"
        )


def generate_learning_response(message: str) -> str:
    """Generate learning-related response."""
    if "python" in message.lower():
        return (
            "好嘞！Python是一个非常适合入门的编程语言，我来给你讲讲基础：\n\n"
            "## Python基础\n\n"
            "**1. 变量和数据类型**\n"
            "```python\n"
            "age = 25            # 数字\n"
            "name = 'RootCode'   # 字符串\n"
            "is_student = True   # 布尔\n"
            "scores = [90, 85]   # 列表\n"
            "person = {'name': '张三', 'age': 25}  # 字典\n"
            "```\n\n"
            "**2. 条件和循环**\n"
            "```python\n"
            "if age >= 18:\n"
            "    print('成年人')\n"
            "else:\n"
            "    print('未成年人')\n\n"
            "for score in scores:\n"
            "    print(score)\n"
            "```\n\n"
            "**3. 函数**\n"
            "```python\n"
            "def greet(name):\n"
            "    return f'你好，{name}！'\n\n"
            "print(greet('RootCode'))\n"
            "```\n\n"
            "你想学哪个部分？我可以给你更多例子和练习题~"
        )
    else:
        return (
            "好嘞！编程入门路径：\n\n"
            "**第一步：选择语言**\n"
            "- Python：简单易学，适合入门\n"
            "- JavaScript：做网页必备\n"
            "- Java：企业开发常用\n\n"
            "**第二步：学习基础**\n"
            "- 变量和数据类型\n"
            "- 条件判断（if/else）\n"
            "- 循环（for/while）\n"
            "- 函数\n\n"
            "**第三步：动手实践**\n"
            "- 写小程序练手\n"
            "- 参与开源项目\n"
            "- 做个人项目\n\n"
            "你想从哪个语言开始学？我来给你制定学习计划~"
        )


def generate_review_response(message: str) -> str:
    """Generate code review response."""
    return (
        "好的，我来帮你审查代码。请把代码贴过来，我会从以下几个方面检查：\n\n"
        "1. **Bug风险** - 潜在的运行时错误\n"
        "2. **安全隐患** - SQL注入、XSS等\n"
        "3. **代码风格** - 命名规范、格式一致性\n"
        "4. **性能问题** - 不必要的循环、内存泄漏\n"
        "5. **可维护性** - 代码结构、注释质量\n\n"
        "请把需要审查的代码贴过来吧~"
    )


def generate_general_response(message: str) -> str:
    """Generate general response."""
    return (
        "你好！我是RootCode AI助手，很高兴为你服务~\n\n"
        "我可以帮你：\n"
        "- **写代码**：告诉我你的需求，我来实现\n"
        "- **改bug**：粘贴错误代码，我来修复\n"
        "- **解释代码**：粘贴代码，我来逐行解释\n"
        "- **代码审查**：检查代码问题和安全隐患\n"
        "- **学习编程**：解答技术问题，提供学习路径\n\n"
        "有什么我可以帮你的不？"
    )


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def run_chatbot(host='0.0.0.0', port=5001, debug=False):
    """Run the chatbot server"""
    print(f"[RootCode Chatbot] Starting on http://{host}:{port}")
    print(f"[RootCode Chatbot] Data dir: {DATA_DIR}")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="RootCode Chatbot Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5001, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    run_chatbot(host=args.host, port=args.port, debug=args.debug)
