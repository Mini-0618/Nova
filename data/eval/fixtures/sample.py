def old_func():
    return "old_func result"

def another_old_func():
    x = old_func()
    return x + " modified by old_func"
