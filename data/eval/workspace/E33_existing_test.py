def normalize(s):
    if not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

def test_very_large():
    large = '  x' * 100000 + '  '
    result = normalize(large)
    assert result == ('x' * 100000)

def test_unicode():
    assert normalize('  Café  ') == 'café'
    assert normalize('  \u00e9\u00e0\u00fc  ') == '\u00e9\u00e0\u00fc'
    assert normalize('  \u4e2d\u6587  ') == '\u4e2d\u6587'

def test_none():
    try:
        normalize(None)
        assert False, "Expected exception"
    except (TypeError, AttributeError):
        pass