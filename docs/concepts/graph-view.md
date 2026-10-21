# Graph View Abstraction

The `GraphView` is the primary interface for executing queries in the Impulse Graph Engine. It acts as a unified, read-only projection of an immutable `.imps` graph snapshot at a specific point in time.

## Wrapping Read-Only Snapshots

A `GraphView` wraps an `ImpulseGraphSnapshot`. Because the snapshot is strictly immutable, the `GraphView` acts as a zero-overhead, lock-free adapter routing all queries directly to the memory-mapped (`mmap`) address space:

```java
GraphView view = snapshot.createView();
```

## Atomic A/B Snapshot Rotation

When underlying data changes, an out-of-band streaming compiler writes a new immutable `.imps` snapshot generation (`B`) while active readers continue querying the current snapshot (`A`) with zero lock contention. Once `B` is mapped into memory, `SnapshotSwapManager` performs an atomic reference swap so subsequent queries read from `B`.
