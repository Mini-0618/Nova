# Named constants replacing magic numbers
BULK_ORDER_THRESHOLD_HIGH = 100
BULK_ORDER_THRESHOLD_LOW = 50
DISCOUNT_HIGH = 0.1
DISCOUNT_LOW = 0.05
DISCOUNT_NONE = 0
FREE_SHIPPING_THRESHOLD = 500
SHIPPING_FEE_WAIVER = 25


def calculate_price(quantity, unit_price):
    if quantity > BULK_ORDER_THRESHOLD_HIGH:
        discount = DISCOUNT_HIGH
    elif quantity > BULK_ORDER_THRESHOLD_LOW:
        discount = DISCOUNT_LOW
    else:
        discount = DISCOUNT_NONE
    total = quantity * unit_price * (1 - discount)
    if total > FREE_SHIPPING_THRESHOLD:
        total -= SHIPPING_FEE_WAIVER
    return total


if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 545.0
    assert calculate_price(200, 5) == 875.0
    print('PASS')