import sys, importlib.util

spec = importlib.util.spec_from_file_location('solution', 'solution.py')
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

failed = 0
# Format: (args_tuple, expected) for each test case
tests = [
    (('racecar',), True),
    (('A man a plan a canal Panama',), True),
    (('hello',), False),
    (('',), True),
    (('a.',), True),
    (('race a car',), False),
]

for args, expected in tests:
    if isinstance(args, tuple):
        result = sol.is_palindrome(*args)
    else:
        result = sol.is_palindrome(args)
    if result != expected:
        print(f'FAIL: got {result!r}, expected {expected!r}')
        failed += 1

if failed:
    print(f'\n{failed}/{len(tests)} tests failed')
    sys.exit(1)
print(f'All {len(tests)} tests passed')
