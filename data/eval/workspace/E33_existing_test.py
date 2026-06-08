def normalize(s):
    if not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

def test_none():
    assert normalize(None) == ''

def test_unicode():
    assert normalize('  Café  ') == 'café'
    assert normalize('  über  ') == 'über'
    assert normalize('  ñoño  ') == 'ñoño'

def test_large_input():
    large = '  ' + 'a' * 100000 + '  '
    result = normalize(large)
    assert result == 'a' * 100000
    assert len(result) == 100000