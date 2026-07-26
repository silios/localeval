import sys, importlib.util

spec = importlib.util.spec_from_file_location("solution", "solution.py")
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

tests = [
    ("()", True),
    ("()[]{}", True),
    ("(]", False),
    ("([)]", False),
    ("{[]}", True),
    ("", True),
    ("(((((())))))", True),
    ("(((())))", True),
    ("(((", False),
    ("]", False),
    ("[", False),
    ("[(])", False),
]

failed = 0
for s, expected in tests:
    result = sol.is_valid(s)
    if result != expected:
        print(f"FAIL: is_valid({s!r}) = {result}, expected {expected}")
        failed += 1

if failed:
    print(f"\n{failed}/{len(tests)} tests failed")
    sys.exit(1)
print(f"All {len(tests)} tests passed")
