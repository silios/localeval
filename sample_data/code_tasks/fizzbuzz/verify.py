import sys, importlib.util

spec = importlib.util.spec_from_file_location('solution', 'solution.py')
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

failed = 0
# Format: (args_tuple, expected) for each test case
tests = [
    ((3,), ['1', '2', 'Fizz']),
    ((5,), ['1', '2', 'Fizz', '4', 'Buzz']),
    ((15,), ['1', '2', 'Fizz', '4', 'Buzz', 'Fizz', '7', '8', 'Fizz', 'Buzz', '11', 'Fizz', '13', '14', 'FizzBuzz']),
    ((1,), ['1']),
]

for args, expected in tests:
    if isinstance(args, tuple):
        result = sol.fizzbuzz(*args)
    else:
        result = sol.fizzbuzz(args)
    if result != expected:
        print(f'FAIL: got {result!r}, expected {expected!r}')
        failed += 1

if failed:
    print(f'\n{failed}/{len(tests)} tests failed')
    sys.exit(1)
print(f'All {len(tests)} tests passed')
