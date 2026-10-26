# Capacity Growth & Scratch Arena Sizing

Because Impulse Graph Engine operates over **immutable `.imps` binary snapshots**, graph capacity growth and per-query scratch memory sizing are handled deterministically without in-place array resizing, stop-the-world reallocations, or JVM heap GC pressure.

---

## 1. Per-Domain Node Cardinality & `PrimitiveWidth` Boundaries

Every node domain in an `.imps` snapshot defines an independent 0-indexed dense integer ID space ($0 \dots N_d - 1$) with a fixed `nodeCount` ($N_d$) and physical integer width (`PrimitiveWidth`):

| `PrimitiveWidth` | Physical Type | Bytes per ID | Max Domain Cardinality ($N_d$) |
| :--- | :--- | :---: | :--- |
| **`PrimitiveWidth.UINT16`** | `uint16_t` | 2 bytes | Up to `65,536` nodes |
| **`PrimitiveWidth.UINT32`** | `uint32_t` | 4 bytes | Up to `4,294,967,296` nodes |
| **`PrimitiveWidth.UINT64`** | `uint64_t` | 8 bytes | $> 4.29\text{ billion}$ nodes |

### Growing Domain Cardinality via Out-of-Band Snapshot Rotation
An active `.imps` snapshot is never mutated or resized in place. When upstream data grows—or when a domain's cardinality crosses a `PrimitiveWidth` boundary (for example, growing past `65,536` nodes from `UINT16` to `UINT32`):

1. **Out-of-Band Compilation**: `SnapshotBuilder` (Java) or `impulse snapshot build` (CLI) streams a new `.imps` snapshot generation to disk with the updated domain `nodeCount` and `PrimitiveWidth`:
   ```java
   SnapshotBuilder.create()
       .withStagingDirectory(Path.of("/tmp/staging"))
       .addDomain("User", DomainDefinition.builder(newCardinality)
           .idWidth(newCardinality <= 65_536 ? PrimitiveWidth.UINT16 : PrimitiveWidth.UINT32)
           .build())
       // ...
       .writeTo(Path.of("graph_next.imps"));
   ```
2. **Atomic A/B Swap (`SnapshotSwapManager`)**: The service memory-maps the newly built `.imps` file into a fresh `Arena.ofShared()` and atomically swaps the active snapshot reference via `SnapshotSwapManager.swap(newSnapshot)`:
   ```java
   // Reader threads acquire an epoch-counted reference
   var holder = swapManager.acquireCurrent();
   if (holder != null) {
       try {
           GraphSnapshot snap = holder.getResource();
           // Execute lock-free read-only query...
       } finally {
           holder.release();
       }
   }

   // Background updater atomically swaps in the new snapshot generation
   swapManager.swap(newGraphSnapshot);
   ```
3. **Zero-Downtime Draining**: In-flight queries on the previous snapshot complete normally. Once the previous holder's `getActiveReaders()` count reaches `0`, `SnapshotSwapManager` automatically closes the old `GraphSnapshot` and unmaps its off-heap `Arena`.

---

## 2. Bounded Off-Heap Query Scratch Memory (`VmQueryContext`)

Because every `.imps` snapshot encodes the exact node cardinality $N_d$ per domain in its catalog header, intermediate traversal bitsets ($\lceil N_d / 64 \rceil$ 64-bit words) and register state vectors are sized deterministically from the snapshot metadata.

### 2.1 Java 25 `VmQueryContext` & `OffHeapBitSet` Pooling
In `impulse-vm`, `VmQueryContext` manages off-heap scratch memory and reusable bitset handles bound to a `java.lang.foreign.Arena`:

* **Bounded Scratch Capacity**: `VmQueryContext` tracks off-heap scratch allocations (`DEFAULT_SCRATCH_BYTES = 64 KB` baseline, `512 MB` default maximum cap) via `setMaxScratchCapacityBytes(long bytes)`, `getMaxScratchCapacityBytes()`, and 64-byte-aligned `allocateScratch(long bytes)` calls (validated at runtime by `OP_ALLOC_SCRATCH` and `OP_ASSERT_SCRATCH_BYTES`).
* **Reusable `OffHeapBitSet` Handle Pool**: Calling `ctx.acquireBitset()` allocates an `OffHeapBitSet` inside the context's `Arena` sized to the snapshot's maximum domain node count (or recycles a cleared bitset from `freeBitsetHandles` without allocating new off-heap memory). Calling `ctx.releaseBitset(handle)` clears the bitset and returns its handle to the free pool for subsequent hops.
* **L1-Aligned VM Register Frame**: `ctx.allocateStateSegment()` allocates the fixed 640-byte `VmStateLayout.VM_STATE_LAYOUT` register file (`R0`..`R63`) directly inside the `Arena`.

```java
try (Arena queryArena = Arena.ofConfined();
     VmQueryContext ctx = new VmQueryContext(snapshot, queryArena)) {

    // Enforce a strict per-query off-heap scratch ceiling (e.g., 64 MB)
    ctx.setMaxScratchCapacityBytes(64L * 1024 * 1024);

    // Acquire and recycle off-heap frontier bitsets across traversal steps
    int frontierHandle = ctx.acquireBitset();
    ImpulseBitSet frontier = ctx.getBitset(frontierHandle);
    // ...
    ctx.releaseBitset(frontierHandle);
}
```

### 2.2 Native C-ABI Deterministic Scratch Buffer (`impulse_stmt_buffer_size`)
In the C-ABI runtime (`impulse_graph.h`), prepared statements compute their exact scratch and output buffer requirement at `prepare` time based on the active snapshot's domain cardinalities:

```c
// Query exact buffer requirement for the current snapshot generation
size_t required_bytes = impulse_stmt_buffer_size(stmt);
void* scratch_buf = aligned_alloc(128, required_bytes);

// Execute with zero internal heap allocations
impulse_status_t status = impulse_stmt_execute(stmt, scratch_buf, required_bytes);
```

When a larger `.imps` snapshot is swapped in, worker threads simply re-query `impulse_stmt_buffer_size(stmt)` (or create a fresh `VmQueryContext` bound to the new snapshot) and grow their thread-local scratch buffer if `required_bytes` exceeds the previously allocated size.
