def add_item(item, lst=None):  # Fixed: no mutable default
    if lst is None:
        lst = []
    lst.append(item)
    return lst

if __name__ == '__main__':
    r1 = add_item('a')
    r2 = add_item('b')
    assert r2 == ['b'], f'Expected ["b"], got {r2}'
    print('PASS')