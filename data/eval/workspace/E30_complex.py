def _validate_order(order):
    """Validates the order and returns an error response if invalid, or None if valid."""
    if not order:
        return {'status': 'error', 'msg': 'no order'}
    if 'items' not in order:
        return {'status': 'error', 'msg': 'missing items'}
    if not order['items']:
        return {'status': 'error', 'msg': 'no items'}
    return None


def _calculate_total(items):
    """Calculates the subtotal from valid line items."""
    total = 0
    for item in items:
        if 'price' in item and 'qty' in item and item['qty'] > 0:
            total += item['price'] * item['qty']
    return total


def _apply_discount(total, order):
    """Applies discount to the total if a discount is present in the order."""
    if 'discount' in order:
        total *= (1 - order['discount'])
    return total


def process_order(order):
    error = _validate_order(order)
    if error:
        return error

    total = _calculate_total(order['items'])
    if total <= 0:
        return {'status': 'error', 'msg': 'empty cart'}

    total = _apply_discount(total, order)
    return {'status': 'ok', 'total': total}

if __name__ == '__main__':
    assert process_order(None)['status'] == 'error'
    assert process_order({})['status'] == 'error'
    assert process_order({'items': []})['status'] == 'error'
    assert process_order({'items': [{'price': 10, 'qty': 2}]})['total'] == 20
    assert process_order({'items': [{'price': 10, 'qty': 2}], 'discount': 0.1})['total'] == 18.0
    print('PASS')