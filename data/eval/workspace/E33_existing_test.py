def normalize(s):
    if not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

def test_very_large_input():
    large = 'x' * 10000
    result = normalize(large)
    assert result == 'x' * 10000

def test_unicode():
    assert normalize('  Café  ') == 'café'
    assert normalize('  ñoño  ') == 'ñoño'
    assert normalize('  你好  ') == '你好'

def test_none():
    assert normalize(None) == ''