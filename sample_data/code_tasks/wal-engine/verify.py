import sys, importlib.util, os, tempfile, binascii

spec = importlib.util.spec_from_file_location("solution", "solution.py")
sol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sol)

failed = 0
tmpdir = tempfile.mkdtemp()
wal_path = os.path.join(tmpdir, "wal.log")

try:
    # --- Test 1: basic put/get ---
    engine = sol.StorageEngine(wal_path)
    engine.put("name", "Alice")
    engine.put("age", "30")
    assert engine.get("name") == "Alice", "get('name') should return Alice"
    assert engine.get("age") == "30", "get('age') should return 30"
    assert engine.get("missing") is None, "get('missing') should return None"

    # --- Test 2: delete ---
    engine.delete("age")
    assert engine.get("age") is None, "age should be deleted"

    # --- Test 3: crash recovery ---
    original_state = {"name": "Alice"}
    engine2 = sol.StorageEngine(wal_path)
    recovered = engine2.recover()
    assert recovered == original_state, f"recovery mismatch: {recovered} != {original_state}"

    # --- Test 4: corruption detection ---
    # Write a new entry, then corrupt it in the file
    engine2.put("email", "alice@example.com")
    with open(wal_path, "r") as f:
        lines = f.readlines()

    # Corrupt the last line (flip a byte in the CRC32 value)
    last = lines[-1]
    corrupted = last.replace('"crc32": ', '"crc32": 99999999')
    lines[-1] = corrupted

    # Also corrupt a middle line
    if len(lines) >= 2:
        mid = lines[len(lines) // 2]
        corrupted_mid = mid.replace('"key": "', '"key": "CORRUPTED_')
        lines[len(lines) // 2] = corrupted_mid

    with open(wal_path, "w") as f:
        f.writelines(lines)

    reader = sol.WALReader(wal_path)
    entries = reader.read_all()

    corrupted_count = sum(1 for e in entries if not e.get("crc_valid", True))
    if corrupted_count != 2:
        print(f"FAIL: expected 2 corrupted entries, got {corrupted_count}")
        failed += 1

    valid_entries = [e for e in entries if e.get("crc_valid", True)]
    if len(valid_entries) != len(entries) - 2:
        print(f"FAIL: expected {len(entries) - 2} valid entries, got {len(valid_entries)}")
        failed += 1

    # --- Test 5: recovery after corruption (only valid entries replayed) ---
    engine3 = sol.StorageEngine(wal_path)
    recovered2 = engine3.recover()
    # The corrupted email entry should NOT be in recovered state
    assert recovered2.get("name") == "Alice", "name should survive corruption"
    assert recovered2.get("email") is None, "corrupted email entry must not be replayed"

    if failed:
        print(f"\n{failed} test(s) failed")
        sys.exit(1)
    print("All WAL engine tests passed")
finally:
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
