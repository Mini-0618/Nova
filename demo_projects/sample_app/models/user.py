"""User model"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class User:
    """User entity"""
    id: int
    name: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)

    def greet(self) -> str:
        return f"Hello, {self.name}!"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }


def create_user(name: str, email: str) -> User:
    """Factory function to create a user"""
    return User(id=hash(name) % 10000, name=name, email=email)