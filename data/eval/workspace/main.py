from models import User
from repository import UserRepo


def main():
    repo = UserRepo()
    repo.add(User('alice', 'a@b.c'))
    assert repo.find_by_name('alice').email == 'a@b.c'
    assert repo.find_by_name('bob') is None
    print('PASS')


if __name__ == '__main__':
    main()
