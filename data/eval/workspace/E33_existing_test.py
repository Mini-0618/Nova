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

def test_large_input():
    large = ' ' * 1000000 + 'Hello World' + ' ' * 1000000
    assert normalize(large) == 'hello world'

def test_unicode():
    assert normalize('  café résumé  ') == 'café résumé'
    assert normalize('  日本語テスト  ') == '日本語テスト'
    assert normalize('  Привет мир  ') == 'привет мир'