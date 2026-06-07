people = [{'name': 'alice', 'age': 30}, {'name': 'bob', 'age': 20}, {'name': 'carol', 'age': 25}]

def sort_by_age(ppl):
    return sorted(ppl, key=lambda p: p['age'])

if __name__ == '__main__':
    result = sort_by_age(people)
    assert result[0]['name'] == 'bob', f'Youngest first should be bob, got {result[0]["name"]}'
    assert result[-1]['name'] == 'alice', f'Oldest last should be alice, got {result[-1]["name"]}'
    print('PASS')