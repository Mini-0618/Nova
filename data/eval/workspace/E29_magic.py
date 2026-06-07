# Named constants for thresholds and discounts
LARGE_QUANTITY_THRESHOLD = 100
LARGE_QUANTITY_DISCOUNT = 0.1
MEDIUM_QUANTITY_THRESHOLD = 50
MEDIUM_QUANTITY_DISCOUNT = 0.05
NO_DISCOUNT = 0
FREE_SHIPPING_THRESHOLD = 500
SHIPPING_COST = 25


def calculate_price(quantity, unit_price):
    if quantity > LARGE_QUANTITY_THRESHOLD:
        discount = LARGE_QUANTITY_DISCOUNT
    elif quantity > MEDIUM_QUANTITY_THRESHOLD:
        discount = MEDIUM_QUANTITY_DISCOUNT
    else:
        discount = NO_DISCOUNT
    total = quantity * unit_price * (1 - discount)
    if total > FREE_SHIPPING_THRESHOLD:
        total -= SHIPPING_COST
    return total

if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 570.0
    assert calculate_price(200, 5) == 900.0
    print('PASS')