# Named constants for magic numbers
QUANTITY_THRESHOLD_HIGH = 100
QUANTITY_THRESHOLD_MEDIUM = 50
DISCOUNT_HIGH = 0.1
DISCOUNT_MEDIUM = 0.05
DISCOUNT_NONE = 0
TOTAL_THRESHOLD_ADDITIONAL_DISCOUNT = 500
ADDITIONAL_DISCOUNT_AMOUNT = 25


def calculate_price(quantity, unit_price):
    if quantity > QUANTITY_THRESHOLD_HIGH:
        discount = DISCOUNT_HIGH
    elif quantity > QUANTITY_THRESHOLD_MEDIUM:
        discount = DISCOUNT_MEDIUM
    else:
        discount = DISCOUNT_NONE
    total = quantity * unit_price * (1 - discount)
    if total > TOTAL_THRESHOLD_ADDITIONAL_DISCOUNT:
        total -= ADDITIONAL_DISCOUNT_AMOUNT
    return total


if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 545.0
    assert calculate_price(200, 5) == 875.0
    print('PASS')