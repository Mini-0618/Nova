def new_func():
    return "new_func result"

def another_new_func():
    x = new_func()
    return x + " modified by new_func"
