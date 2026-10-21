# Query API Overview

Welcome to the Impulse Graph Engine Query API. The Query API provides a type-safe, composable, and allocation-free environment for executing complex graph traversals.

## Queries are Pure Values

The most important concept in the Impulse Query API is that **queries are pure values**. A query is an immutable, serializable AST (Abstract Syntax Tree) with **no reference to any specific graph instance**. 

It can be created at startup, cached, composed into larger queries, sent over a wire, and executed repeatedly against different graph generations.

## Query Lifecycle

The execution-time graph parameterization relies on a short-lived `GraphView` wrapper:

```text
STARTUP RUNTIME SNAPSHOT ROTATION
─────────────────────────────────────────────────────────────────────────────────────

ImpulseQuery (long-lived) GraphView (short-lived) ImpulseQuery (reused ✓)
  │                                │                                │
  │ Built once from               │ Wraps current graph           │ Same query object,
  │ pure AST (no graph ref)       │ state for one execute()       │ new GraphView
  │                                │                                │
  ▼                                ▼                                ▼
ImpulseQuery.builder() GraphView.of(snapshot) GraphView.of(newSnapshot)
  .input(USER, BITSET)      ──▶ query.execute(view, input) ──▶ query.execute(newView, input)
  .walkEdge("userToGroup")
  .walkEdge("groupToRole") GraphView.of(liveGraph)
  .collect(ROARING)          ──▶ query.execute(view, input)

                                  GraphView.of(snapshot, delta)   ← custom delta injection
                             ──▶ query.execute(view, input)      ← N-2 contingency
```

## Polyglot Consistency

The same logical operations map 1:1 across Java, Rust, Python, and others:

=== "Java"
    ```java
    ImpulseQuery<RoaringBitmap> q = ImpulseQuery.builder()
        .input(EntityType.USER, ArgType.ROARING_BITSET)
        .walkEdge("userToGroup")
        .walkEdge("groupToRole")
        .collect(ReturnType.ROARING_BITSET);
    ```

=== "C++"
    ```cpp
    using Q = Collect<RoaringBitmap,
        WalkEdge<schema::GROUP_TO_ROLE,
            WalkEdge<schema::USER_TO_GROUP,
                Input<schema::USER, BitsetArg>>>>;
    ```

=== "Rust"
    ```rust
    let q = ImpulseQuery::builder()
        .input("user", ArgType::RoaringBitset)
        .walk_edge("userToGroup")
        .walk_edge("groupToRole")
        .collect::<RoaringBitmap>();
    ```
