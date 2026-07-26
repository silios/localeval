## Token Bucket Rate Limiter

Implement a token bucket rate limiter. A token bucket has a fixed
capacity and refills at a constant rate (tokens per second). Each
request consumes one or more tokens; if enough tokens are available
the request is allowed, otherwise denied.

**Class:**
```python
class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float): ...
    def consume(self, tokens: int = 1) -> bool: ...
```

- `capacity`: maximum number of tokens the bucket can hold.
- `refill_rate`: tokens added per second (continuous refill).
- `consume(tokens)`: return `True` if `tokens` were consumed (allowed),
  `False` if insufficient tokens (denied). Tokens are only consumed
  on success - a denied request does not drain the bucket.
- Refill is calculated based on elapsed time since last consumption.
  Use `time.monotonic()` for wall-clock time.
- The bucket starts full (tokens = capacity).

**Example:**
```python
bucket = TokenBucket(capacity=10, refill_rate=5.0)  # 10 tokens max, 5/sec
bucket.consume(3)   # True, 7 tokens left
bucket.consume(8)   # False, only 7 available
time.sleep(1.0)     # wait 1 second, 5 tokens refilled
bucket.consume(8)   # True, now 12 available capped at 10 → 2 left
```
