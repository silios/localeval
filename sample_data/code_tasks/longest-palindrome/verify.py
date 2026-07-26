import sys, importlib.util

spec = importlib.util.spec_from_file_location("solution", "solution.py")
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

def is_pal(s):
    return s == s[::-1]

tests = [
    ("babad", {"bab", "aba"}),
    ("cbbd", {"bb"}),
    ("a", {"a"}),
    ("ac", {"a", "c"}),
    ("racecar", {"racecar"}),
    ("aaaa", {"aaaa"}),
    ("abcba", {"abcba"}),
    ("abacdfgdcaba", {"aba"}),
]

failed = 0
for s, expected_set in tests:
    result = sol.longest_palindrome(s)
    if not is_pal(result):
        print(f"FAIL: longest_palindrome({s!r}) = {result!r} is not a palindrome")
        failed += 1
    elif result not in expected_set:
        print(f"FAIL: longest_palindrome({s!r}) = {result!r}, expected one of {expected_set}")
        failed += 1

if failed:
    print(f"\n{failed}/{len(tests)} tests failed")
    sys.exit(1)
print(f"All {len(tests)} tests passed")
