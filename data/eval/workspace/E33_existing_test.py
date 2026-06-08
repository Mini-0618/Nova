def normalize(s):
    if s is None or not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

def test_large_input():
    large = '  HELLO  ' * 10000
    result = normalize(large)
    assert result == ('hello  ' * 10000).strip()

def test_unicode():
    assert normalize('  Café  ') == 'café'
    assert normalize('  \u00e9\u00e0\u00fc  ') == '\u00e9\u00e0\u00fc'
    assert normalize('  MÜNCHEN  ') == 'münchen'

def test_none():
    assert normalize(None) == ''