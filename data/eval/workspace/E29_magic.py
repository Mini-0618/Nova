LARGE_QTY_THRESHOLD = 100
LARGE_QTY_DISCOUNT = 0.1
MEDIUM_QTY_THRESHOLD = 50
MEDIUM_QTY_DISCOUNT = 0.05
TOTAL_DISCOUNT_THRESHOLD = 500
FLAT_DISCOUNT_AMOUNT = 25

def calculate_price(quantity, unit_price):
    if quantity > LARGE_QTY_THRESHOLD:
        discount = LARGE_QTY_DISCOUNT
    elif quantity > MEDIUM_QTY_THRESHOLD:
        discount = MEDIUM_QTY_DISCOUNT
    else:
        discount = 0
    total = quantity * unit_price * (1 - discount)
    if total > TOTAL_DISCOUNT_THRESHOLD:
        total -= FLAT_DISCOUNT_AMOUNT
    return total

if __name__ == '__main__':
    assert calculate_price(10, 10) == 100
    assert calculate_price(60, 10) == 570.0
    assert calculate_price(200, 5) == 900.0
    print('PASS')