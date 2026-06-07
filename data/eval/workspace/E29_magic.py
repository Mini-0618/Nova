# Named constants for quantity thresholds
HIGH_DISCOUNT_QUANTITY_THRESHOLD = 100
MEDIUM_DISCOUNT_QUANTITY_THRESHOLD = 50

# Named constants for discount rates
HIGH_DISCOUNT_RATE = 0.1
MEDIUM_DISCOUNT_RATE = 0.05

# Named constants for shipping-related thresholds and deductions
SHIPPING_FEE_THRESHOLD = 500
SHIPPING_FEE_DISCOUNT = 25


def calculate_price(quantity, unit_price):
    if quantity > HIGH_DISCOUNT_QUANTITY_THRESHOLD:
        discount = HIGH_DISCOUNT_RATE
    elif quantity > MEDIUM_DISCOUNT_QUANTITY_THRESHOLD:
        discount = MEDIUM_DISCOUNT_RATE
    else:
        discount = 0
    total = quantity * unit_price * (1 - discount)
    if total > SHIPPING_FEE_THRESHOLD:
        total -= SHIPPING_FEE_DISCOUNT
    return total

if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 570.0
    assert calculate_price(200, 5) == 900.0
    print('PASS')
