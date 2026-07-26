## LRU Cache

Implement a Least Recently Used (LRU) cache with O(1) `get` and `put`
operations. When the cache exceeds its capacity, evict the least recently
used item.

**Class:**
```python
class LRUCache:
    def __init__(self, capacity: int): ...
    def get(self, key: int) -> int: ...
    def put(self, key: int, value: int) -> None: ...
```

- `get(key)`: return the value if the key exists, otherwise -1.
- `put(key, value)`: insert or update the key. If the cache exceeds
  capacity after insertion, evict the least recently used key.
- Both operations must run in O(1) average time complexity.
- Keys and values are integers.

**Example:**
```python
cache = LRUCache(2)
cache.put(1, 1)
cache.put(2, 2)
cache.get(1)       # returns 1  (2 is now LRU)
cache.put(3, 3)    # evicts key 2
cache.get(2)       # returns -1 (evicted)
cache.put(4, 4)    # evicts key 1
cache.get(1)       # returns -1
cache.get(3)       # returns 3
cache.get(4)       # returns 4
```
