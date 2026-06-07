import json

class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
    def to_dict(self):
        return {'name': self.name, 'email': self.email}

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

if __name__ == '__main__':
    repo = UserRepo()
    repo.add(User('alice', 'a@b.c'))
    assert repo.find_by_name('alice').email == 'a@b.c'
    assert repo.find_by_name('bob') is None
    print('PASS')