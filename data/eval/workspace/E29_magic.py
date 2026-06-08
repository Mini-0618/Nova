def calculate_price(quantity, unit_price):
    if quantity > 100:  # magic number
        discount = 0.1
    elif quantity > 50:  # magic number
        discount = 0.05
    else:
        discount = 0
    total = quantity * unit_price * (1 - discount)
    if total > 500:  # magic number
        total -= 25  # magic number
    return total

if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 570.0
    assert calculate_price(200, 5) == 900.0
    print('PASS')