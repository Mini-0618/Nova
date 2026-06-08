def normalize(s):
    if s is None:
        return ''
    if not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

def test_none():
    assert normalize(None) == ''

def test_very_large_input():
    large = '  X' * 10000 + '  '
    result = normalize(large)
    expected = ('x' * 10000).lower()
    assert result == expected, f"Expected length {len(expected)}, got length {len(result)}"

def test_unicode():
    assert normalize('  Café  ') == 'café'
    assert normalize('  MÜNCHEN  ') == 'münchen'
    assert normalize('  日本語  ') == '日本語'
    assert normalize('  \u00c9\u00e9  ') == 'éé'