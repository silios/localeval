import sys, importlib.util

spec = importlib.util.spec_from_file_location('solution', 'solution.py')
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

failed = 0
# Format: (args_tuple, expected) for each test case
tests = [
    (('leetcode',), 0),
    (('loveleetcode',), 2),
    (('aabb',), -1),
    (('',), -1),
    (('a',), 0),
]

for args, expected in tests:
    if isinstance(args, tuple):
        result = sol.first_unique_char(*args)
    else:
        result = sol.first_unique_char(args)
    if result != expected:
        print(f'FAIL: got {result!r}, expected {expected!r}')
        failed += 1

if failed:
    print(f'\n{failed}/{len(tests)} tests failed')
    sys.exit(1)
print(f'All {len(tests)} tests passed')
