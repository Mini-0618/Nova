# Named constants for magic numbers
QUANTITY_THRESHOLD_HIGH = 100
QUANTITY_THRESHOLD_MEDIUM = 50
DISCOUNT_RATE_HIGH = 0.1  # 10% discount for high quantity
DISCOUNT_RATE_MEDIUM = 0.05  # 5% discount for medium quantity
TOTAL_THRESHOLD_FOR_ADDITIONAL_DISCOUNT = 500
ADDITIONAL_DISCOUNT_AMOUNT = 25


def calculate_price(quantity, unit_price):
    if quantity > QUANTITY_THRESHOLD_HIGH:
        discount = DISCOUNT_RATE_HIGH
    elif quantity > QUANTITY_THRESHOLD_MEDIUM:
        discount = DISCOUNT_RATE_MEDIUM
    else:
        discount = 0
    total = quantity * unit_price * (1 - discount)
    if total > TOTAL_THRESHOLD_FOR_ADDITIONAL_DISCOUNT:
        total -= ADDITIONAL_DISCOUNT_AMOUNT
    return total


if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 570.0
    assert calculate_price(200, 5) == 900.0
    print('PASS')