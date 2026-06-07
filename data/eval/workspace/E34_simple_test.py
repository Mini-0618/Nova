import pytest


def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'


@pytest.mark.parametrize("age, expected", [
    (-1, ValueError),         # edge: negative age should raise ValueError
    (0, 'child'),             # edge: zero is a child
    (1, 'child'),             # typical: very young child
    (12, 'child'),            # edge: just below teen boundary
    (13, 'teen'),             # edge: exactly teen boundary
    (15, 'teen'),             # typical: mid-teen
    (17, 'teen'),             # edge: just below adult boundary
    (18, 'adult'),            # edge: exactly adult boundary
    (30, 'adult'),            # typical: typical adult
    (64, 'adult'),            # edge: just below senior boundary
    (65, 'senior'),           # edge: exactly senior boundary
    (100, 'senior'),          # typical: elderly person
])
def test_classify_age(age, expected):
    if expected is ValueError:
        with pytest.raises(ValueError):
            classify_age(age)
    else:
        assert classify_age(age) == expected
