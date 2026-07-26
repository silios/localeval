import sys, importlib.util, statistics

spec = importlib.util.spec_from_file_location("solution", "solution.py")
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

failed = 0

# Test: deterministic routing
ring = sol.ConsistentHashRing(nodes=["A", "B", "C"], vnodes=150)
n1 = ring.get_node("hello")
n2 = ring.get_node("hello")
assert n1 == n2, "same key must always route to same node"

# Test: every node gets some keys
keys = [f"key_{i}" for i in range(1000)]
counts = {}
for k in keys:
    n = ring.get_node(k)
    counts[n] = counts.get(n, 0) + 1
assert set(counts.keys()) == {"A", "B", "C"}, "all 3 nodes should get keys"

# Test: remove_node removes all vnodes
ring2 = sol.ConsistentHashRing(nodes=["X", "Y"], vnodes=10)
ring2.remove_node("X")
for k in keys:
    assert ring2.get_node(k) == "Y", "only node Y remains"

# Test: add_node distributes keys
ring3 = sol.ConsistentHashRing(nodes=["A", "B", "C"], vnodes=100)
before = {}
for k in keys:
    before[k] = ring3.get_node(k)

ring3.add_node("D")
moved = 0
after = {}
for k in keys:
    after[k] = ring3.get_node(k)
    if after[k] != before[k]:
        moved += 1

migration_pct = moved / len(keys) * 100
# With 4 nodes (adding 1 to 3), good hashing moves roughly 25% of keys
# Allow 15-35% range to be flexible
if migration_pct < 10:
    print(f"FAIL: too few keys moved ({migration_pct:.1f}%), ring may not be working")
    failed += 1
elif migration_pct > 50:
    print(f"FAIL: too many keys moved ({migration_pct:.1f}%), should be ~25%")
    failed += 1

# Test: balance score (stddev of key counts)
dist = {}
for k in keys:
    n = ring3.get_node(k)
    dist[n] = dist.get(n, 0) + 1
stddev = statistics.stdev(dist.values())
if stddev > 80:
    print(f"FAIL: poor balance (stddev={stddev:.1f}), should be under 80")
    failed += 1

# Test: empty ring raises on get_node
ring4 = sol.ConsistentHashRing()
try:
    ring4.get_node("test")
    print("FAIL: get_node on empty ring should raise ValueError")
    failed += 1
except ValueError:
    pass  # expected

if failed:
    print(f"\n{failed} test(s) failed")
    sys.exit(1)

print(f"All consistent hash tests passed (migration={migration_pct:.1f}%, stddev={stddev:.1f})")
