import pytest

def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'


@pytest.mark.parametrize("age,expected", [
    (0, 'child'),         # edge: newborn
    (5, 'child'),         # typical child
    (12, 'child'),        # edge: just below teen
    (13, 'teen'),         # edge: just at teen
    (15, 'teen'),         # typical teen
    (17, 'teen'),         # edge: just below adult
    (18, 'adult'),        # edge: just at adult
    (30, 'adult'),        # typical adult
    (64, 'adult'),        # edge: just below senior
    (65, 'senior'),       # edge: just at senior
    (100, 'senior'),      # typical senior
])
def test_classify_age(age, expected):
    assert classify_age(age) == expected


@pytest.mark.parametrize("invalid_age", [
    -1,   # just below zero
    -100, # very negative
])
def test_classify_age_invalid(invalid_age):
    with pytest.raises(ValueError):
        classify_age(invalid_age)
