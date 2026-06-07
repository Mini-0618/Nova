def read_file(path):
    with open(path, 'r') as f:  # BUG: no encoding specified
        return f.read()

if __name__ == '__main__':
    content = read_file('data/eval/fixtures/chinese.txt')
    assert '你好' in content, f'Expected Chinese chars, got: {content}'
    print('PASS')