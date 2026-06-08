import pytest

def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'

@pytest.mark.parametrize("age,expected", [
    (5, 'child'),          # child age
    (0, 'child'),          # edge: age 0 (youngest child)
    (12, 'child'),         # edge: max child
    (13, 'teen'),          # edge: min teen
    (15, 'teen'),          # teen age
    (17, 'teen'),          # edge: max teen
    (18, 'adult'),         # edge: min adult
    (30, 'adult'),         # adult age
    (64, 'adult'),         # edge: max adult
    (65, 'senior'),        # edge: min senior
    (100, 'senior'),       # senior age
])
def test_classify_age(age, expected):
    assert classify_age(age) == expected

@pytest.mark.parametrize("invalid_age", [
    -1,                    # edge: negative
    -100,                  # negative value
])
def test_classify_age_invalid(invalid_age):
    with pytest.raises(ValueError):
        classify_age(invalid_age)
