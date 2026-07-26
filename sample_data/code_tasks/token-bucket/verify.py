import sys, importlib.util, time

spec = importlib.util.spec_from_file_location("solution", "solution.py")
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

failed = 0

# Test: initial capacity allows consumption up to capacity
b = sol.TokenBucket(capacity=10, refill_rate=5.0)
assert b.consume(10) is True, "should allow consume up to capacity"
assert b.consume(1) is False, "should deny when empty"

# Test: refill over time
b2 = sol.TokenBucket(capacity=5, refill_rate=10.0)  # 10 tokens/sec
b2.consume(5)  # drain
time.sleep(0.5)  # 5 tokens refilled
assert b2.consume(4) is True, "should allow after refill"
assert b2.consume(2) is False, "only 1 token left"

# Test: bucket does not exceed capacity
b3 = sol.TokenBucket(capacity=3, refill_rate=100.0)
b3.consume(3)  # drain
time.sleep(0.5)  # 50 tokens would refill, but cap at 3
assert b3.consume(3) is True, "capped at capacity"
assert b3.consume(1) is False, "empty after cap drain"

# Test: denied request does not consume tokens
b4 = sol.TokenBucket(capacity=5, refill_rate=1.0)
assert b4.consume(10) is False, "denied"
assert b4.consume(5) is True, "still full after denial"

# Test: consume 0 tokens always succeeds
b5 = sol.TokenBucket(capacity=1, refill_rate=1.0)
b5.consume(1)  # drain
assert b5.consume(0) is True, "0 tokens always allowed"

print("All token bucket tests passed")
