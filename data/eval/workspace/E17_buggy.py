def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

if __name__ == '__main__':
    content = read_file('data/eval/fixtures/chinese.txt')
    assert '你好' in content, f'Expected Chinese chars, got: {content}'
    print('PASS')