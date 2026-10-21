# Graph View Execution

The `GraphView` is the execution-time wrapper that binds a compiled query to a read-only, memory-mapped `.imps` snapshot.

## The Separation of Query and Data

By keeping compiled queries (`ImpulseQuery`, `ImpulseStatement`) independent of the underlying snapshot memory segment, the exact same compiled bytecode pipeline can run against any compatible `.imps` snapshot generation without recompilation.

## `GraphView.of(snapshot)`

All queries execute against a read-only, memory-mapped snapshot:

```java
GraphView view = GraphView.of(snapshot);
RoaringBitmap roles = query.execute(view, userBitset);
```
