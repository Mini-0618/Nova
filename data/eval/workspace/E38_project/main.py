import sys
import os

# Add the project directory to the path so imports work
sys.path.insert(0, os.path.dirname(__file__))

from models import User
from repository import UserRepo

if __name__ == '__main__':
    repo = UserRepo()
    repo.add(User('alice', 'a@b.c'))
    assert repo.find_by_name('alice').email == 'a@b.c'
    assert repo.find_by_name('bob') is None
    print('PASS')
