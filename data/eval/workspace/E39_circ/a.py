def get_a_value():
    from b import get_b_value
    return 'a' + get_b_value()