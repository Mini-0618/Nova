import pytest

def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'


@pytest.mark.parametrize("age,expected", [
    (0, 'child'),       # boundary: youngest child
    (5, 'child'),       # typical child
    (12, 'child'),      # boundary: just before teen
    (13, 'teen'),       # boundary: youngest teen
    (15, 'teen'),       # typical teen
    (17, 'teen'),       # boundary: just before adult
    (18, 'adult'),      # boundary: youngest adult
    (30, 'adult'),      # typical adult
    (64, 'adult'),      # boundary: just before senior
    (65, 'senior'),     # boundary: youngest senior
    (100, 'senior'),    # typical senior
])
def test_classify_age(age, expected):
    assert classify_age(age) == expected


@pytest.mark.parametrize("age", [
    -1,
    -100,
])
def test_classify_age_invalid(age):
    with pytest.raises(ValueError):
        classify_age(age)
