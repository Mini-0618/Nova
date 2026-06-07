def normalize(s):
    if not s:
        return ''
    return s.strip().lower()

def test_basic():
    assert normalize('  Hello  ') == 'hello'

def test_empty():
    assert normalize('') == ''

# Edge case tests

def test_none_input():
    """None should return empty string (falsy check)."""
    assert normalize(None) == ''

def test_large_input():
    """Very large input should be handled correctly."""
    large_string = '  ' + 'A' * 1_000_000 + '  '
    result = normalize(large_string)
    assert result == 'a' * 1_000_000

def test_unicode_input():
    """Unicode characters should be lowercased correctly."""
    assert normalize('  Héllo Wörld  ') == 'héllo wörld'
    assert normalize('  日本語テスト  ') == '日本語テスト'
    assert normalize('  Ñoño  ') == 'ñoño'
    assert normalize('  Ελληνικά  ') == 'ελληνικά'
    assert normalize('  한국어  ') == '한국어'

def test_whitespace_only():
    """Strings with only whitespace should return empty string."""
    assert normalize('   ') == ''
    assert normalize('\t\n\r') == ''
    assert normalize('  \t  \n  \r  ') == ''