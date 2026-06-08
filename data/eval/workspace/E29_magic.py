# Named constants
QUANTITY_DISCOUNT_TIER1 = 100
QUANTITY_DISCOUNT_TIER2 = 50
DISCOUNT_TIER1 = 0.1
DISCOUNT_TIER2 = 0.05
DISCOUNT_NONE = 0
FLAT_DISCOUNT_THRESHOLD = 500
FLAT_DISCOUNT_AMOUNT = 25


def calculate_price(quantity, unit_price):
    if quantity > QUANTITY_DISCOUNT_TIER1:
        discount = DISCOUNT_TIER1
    elif quantity > QUANTITY_DISCOUNT_TIER2:
        discount = DISCOUNT_TIER2
    else:
        discount = DISCOUNT_NONE
    total = quantity * unit_price * (1 - discount)
    if total > FLAT_DISCOUNT_THRESHOLD:
        total -= FLAT_DISCOUNT_AMOUNT
    return total


if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 545.0
    assert calculate_price(200, 5) == 875.0
    print('PASS')