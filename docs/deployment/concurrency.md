# Concurrency Model

The Impulse Graph Engine is designed for extreme concurrency, aiming to support thousands of simultaneous query threads with sub-microsecond latency. The core philosophy is **Zero Shared Mutable State on the Hot Path**.

## Lock-Free Reads via Mmap

All query traversals operate over `ImpulseGraphSnapshot` (`GraphSnapshot` in Java 25, `impulse_snapshot_t` in C-ABI). A snapshot handle is a lightweight descriptor containing slices/pointers into memory-mapped (`mmap`) regions representing the Compressed Sparse Row (CSR) and Structure-of-Arrays (SoA) segments of the `.imps` file.

Because the underlying `.imps` file on disk is immutable, these memory regions are completely read-only. 

- **No Read/Write Locks**: There are no locks acquired during traversal. 
- **Page Cache Driven**: The operating system's page cache handles parallel I/O and memory management transparently.
- **Hardware Threading**: Scales perfectly linearly with the number of CPU cores.

## Atomic Snapshot Reference Swaps (`SnapshotSwapManager`)

In a dynamic service environment, new data arrives continuously. Rather than locking the graph to update the base structure, an out-of-band builder writes a new `.imps` file.

When the new file is ready, `SnapshotSwapManager` performs an **atomic pointer swap** (`AtomicReference` in Java, `std::atomic` in C++) to redirect new queries to the new memory map while reference-counting and draining in-flight queries on the previous snapshot:

```java
SnapshotSwapManager<GraphSnapshot> swapManager = new SnapshotSwapManager<>(initialSnapshot);

// Atomically swap active snapshot and asynchronously drain/close the old generation
swapManager.swap(newSnapshot);
```

Queries that started before the swap continue reading from the old mapped memory. Once their `holder.release()` count reaches zero, the old `Arena` is closed and unmapped.

## Zero-Allocation Hot Path

To prevent Java Garbage Collection (GC) pauses from ruining predictable latency, the engine enforces a strict zero-allocation rule during query execution.

- No objects are allocated per-step.
- Node arrays and bitsets are updated in place.

## Allocation Budget & `VmQueryContext` / Caller Buffer

Every concurrent query requires temporary scratch space (e.g., off-heap bitsets for intermediate unions or intersections). To satisfy the zero-allocation rule, this scratch space is pre-allocated in an off-heap `Arena` (`VmQueryContext` in Java 25, or the caller-provided buffer in C-ABI `impulse_stmt_execute`):

=== "Java 25"
    ```java
    // Pre-compiled MethodHandle pipeline
    MethodHandle compiled = ImpulseMethodHandleCompiler.compile(prog, instructionCount);

    // Worker or Virtual Thread reuses an off-heap Arena / VmQueryContext
    try (Arena workerArena = Arena.ofConfined()) {
        ImpulseBitSet result = (ImpulseBitSet) compiled.invokeExact(graph, (Object) seedNodeId, workerArena);
    }
    ```

=== "C-ABI (`impulse_stmt_t`)"
    ```c
    // Allocated once per worker thread based on deterministic prepare-time size
    size_t buf_len = impulse_stmt_buffer_size(stmt);
    void* thread_buf = malloc(buf_len);

    // Hot request loop: zero internal mallocs
    impulse_stmt_bind_node(stmt, "$seed", seed_id);
    impulse_stmt_execute(stmt, thread_buf, buf_len);
    ```
