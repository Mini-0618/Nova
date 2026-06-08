def _calculate_item_total(item):
    """Calculate the line total for a single item."""
    if 'price' not in item or 'qty' not in item:
        return 0
    if item['qty'] <= 0:
        return 0
    return item['price'] * item['qty']


def _apply_discount(total, order):
    """Apply discount to the total if present."""
    if 'discount' in order:
        return total * (1 - order['discount'])
    return total


def process_order(order):
    if not order:
        return {'status': 'error', 'msg': 'no order'}
    if 'items' not in order:
        return {'status': 'error', 'msg': 'missing items'}
    if len(order['items']) == 0:
        return {'status': 'error', 'msg': 'no items'}

    total = sum(_calculate_item_total(item) for item in order['items'])
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