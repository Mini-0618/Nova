import pytest


def classify_age(age):
    if age < 0:
        raise ValueError("Age cannot be negative")
    if age < 13:
        return 'child'
    if age < 18:
        return 'teen'
    if age < 65:
        return 'adult'
    return 'senior'


@pytest.mark.parametrize("age, expected", [
    # Edge case: negative age should raise ValueError
    (-1, None),
    # Boundary: age 0 (minimum valid age)
    (0, 'child'),
    # Normal child age
    (5, 'child'),
    # Boundary: maximum child age (12)
    (12, 'child'),
    # Boundary: minimum teen age (13)
    (13, 'teen'),
    # Boundary: maximum teen age (17)
    (17, 'teen'),
    # Boundary: minimum adult age (18)
    (18, 'adult'),
    # Normal adult age
    (30, 'adult'),
    # Boundary: maximum adult age (64)
    (64, 'adult'),
    # Boundary: minimum senior age (65)
    (65, 'senior'),
    # Normal senior age
    (80, 'senior'),
    # Edge case: very large age
    (150, 'senior'),
])
def test_classify_age(age, expected):
    if age < 0:
        with pytest.raises(ValueError):
            classify_age(age)
    else:
        assert classify_age(age) == expected