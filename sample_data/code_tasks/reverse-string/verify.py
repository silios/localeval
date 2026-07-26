import importlib.util
import sys


def load_solution():
    spec = importlib.util.spec_from_file_location("solution", "solution.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = load_solution()
    cases = [("hello", "olleh"), ("", ""), ("a", "a"), ("ab cd", "dc ba")]
    for input_str, expected in cases:
        actual = module.reverse_string(input_str)
        if actual != expected:
            print(f"FAIL: reverse_string({input_str!r}) = {actual!r}, expected {expected!r}")
            sys.exit(1)
    print("all cases passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
