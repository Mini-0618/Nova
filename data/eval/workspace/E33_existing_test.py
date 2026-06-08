def normalize(s):
    if not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

def test_very_large_input():
    large = '  X ' * 10000
    expected = ('x ' * 10000).strip()
    result = normalize(large)
    assert len(result) == len(expected)
    assert result.count(' ') == expected.count(' ')
    assert result.replace(' ', '') == expected.replace(' ', '')

def test_unicode():
    assert normalize('  \u00c9l\u00e9phant  ') == '\u00e9l\u00e9phant'
    assert normalize('  M\u00fcnchen  ') == 'm\u00fcnchen'
    assert normalize('\u00a0') == '\u00a0'.strip()

def test_none():
    try:
        result = normalize(None)
        assert result == ''
    except (TypeError, AttributeError):
        pass