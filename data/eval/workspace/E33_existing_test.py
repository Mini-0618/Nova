def normalize(s):
    if not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

def test_whitespace_only():
    assert normalize('   ') == ''

def test_very_large_input():
    large = '  HELLO ' * 10000
    result = normalize(large)
    # normalize does s.strip().lower(), so '  HELLO ' * 10000 becomes 'hello   hello   ... hello'
    expected = ('  HELLO ' * 10000).strip().lower()
    assert result == expected

def test_unicode():
    assert normalize('  Café  ') == 'café'
    assert normalize('  ıstanbul  ') == 'ıstanbul'
    assert normalize('  naïve  ') == 'naïve'

def test_none():
    try:
        normalize(None)
        assert False, "Expected TypeError or similar"
    except (TypeError, AttributeError):
        pass