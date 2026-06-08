BULK_DISCOUNT_THRESHOLD_HIGH = 100
BULK_DISCOUNT_RATE_HIGH = 0.1
BULK_DISCOUNT_THRESHOLD_MEDIUM = 50
BULK_DISCOUNT_RATE_MEDIUM = 0.05
BULK_DISCOUNT_RATE_NONE = 0
TOTAL_DISCOUNT_THRESHOLD = 500
TOTAL_DISCOUNT_FLAT_AMOUNT = 25


def calculate_price(quantity, unit_price):
    if quantity > BULK_DISCOUNT_THRESHOLD_HIGH:
        discount = BULK_DISCOUNT_RATE_HIGH
    elif quantity > BULK_DISCOUNT_THRESHOLD_MEDIUM:
        discount = BULK_DISCOUNT_RATE_MEDIUM
    else:
        discount = BULK_DISCOUNT_RATE_NONE
    total = quantity * unit_price * (1 - discount)
    if total > TOTAL_DISCOUNT_THRESHOLD:
        total -= TOTAL_DISCOUNT_FLAT_AMOUNT
    return total


if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 545.0
    assert calculate_price(200, 5) == 875.0
    print('PASS')