import json
from models import User


class UserRepo:
    def __init__(self, path='data/eval/workspace/E38_users.json'):
        self.path = path
        self.users = []
    def add(self, user):
        self.users.append(user)
        self._save()
    def find_by_name(self, name):
        for u in self.users:
            if u.name == name:
                return u
        return None
    def _save(self):
        with open(self.path, 'w') as f:
            json.dump([u.to_dict() for u in self.users], f)
