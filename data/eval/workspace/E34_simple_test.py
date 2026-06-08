import pytest

def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'


@pytest.mark.parametrize("age,expected", [
    (0, 'child'),        # edge case: newborn
    (5, 'child'),        # typical child
    (12, 'child'),       # edge case: just under teen
    (13, 'teen'),        # edge case: exactly teen
    (15, 'teen'),        # typical teen
    (17, 'teen'),        # edge case: just under adult
    (18, 'adult'),       # edge case: exactly adult
    (30, 'adult'),       # typical adult
    (64, 'adult'),       # edge case: just under senior
    (65, 'senior'),      # edge case: exactly senior
    (100, 'senior'),     # typical senior
])
def test_classify_age(age, expected):
    assert classify_age(age) == expected


@pytest.mark.parametrize("invalid_age", [
    -1,                   # edge case: negative age
    -100,                 # very negative
])
def test_classify_age_invalid(invalid_age):
    with pytest.raises(ValueError):
        classify_age(invalid_age)
