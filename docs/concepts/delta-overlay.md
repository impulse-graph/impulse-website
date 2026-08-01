# Delta Overlay

Since an `ImpulseGraphSnapshot` is strictly immutable, the engine supports real-time, live mutations (insertions, updates, deletions) through a memory abstraction called the **Delta Overlay**.

## The CsrDeltaLayer

When you instantiate a live `ImpulseGraph`, it mounts a `CsrDeltaLayer` on top of a base snapshot. 

The `CsrDeltaLayer` is a thread-safe, concurrent data structure residing entirely in RAM. When a mutation occurs:
- **Additions**: New edges and nodes are recorded directly into concurrent adjacency arrays in the delta layer.
- **Deletions (Tombstones)**: The engine uses highly optimized `RoaringBitmap` tombstones to mark nodes or edges in the immutable snapshot as logically deleted. 

When a query is executed, the `GraphView` transparently merges the static disk-backed snapshot reads with the in-memory delta lists, yielding a perfectly consistent view of the graph state at the time the query was issued.

## Atomic Reference Swaps

Updates to the `CsrDeltaLayer` publish to readers via **Atomic Reference Swaps**. Whether using Java's `VarHandle`, C++ `std::atomic`, or Rust `AtomicPtr`, readers always observe a stable, lock-free view of the delta layer while writers safely append to new structures.

## A/B Snapshot Compaction

As the in-memory delta layer grows, memory usage increases. The standard lifecycle pattern involves an offline or background thread generating a new baseline snapshot (`B`), merging the old snapshot (`A`) and the accumulated delta layer. Once the new `B` snapshot is ready on disk, the `ImpulseGraph` performs an atomic pointer swap to base future queries off of `B`, immediately dropping the old delta memory.
