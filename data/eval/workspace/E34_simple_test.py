import pytest

def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'


@pytest.mark.parametrize("age,expected", [
    (5, 'child'),          # young child
    (12, 'child'),         # upper edge of child
    (13, 'teen'),          # lower edge of teen
    (15, 'teen'),          # middle teen
    (17, 'teen'),          # upper edge of teen
    (18, 'adult'),         # lower edge of adult
    (30, 'adult'),         # middle adult
    (64, 'adult'),         # upper edge of adult
    (65, 'senior'),        # lower edge of senior
    (100, 'senior'),       # senior
])
def test_classify_age(age, expected):
    assert classify_age(age) == expected


@pytest.mark.parametrize("invalid_age", [
    -1,
    -100,
])
def test_invalid_age(invalid_age):
    with pytest.raises(ValueError):
        classify_age(invalid_age)
