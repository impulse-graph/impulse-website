# Zero-Allocation Execution & Caller Buffers

A defining guarantee of **Impulse Graph Engine** is **zero dynamic memory allocations (`malloc` / `new`) in the hot query path**.

In a traditional database, a multi-hop query allocates and resizes hash tables, lists, and intermediate row objects as it runs—Because the engine cannot predict how many duplicate paths will fan out, memory grows unpredictably and triggers garbage collection (GC) or allocator contention.

Because Impulse Graph operates over **immutable `.imps` snapshots** with **set-based monoidic reduction**, the exact memory required for any query is **100% deterministic before the query ever executes**.

---

## 1. Why Query Memory Is Deterministic at `prepare` Time

When a query is compiled against an `.imps` snapshot:

1. **Domain Cardinalities ($N_d$) Are Fixed**: Every node domain's exact size $N_d$ is stored in the Section 2 Domain Catalog.
2. **Frontiers Are Bounded by $N_d$**: Because intermediate results are [collapsed into sets at every hop](../getting-started/index.md#how-queries-work-the-two-core-mechanics), a reachability frontier over domain $D$ never exceeds $\lceil N_d / 64 \rceil$ 64-bit words, and a scalar state vector never exceeds $N_d \times \text{sizeof}(\text{state})$.
3. **Static Register & Scratch Accounting**: During compilation, the compiler emits `OP_ALLOC_SCRATCH` and `OP_ASSERT_SCRATCH_BYTES` instructions, computing the exact byte count needed for both intermediate VM scratch space and final columnar output projections.

---

## 2. The SQLite-Style Prepared Statement Lifecycle

In the C/C++20 C-ABI (`impulse_stmt_*`) and all language bindings built on it, the caller queries the required buffer size once at `prepare` time, allocates or reuses a memory block (on the stack, in a thread-local buffer, or in a custom arena), and passes it into `execute`:

```text
 1. Prepare (< 3 µs)          impulse_stmt_prepare(snap, query_str, &stmt)
                              └─ Compiles AST -> impOps bytecode & computes workspace bounds

 2. Query Required Size       size_t buf_len = impulse_stmt_buffer_size(stmt)
                              └─ Exact byte count for Scratch Area + Columnar Return Area

 3. Supply Reusable Buffer    void* buf = thread_local_arena(buf_len); // Allocated once per thread

 4. Bind Parameters           impulse_stmt_bind_str(stmt, "$user", "usr_101");
                              impulse_stmt_bind_float(stmt, "$min_amt", 1000.0);

 5. Execute (0 Allocations)   impulse_stmt_execute(stmt, buf, buf_len);
                              └─ Runs entirely inside the 640B VM register frame + caller buffer

 6. Read Columnar Results     const void* col0 = impulse_stmt_column_data(stmt, 0);
                              └─ Zero-copy Arrow-compatible typed arrays & validity bitmaps
```

In the **Pure Java 25 Engine**, `ImpulseVmInterpreter.execute(programSeg, instructionCount, snapshot, input, arena)` and `ImpulseStatement.execute()` follow the exact same off-heap discipline over reusable `java.lang.foreign.MemorySegment` slices (`VmStateLayout` + `OffHeapBitSet` handle pools), ping-ponging intermediate frontiers in place via `OP_SWAP_REG` with zero heap object creation.

---

## 3. Inside the Caller-Provided Memory Buffer

When `impulse_stmt_execute(stmt, buf, buf_len)` runs, the engine partitions the caller's contiguous buffer into 128-byte-aligned regions:

```text
Caller-Provided Memory Buffer (buf, buf_len):
┌─────────────────────────┬─────────────────────────┬─────────────────────────┬─────────────────────────┐
│ Section A: Scratch Area │ Section B: Col 0 Data   │ Section C: Col 1 Data   │ Section D: Null Bitmaps │
│ Internal VM Bitsets &   │ Contiguous Typed Array  │ Contiguous Typed Array  │ Arrow Validity Bitmaps  │
│ State Vector Registers  │ (e.g. uint32_t IDs or   │ (e.g. float64_t scores  │ (1 bit per row:         │
│ (128-Byte Aligned)      │  const char* pointers)  │  or projected totals)   │  1 = valid, 0 = NULL)   │
└─────────────────────────┴─────────────────────────┴─────────────────────────┴─────────────────────────┘
```

* **Zero String Copies on Projection**: Variable-length string attributes and string domain keys (`VAR_STRING` `0x0B`) are stored in Section 4 as per-column 128-byte-aligned `uint32_t offsets[K+1]` arrays paired with a contiguous UTF-8 byte payload blob (while the Section 2 Shared String Table stores schema/catalog identifier names). When projecting strings, the engine slices `(offsets[id], offsets[id + 1])` **directly inside the immutable `mmap` payload blob**—never copying string characters into heap objects.
* **Apache Arrow-Compatible Null Bitmaps**: Non-nullable columns (`NullCount == 0`) omit the bitmap entirely (`null_bitmap == NULL`). Nullable columns emit a 128-byte-aligned validity bitmap (`bit i == 1` valid, `bit i == 0` null) that maps directly to Apache Arrow / PyArrow arrays.
* **Boundary Key Resolution**: External business keys (`String`, `UUID`, `int64`) are resolved to dense `0..N-1` IDs once at the start of execution (`OP_MAP_KEYS_TO_DENSE` / `fromKey`) and projected back to external keys only for the surviving output rows (`OP_MAP_DENSE_TO_KEYS` / `toKeyList`).

---

## Next Steps

* **[Compiler Pipeline & ImpulseVM](compiler-architecture.md)**: See how queries are optimized using snapshot metadata and executed on the 64-register VM.
* **[C-ABI Kernel & VM Reference](../reference/c-abi.md)**: Full struct and function signatures for `impulse_stmt_*` and `impulse_snapshot_*`.
