## Write-Ahead Log Engine

Implement a minimal Write-Ahead Log (WAL) storage engine. This is the
same fundamental mechanism used by PostgreSQL, SQLite, and RocksDB to
guarantee durability: all mutations are written to an append-only log
before being applied to in-memory state, enabling crash recovery.

**Classes:**
```python
class WALWriter:
    def __init__(self, path: str): ...
    def append(self, seq: int, op: str, key: str, value: str = "") -> int: ...
    def close(self) -> None: ...

class WALReader:
    def __init__(self, path: str): ...
    def read_all(self) -> list[dict]: ...

class StorageEngine:
    def __init__(self, wal_path: str): ...
    def put(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def get(self, key: str) -> str | None: ...
    def recover(self) -> dict[str, str]: ...
```

**WALWriter details:**
- `append(seq, op, key, value)`: writes one JSON line to the file with
  fields: `seq`, `op` (PUT or DELETE), `key`, `value`, and a `crc32`
  computed via `binascii.crc32()` over the JSON of `seq:op:key:value`.
  Returns the CRC32 value.
- `close()`: flushes and closes the file handle.

**WALReader details:**
- `read_all()`: reads every line from the log file. For each line, parse
  the JSON, recompute the CRC32 from the `seq:op:key:value`, and
  compare to the stored `crc32`. Set `crc_valid: True/False` on each
  entry. Return list of all entries (including corrupted ones with
  `crc_valid: False`).

**StorageEngine details:**
- Maintains an in-memory dict `_store`.
- `put(key, value)`: write a PUT entry to WAL, then update `_store`.
- `delete(key)`: write a DELETE entry to WAL, then remove from `_store`.
- `get(key)`: read from `_store` only.
- `recover()`: create a WALReader, read all entries, and replay only
  valid (crc_valid=True) PUT/DELETE operations in sequence order to
  rebuild `_store`. Returns the rebuilt dict.

**Key constraint:** The CRC32 must be computed over the string
`f"{seq}:{op}:{key}:{value}"` encoded as UTF-8, using `binascii.crc32()`.
