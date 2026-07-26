import sys, importlib.util

spec = importlib.util.spec_from_file_location('solution', 'solution.py')
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

failed = 0
# Format: (args_tuple, expected) for each test case
tests = [
    (([1, 2, 3, 4, 5, 6, 7], 3), [5, 6, 7, 1, 2, 3, 4]),
    (([-1, -100, 3, 99], 2), [3, 99, -1, -100]),
    (([1, 2], 3), [2, 1]),
    (([1], 0), [1]),
]

for args, expected in tests:
    if isinstance(args, tuple):
        result = sol.rotate(*args)
    else:
        result = sol.rotate(args)
    if result != expected:
        print(f'FAIL: got {result!r}, expected {expected!r}')
        failed += 1

if failed:
    print(f'\n{failed}/{len(tests)} tests failed')
    sys.exit(1)
print(f'All {len(tests)} tests passed')
