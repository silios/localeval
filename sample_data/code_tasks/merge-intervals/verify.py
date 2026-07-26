import sys, importlib.util

spec = importlib.util.spec_from_file_location("solution", "solution.py")
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

tests = [
    ([[1, 3], [2, 6], [8, 10], [15, 18]], [[1, 6], [8, 10], [15, 18]]),
    ([[1, 4], [4, 5]], [[1, 5]]),
    ([[1, 4], [0, 4]], [[0, 4]]),
    ([[1, 4], [2, 3]], [[1, 4]]),
    ([[1, 3]], [[1, 3]]),
    ([], []),
    ([[2, 3], [4, 5], [6, 7], [8, 9], [1, 10]], [[1, 10]]),
    ([[1, 4], [5, 6]], [[1, 4], [5, 6]]),
    ([[4, 5], [1, 4], [3, 6]], [[1, 6]]),
]

failed = 0
for inp, expected in tests:
    result = sol.merge([list(x) for x in inp])  # deep copy
    if result != expected:
        print(f"FAIL: merge({inp}) = {result}, expected {expected}")
        failed += 1

if failed:
    print(f"\n{failed}/{len(tests)} tests failed")
    sys.exit(1)
print(f"All {len(tests)} tests passed")
