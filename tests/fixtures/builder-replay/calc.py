def calculate(a, op, b):
    if op == "+":
        return a + b
    raise ValueError("unsupported operation")
