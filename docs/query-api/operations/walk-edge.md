# Edge Traversals

Edge traversals are the core operations in Impulse Graph Engine. All traversals are explicitly directed — there is no ambiguity.

## `walkEdge(rel)`

For every node in the input set, `walkEdge` collects all neighbors reachable via the specified relation. It produces a fan-out result.

=== "Java"
    ```java
    ImpulseQuery.builder()
        .input(EntityType.USER, ArgType.SINGLE_NODE)
        .walkEdge("userToGroup")
        .collect(ReturnType.ROARING_BITSET);
    ```

=== "C++"
    ```cpp
    using Q = Collect<RoaringBitmap,
        WalkEdge<schema::USER_TO_GROUP,
            Input<schema::USER, SingleNodeArg>>>;
    ```

=== "Rust"
    ```rust
    ImpulseQuery::builder()
        .input("user", ArgType::SingleNode)
        .walk_edge("userToGroup")
        .collect::<RoaringBitmap>()
    ```

## `walkEdgeFiltered(rel, filter)`

Similar to `walkEdge`, but only follows edges that match a specified predicate. Excellent for labeled multi-graphs (e.g., following only "active" membership edges).

=== "Java"
    ```java
    ImpulseQuery.builder()
        .input(EntityType.USER, ArgType.SINGLE_NODE)
        .walkEdgeFiltered("userToGroup", EdgeFilter.byLabel("active"))
        .collect(ReturnType.ROARING_BITSET);
    ```

=== "C++"
    ```cpp
    // Assuming filter logic is defined in schema/C++ logic
    using Q = Collect<RoaringBitmap,
        WalkEdgeFiltered<schema::USER_TO_GROUP, ActiveFilter,
            Input<schema::USER, SingleNodeArg>>>;
    ```

=== "Rust"
    ```rust
    ImpulseQuery::builder()
        .input("user", ArgType::SingleNode)
        .walk_edge_filtered("userToGroup", EdgeFilter::by_label("active"))
        .collect::<RoaringBitmap>()
    ```

## `walkTarget(rel)`

Follows edges for a single-valued relation (e.g., `user.primaryOrg`). This operation asserts that the relation is 1:1 or 1:0 and returns a single optional `NodeId` rather than a set, serving as a strong optimization hint to the engine.

=== "Java"
    ```java
    ImpulseQuery.builder()
        .input(EntityType.USER, ArgType.SINGLE_NODE)
        .walkTarget("userToPrimaryOrg")
        .collect(ReturnType.SINGLE_NODE);
    ```

=== "C++"
    ```cpp
    using Q = Collect<SingleNode,
        WalkTarget<schema::USER_TO_PRIMARY_ORG,
            Input<schema::USER, SingleNodeArg>>>;
    ```

=== "Rust"
    ```rust
    ImpulseQuery::builder()
        .input("user", ArgType::SingleNode)
        .walk_target("userToPrimaryOrg")
        .collect::<SingleNode>()
    ```
