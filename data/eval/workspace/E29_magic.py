LARGE_BULK_THRESHOLD = 100
LARGE_BULK_DISCOUNT = 0.1
MEDIUM_BULK_THRESHOLD = 50
MEDIUM_BULK_DISCOUNT = 0.05
FREE_SHIPPING_THRESHOLD = 500
SHIPPING_DEDUCTION = 25


def calculate_price(quantity, unit_price):
    if quantity > LARGE_BULK_THRESHOLD:
        discount = LARGE_BULK_DISCOUNT
    elif quantity > MEDIUM_BULK_THRESHOLD:
        discount = MEDIUM_BULK_DISCOUNT
    else:
        discount = 0
    total = quantity * unit_price * (1 - discount)
    if total > FREE_SHIPPING_THRESHOLD:
        total -= SHIPPING_DEDUCTION
    return total

if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 570.0
    assert calculate_price(200, 5) == 900.0
    print('PASS')