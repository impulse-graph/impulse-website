# Set Algebra

Set algebra operations allow you to branch and merge query paths. 

**Type Safety Rule**: Both sides of `union`, `intersect`, and `difference` must produce the **same entity type**. 

## Operations

* **`union(q1, q2)`**: Logical OR of two node sets of the same entity type.
* **`intersect(q1, q2)`**: Logical AND. Produces nodes present in both sets.
* **`difference(q1, q2)`**: Subtraction. Nodes in `q1` but not in `q2`.

## Universe & Constants

* **`universe(type)`**: Returns the full live set for a given entity type, accounting for tombstones in the current `GraphView`.
* **`empty(type)`**: Returns the empty set.

## Examples

Branching within a query to exclude suspended groups:

=== "Java"
    ```java
    ImpulseQuery<RoaringBitmap> q = ImpulseQuery.builder()
        .input(EntityType.USER, ArgType.ROARING_BITSET)
        .difference(
            step -> step.walkEdge("userToGroup"),
            step -> step.walkEdge("userToSuspendedGroup")
        )
        .collect(ReturnType.ROARING_BITSET);
    ```

=== "C++"
    ```cpp
    using Q = Collect<RoaringBitmap,
        Difference<
            WalkEdge<schema::USER_TO_GROUP>,
            WalkEdge<schema::USER_TO_SUSPENDED_GROUP>,
            Input<schema::USER, BitsetArg>
        >>;
    ```

=== "Rust"
    ```rust
    let q = ImpulseQuery::builder()
        .input("user", ArgType::RoaringBitset)
        .difference(
            |step| step.walk_edge("userToGroup"),
            |step| step.walk_edge("userToSuspendedGroup")
        )
        .collect::<RoaringBitmap>();
    ```
