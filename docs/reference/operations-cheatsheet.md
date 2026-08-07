# Query Operations Cheatsheet

The `ImpulseQueryBuilder` API provides a polyglot, declarative API for constructing type-safe graph traversals. Below is a cheatsheet of all available operations.

## Core Traversals

| Operation | Signature | Description |
|-----------|-----------|-------------|
| `walkEdge("rel")` | `Bitset<A> → Bitset<B>` | Collects **all** neighbors reachable via the named relation. |
| `walkEdgeFiltered("rel", filter)` | `Bitset<A> → Bitset<B>` | Follows edges whose properties match the predicate (e.g., `EdgeFilter.byLabel("active")`). |
| `walkTarget("rel")` | `Bitset<A> → NodeId<B>` | Follows a 1:1 or 1:0 relation, returning a single node rather than a set. |

=== "Java"
    ```java
    .walkEdge("userToGroup")
    ```
=== "C++"
    ```cpp
    WalkEdge<schema::USER_TO_GROUP>
    ```
=== "Rust"
    ```rust
    .walk_edge("userToGroup")
    ```

## Set Algebra

| Operation | Signature | Description |
|-----------|-----------|-------------|
| `union(q1, q2)` | `(Bitset<A>, Bitset<A>) → Bitset<A>` | Logical OR. Combines two node sets of the same entity type. |
| `intersect(q1, q2)` | `(Bitset<A>, Bitset<A>) → Bitset<A>` | Logical AND. Nodes present in both sets. |
| `difference(q1, q2)` | `(Bitset<A>, Bitset<A>) → Bitset<A>` | Subtraction. Nodes in `q1` but not in `q2`. |

=== "Java"
    ```java
    .union(step -> step.walkEdge("A"), step -> step.walkEdge("B"))
    ```

## Iteration & Transitive Closure

| Operation | Signature | Description |
|-----------|-----------|-------------|
| `repeat(step, n)` | `Bitset<A> → Bitset<A>` | Applies a step exactly `n` times. Requires input and output entity types to match. |
| `repeatUntilStable(step)` | `Bitset<A> → Bitset<A>` | Applies `step` and unions the result repeatedly until no new nodes are added (Transitive Closure). |

=== "Java"
    ```java
    .repeatUntilStable(step -> step.walkEdge("parentOrg"))
    ```

## Collectors (Terminals)

| Terminal | Return Type | Description |
|----------|-------------|-------------|
| `collect(ROARING_BITSET)` | `RoaringBitmap` | Sparse, compressed bitset. Ideal for sets. |
| `collect(DENSE_BITSET)` | `long[]` | Dense words. Good for downstream SIMD logic. |
| `collect(NODE_ARRAY)` | `long[]` (Java) / `Tensor` (Python) | Sorted ID array. Best for serialization or ML batches. |
| `collect(COUNT)` | `long` | Cardinality only. Avoids memory materialization. |

=== "Java"
    ```java
    .collect(ReturnType.ROARING_BITSET)
    ```

## AST & Disassembler Export

| Method | Signature | Description |
|--------|-----------|-------------|
| `exportAst()` | `() → String` | Pretty-prints the query AST pipeline steps. |
| `disassemble(snapshot)` | `(ImpulseGraphSnapshot) → String` | Disassembles compiled VM bytecodes into annotated assembly text. |

=== "Java"
    ```java
    String astTree = query.exportAst();
    String asmText = query.disassemble(snapshot);
    ```

## Snapshot Blue/Green & Drain Operations

| Method | Signature | Description |
|--------|-----------|-------------|
| `compiledQuery.rebind(newSnap)` | `(GraphSnapshot) → void` | Atomically re-binds relation IDs and JIT MethodHandles to a new blue/green snapshot. |
| `snapshot.getActiveQueryCount()` | `() → long` | Returns the count of in-flight queries currently executing against this snapshot. |
| `snapshot.drainAndClose(timeout, unit)`| `(long, TimeUnit) → void` | Awaits in-flight queries to drain and closes off-heap memory segments safely. |

=== "Java"
    ```java
    compiledQuery.rebind(newSnapshot);
    oldSnapshot.drainAndClose(5, TimeUnit.SECONDS);
    ```
