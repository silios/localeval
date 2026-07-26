## Consistent Hash Ring

Implement a minimal consistent hashing ring. Given a set of nodes, the
ring maps string keys to nodes such that adding or removing a node only
redistributes a fraction of the keys (roughly 1/N).

**Class:**
```python
class ConsistentHashRing:
    def __init__(self, nodes: list[str] = None, vnodes: int = 150): ...
    def add_node(self, node_id: str) -> None: ...
    def remove_node(self, node_id: str) -> None: ...
    def get_node(self, key: str) -> str: ...
```

- Use `hashlib.md5` for deterministic hashing of node vnode keys and
  data keys.
- Each physical node gets `vnodes` virtual nodes on the ring. Virtual
  node positions are computed as `md5(f"{node_id}:{i}")` for i in
  range(vnodes), interpreted as an integer.
- `get_node(key)`: hash the key with md5, find the first node position
  >= the key hash on the ring (wrapping around to the first node if
  none found). Return the physical node name.
- The ring positions must be kept in sorted order for efficient lookup.
  Use `bisect` from the standard library.
- `add_node` and `remove_node` must correctly update the ring.

**Example:**
```python
ring = ConsistentHashRing(nodes=["A", "B", "C"])
ring.get_node("mykey")    # returns one of A, B, or C
ring.add_node("D")
ring.get_node("mykey")    # may return D now if key remapped
ring.remove_node("B")
ring.get_node("mykey")    # B is gone, key mapped to another node
```
