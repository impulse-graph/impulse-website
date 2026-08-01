# Graph View Abstraction

The `GraphView` is the primary interface for executing queries in the Impulse Graph Engine. It acts as a unified projection of the graph topology at a specific, stable point in time.

## Wrapping Read-Only Snapshots

At its simplest, a `GraphView` wraps a raw `ImpulseGraphSnapshot`. Because the snapshot is immutable, the `GraphView` simply acts as a fast-path adapter, routing all queries directly to the `mmap` memory space. 

```java
GraphView view = snapshot.createView();
```

## Live ImpulseGraph

In scenarios requiring live updates, an `ImpulseGraph` object orchestrates the merging of a snapshot and a `CsrDeltaLayer`. When you request a view from a live graph, it yields a composite `GraphView` that seamlessly interleaves data from disk and RAM. The query logic interacting with the view remains completely unchanged.

## Hypothetical Deltas (ImpulseGraphDelta)

For advanced analytical workloads, security modeling (like ReBAC), or "What-If" scenarios, users can construct an `ImpulseGraphDelta`. This allows you to create a cheap, local delta layer, branch off a base `GraphView`, and apply hypothetical edges (e.g., "What if this user had this permission?").

The resulting hypothetical `GraphView` isolates these changes exclusively to the thread evaluating the query, providing branching multiversion concurrency control without corrupting global state.
