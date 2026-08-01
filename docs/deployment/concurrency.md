# Concurrency Model

The Impulse Graph Engine is designed for extreme concurrency, aiming to support thousands of simultaneous query threads with sub-microsecond latency. The core philosophy is **Zero Shared Mutable State on the Hot Path**.

## Lock-Free Reads via Mmap

All query traversals operate over `GraphView` objects. A `GraphView` is fundamentally a lightweight struct containing pointers to memory-mapped (`mmap`) regions representing the Compressed Sparse Row (CSR) arrays of the graph.

Because the underlying `.imps` file on disk is immutable, these memory regions are completely read-only. 

- **No Read/Write Locks**: There are no locks acquired during traversal. 
- **Page Cache Driven**: The operating system's page cache handles parallel I/O and memory management transparently.
- **Hardware Threading**: Scales perfectly linearly with the number of CPU cores.

## Atomic Snapshot Reference Swaps

In a dynamic service environment, new data arrives continuously. Rather than locking the graph to update the base structure, the engine employs a background compaction thread to build a new `.imps` file.

When the new file is ready, the engine uses an **atomic pointer swap** (`VarHandle` in Java, `std::atomic` in C++) to redirect the active `GraphView` to the new memory map. 

```java
// Atomic, non-blocking pointer swap
VarHandle.fullFence();
activeGraphViewReference.setRelease(newSnapshotView);
```

Queries that started before the swap continue reading from the old mapped memory. Once their execution context ends, the old memory mapping is unmapped.

## Zero-Allocation Hot Path

To prevent Java Garbage Collection (GC) pauses from ruining predictable latency, the engine enforces a strict zero-allocation rule during query execution.

- No objects are allocated per-step.
- Node arrays and bitsets are updated in place.

## Allocation Budget & `QueryContext`

Every concurrent query requires temporary scratch space (e.g., bitsets for intermediate unions or intersections). To satisfy the zero-allocation rule, this scratch space must be pre-allocated.

This is handled by the `QueryContext`. A worker thread (or virtual thread) allocates a `QueryContext` **once**, sized exactly to the maximum live intermediates computed statically from the query AST.

=== "Java"
    ```java
    // Pre-allocated at startup or worker initialization
    QueryContext ctx = query.createContext();
    
    // In the hot request loop:
    // Reuses `ctx` buffers. No `new` keywords.
    RoaringBitmap result = query.execute(ctx, view, input);
    ```

By explicitly managing the `QueryContext`, the engine avoids the pitfalls of `ThreadLocal` variables in environments utilizing tens of thousands of Project Loom Virtual Threads.
