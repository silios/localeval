import sys, importlib.util

spec = importlib.util.spec_from_file_location('solution', 'solution.py')
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

failed = 0
# Format: (args_tuple, expected) for each test case
tests = [
    ((123,), 321),
    ((-123,), -321),
    ((120,), 21),
    ((0,), 0),
    ((1534236469,), 0),
]

for args, expected in tests:
    if isinstance(args, tuple):
        result = sol.reverse_integer(*args)
    else:
        result = sol.reverse_integer(args)
    if result != expected:
        print(f'FAIL: got {result!r}, expected {expected!r}')
        failed += 1

if failed:
    print(f'\n{failed}/{len(tests)} tests failed')
    sys.exit(1)
print(f'All {len(tests)} tests passed')
