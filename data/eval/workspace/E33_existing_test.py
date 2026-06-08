def normalize(s):
    if not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

def test_very_large_input():
    large = '  HELLO ' * 10000
    expected = ('hello ' * 10000).strip()
    assert normalize(large) == expected

def test_unicode():
    assert normalize('  Café  ') == 'café'
    assert normalize('  \u00c9l\u00e9phant  ') == 'éléphant'
    assert normalize('  \u4e2d\u56fd  ') == '\u4e2d\u56fd'

def test_none():
    assert normalize(None) == ''