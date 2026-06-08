import pytest

def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'


@pytest.mark.parametrize("age,expected", [
    (0, 'child'),       # edge: newborn
    (1, 'child'),       # edge: infant
    (12, 'child'),      # edge: just below teen boundary
    (13, 'teen'),       # edge: exactly teen boundary
    (17, 'teen'),       # edge: just below adult boundary
    (18, 'adult'),      # edge: exactly adult boundary
    (64, 'adult'),      # edge: just below senior boundary
    (65, 'senior'),     # edge: exactly senior boundary
    (100, 'senior'),    # edge: old age
])
def test_classify_age(age, expected):
    assert classify_age(age) == expected


@pytest.mark.parametrize("invalid_age", [
    -1,     # edge: just below zero
    -100,   # edge: very negative
])
def test_classify_age_invalid(invalid_age):
    with pytest.raises(ValueError):
        classify_age(invalid_age)
