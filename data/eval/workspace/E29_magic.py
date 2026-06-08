BULK_DISCOUNT_THRESHOLD = 100
MEDIUM_DISCOUNT_THRESHOLD = 50
BULK_DISCOUNT_RATE = 0.1
MEDIUM_DISCOUNT_RATE = 0.05
NO_DISCOUNT = 0
FLAT_DISCOUNT_THRESHOLD = 500
FLAT_DISCOUNT_AMOUNT = 25


def calculate_price(quantity, unit_price):
    if quantity > BULK_DISCOUNT_THRESHOLD:
        discount = BULK_DISCOUNT_RATE
    elif quantity > MEDIUM_DISCOUNT_THRESHOLD:
        discount = MEDIUM_DISCOUNT_RATE
    else:
        discount = NO_DISCOUNT
    total = quantity * unit_price * (1 - discount)
    if total > FLAT_DISCOUNT_THRESHOLD:
        total -= FLAT_DISCOUNT_AMOUNT
    return total

if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 545.0
    assert calculate_price(200, 5) == 875.0
    print('PASS')