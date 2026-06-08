import pytest

def classify_age(age):
    if age < 0: raise ValueError
    if age < 13: return 'child'
    if age < 18: return 'teen'
    if age < 65: return 'adult'
    return 'senior'


@pytest.mark.parametrize("age,expected", [
    # Edge case: negative age should raise ValueError
    pytest.param(-1, ValueError, id="negative_age_raises_error"),
    pytest.param(-100, ValueError, id="very_negative_age_raises_error"),
    # Boundary: age 0 (youngest valid)
    pytest.param(0, 'child', id="age_zero_is_child"),
    # Child range
    pytest.param(5, 'child', id="young_child"),
    pytest.param(12, 'child', id="almost_teen"),
    # Boundary: age 13 is teen
    pytest.param(13, 'teen', id="exactly_teen"),
    pytest.param(17, 'teen', id="almost_adult"),
    # Boundary: age 18 is adult
    pytest.param(18, 'adult', id="exactly_adult"),
    pytest.param(64, 'adult', id="almost_senior"),
    # Boundary: age 65 is senior
    pytest.param(65, 'senior', id="exactly_senior"),
    pytest.param(100, 'senior', id="very_old_senior"),
])
def test_classify_age(age, expected):
    if expected is ValueError:
        with pytest.raises(ValueError):
            classify_age(age)
    else:
        assert classify_age(age) == expected
