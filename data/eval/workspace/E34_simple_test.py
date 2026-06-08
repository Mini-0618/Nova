import pytest

def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'


@pytest.mark.parametrize("age,expected", [
    (0, 'child'),          # newborn (edge case: boundary at 0)
    (5, 'child'),          # child
    (12, 'child'),         # child just before teen boundary
    (13, 'teen'),          # teen (edge case: boundary at 13)
    (17, 'teen'),          # teen just before adult boundary
    (18, 'adult'),         # adult (edge case: boundary at 18)
    (64, 'adult'),         # adult just before senior boundary
    (65, 'senior'),        # senior (edge case: boundary at 65)
    (100, 'senior'),       # senior (old age)
])
def test_classify_age(age, expected):
    assert classify_age(age) == expected


@pytest.mark.parametrize("invalid_age", [
    -1,     # negative (edge case)
    -100,   # very negative
])
def test_classify_age_invalid(invalid_age):
    with pytest.raises(ValueError):
        classify_age(invalid_age)
