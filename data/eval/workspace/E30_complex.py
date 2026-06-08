def process_order(order):
    if order:
        if 'items' in order:
            if len(order['items']) > 0:
                total = 0
                for item in order['items']:
                    if 'price' in item and 'qty' in item:
                        if item['qty'] > 0:
                            total += item['price'] * item['qty']
                if total > 0:
                    if 'discount' in order:
                        total *= (1 - order['discount'])
                    return {'status': 'ok', 'total': total}
                else:
                    return {'status': 'error', 'msg': 'empty cart'}
            else:
                return {'status': 'error', 'msg': 'no items'}
        else:
            return {'status': 'error', 'msg': 'missing items'}
    else:
        return {'status': 'error', 'msg': 'no order'}

if __name__ == '__main__':
    assert process_order(None)['status'] == 'error'
    assert process_order({})['status'] == 'error'
    assert process_order({'items': []})['status'] == 'error'
    assert process_order({'items': [{'price': 10, 'qty': 2}]})['total'] == 20
    assert process_order({'items': [{'price': 10, 'qty': 2}], 'discount': 0.1})['total'] == 18.0
    print('PASS')