"""Authentication service"""
from typing import Optional, Dict

class AuthService:
    """Handles authentication and session management"""

    def __init__(self, secret_key: str = "dev-secret"):
        self.secret_key = secret_key
        self._tokens: Dict[str, str] = {}

    def login(self, username: str, password: str) -> Optional[str]:
        """Authenticate user and return token"""
        if username == "admin" and password == "admin123":
            token = f"token_{username}_{self.secret_key}"
            self._tokens[token] = username
            return token
        return None

    def verify(self, token: str) -> Optional[str]:
        """Verify token and return username"""
        return self._tokens.get(token)

    def logout(self, token: str) -> bool:
        """Remove token"""
        if token in self._tokens:
            del self._tokens[token]
            return True
        return False
