import sys, importlib.util, json

# Load the solution
spec = importlib.util.spec_from_file_location("solution", "solution.py")
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

tests = [
    ({"nums": [2, 7, 11, 15], "target": 9}, [0, 1]),
    ({"nums": [3, 2, 4], "target": 6}, [1, 2]),
    ({"nums": [3, 3], "target": 6}, [0, 1]),
    ({"nums": [1, 5, 8, 3, 9, 2], "target": 11}, [1, 5]),
    ({"nums": [0, 4, 3, 0], "target": 0}, [0, 3]),
]

failed = 0
for inp, expected in tests:
    result = sol.two_sum(**inp)
    result_sorted = sorted(result)
    expected_sorted = sorted(expected)
    if result_sorted != expected_sorted:
        print(f"FAIL: two_sum({inp['nums']}, {inp['target']}) = {result}, expected {expected}")
        failed += 1

if failed:
    print(f"\n{failed}/{len(tests)} tests failed")
    sys.exit(1)
print(f"All {len(tests)} tests passed")
