import sys, importlib.util

spec = importlib.util.spec_from_file_location("solution", "solution.py")
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

# Test basic put/get
cache = sol.LRUCache(2)
cache.put(1, 1)
cache.put(2, 2)
assert cache.get(1) == 1, "get(1) should return 1"
cache.put(3, 3)  # evicts 2
assert cache.get(2) == -1, "get(2) should return -1 after eviction"
cache.put(4, 4)  # evicts 1
assert cache.get(1) == -1, "get(1) should return -1 after eviction"
assert cache.get(3) == 3, "get(3) should return 3"
assert cache.get(4) == 4, "get(4) should return 4"

# Test update existing key
cache2 = sol.LRUCache(2)
cache2.put(1, 10)
cache2.put(1, 20)  # update
assert cache2.get(1) == 20, "update should change value"

# Test capacity 1
cache3 = sol.LRUCache(1)
cache3.put(1, 1)
cache3.put(2, 2)
assert cache3.get(1) == -1, "capacity 1: first key evicted"
assert cache3.get(2) == 2

# Test get refreshes LRU order
cache4 = sol.LRUCache(2)
cache4.put(1, 1)
cache4.put(2, 2)
cache4.get(1)       # makes 2 LRU
cache4.put(3, 3)    # should evict 2, not 1
assert cache4.get(1) == 1, "get should refresh LRU order"
assert cache4.get(2) == -1
assert cache4.get(3) == 3

print("All LRU cache tests passed")
