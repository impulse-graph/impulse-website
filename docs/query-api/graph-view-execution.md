# Graph View Execution

The `GraphView` is the execution-time wrapper that tells the evaluator which graph data to read. It is **read-only**, **zero-copy**, and highly efficient to construct.

## The Separation of Query and Data

By keeping queries independent of the data, the exact same query object can run against a historical snapshot, a live graph, or a simulated scenario.

## `GraphView.of(snapshot)`

The most common execution path: running against a read-only, memory-mapped snapshot.

```java
GraphView view = GraphView.of(snapshot);
RoaringBitmap roles = query.execute(view, userBitset);
```

## Live Graph Overlays

When querying an `ImpulseGraph`, the `GraphView` seamlessly merges the immutable base snapshot with the mutable `CsrDeltaLayer` (additions and tombstones) at execution time.

```java
GraphView liveView = GraphView.of(liveGraph);
RoaringBitmap roles = query.execute(liveView, userBitset);
```

## Hypothetical Deltas (`ImpulseGraphDelta`)

You can create hypothetical deltas to simulate "What if this node is removed?" scenarios like N-2 contingencies or AML account freezing without modifying the base graph.

```java
ImpulseGraphDelta contingency = ImpulseGraphDelta.builder()
    .removeEdge(busA, busB, "busToBus")
    .build();

GraphView hypotheticalView = GraphView.of(baseSnapshot, contingency);
RoaringBitmap island = query.execute(hypotheticalView, seedBusId);
```
