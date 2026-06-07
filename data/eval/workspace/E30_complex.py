def _calculate_items_total(items):
    total = 0
    for item in items:
        if 'price' in item and 'qty' in item and item['qty'] > 0:
            total += item['price'] * item['qty']
    return total


def _apply_discount(total, order):
    if 'discount' in order:
        total *= (1 - order['discount'])
    return total


def process_order(order):
    if not order:
        return {'status': 'error', 'msg': 'no order'}

    if 'items' not in order:
        return {'status': 'error', 'msg': 'missing items'}

    if not order['items']:
        return {'status': 'error', 'msg': 'no items'}

    total = _calculate_items_total(order['items'])

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
