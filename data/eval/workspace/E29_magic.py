BULK_DISCOUNT_THRESHOLD = 100
BULK_DISCOUNT_RATE = 0.1
MEDIUM_DISCOUNT_THRESHOLD = 50
MEDIUM_DISCOUNT_RATE = 0.05
NO_DISCOUNT = 0
EXTRA_DISCOUNT_THRESHOLD = 500
EXTRA_DISCOUNT_AMOUNT = 25


def calculate_price(quantity, unit_price):
    if quantity > BULK_DISCOUNT_THRESHOLD:
        discount = BULK_DISCOUNT_RATE
    elif quantity > MEDIUM_DISCOUNT_THRESHOLD:
        discount = MEDIUM_DISCOUNT_RATE
    else:
        discount = NO_DISCOUNT
    total = quantity * unit_price * (1 - discount)
    if total > EXTRA_DISCOUNT_THRESHOLD:
        total -= EXTRA_DISCOUNT_AMOUNT
    return total


if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 570.0
    assert calculate_price(200, 5) == 900.0
    print('PASS')
