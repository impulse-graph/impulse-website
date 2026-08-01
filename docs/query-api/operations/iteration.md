# Iteration

Iterative operations are crucial for deep traversals, transitive closures, and graph analytics algorithms like island detection.

## `repeat(step, n)`

Applies a type-preserving step exactly `n` times. This implements a fixed-depth BFS.

* **Constraint**: The output entity type of the step must match its input entity type.

=== "Java"
    ```java
    // 2-hop neighborhood sample
    ImpulseQuery<long[]> twoHop = ImpulseQuery.builder()
        .input(EntityType.NODE, ArgType.ROARING_BITSET)
        .repeat(step -> step.walkEdge("edge"), 2)
        .collect(ReturnType.NODE_ARRAY);
    ```

=== "C++"
    ```cpp
    using Q = Collect<NodeArray,
        Repeat<WalkEdge<schema::EDGE>, 2,
            Input<schema::NODE, BitsetArg>>>;
    ```

=== "Rust"
    ```rust
    let two_hop = ImpulseQuery::builder()
        .input("node", ArgType::RoaringBitset)
        .repeat(|step| step.walk_edge("edge"), 2)
        .collect::<Vec<u64>>();
    ```

## `repeatUntilStable(step)`

Computes the fixed-point (transitive closure) by applying `step` and unioning the result until no new nodes are discovered. It requires a `maxIterations` safety cap.

This operation requires a **3-buffer scratch** memory layout (accumulator, frontier, and previous check) at runtime to detect convergence.

=== "Java"
    ```java
    // All ancestors in an org hierarchy
    ImpulseQuery<RoaringBitmap> allAncestors = ImpulseQuery.builder()
        .input(EntityType.ORG, ArgType.SINGLE_NODE)
        .repeatUntilStable(step -> step.walkEdge("orgToParentOrg"))
        .collect(ReturnType.ROARING_BITSET);
    ```

=== "C++"
    ```cpp
    using Q = Collect<RoaringBitmap,
        RepeatUntilStable<
            WalkEdge<schema::ORG_TO_PARENT_ORG>,
            Input<schema::ORG, SingleNodeArg>>>;
    ```

=== "Rust"
    ```rust
    let all_ancestors = ImpulseQuery::builder()
        .input("org", ArgType::SingleNode)
        .repeat_until_stable(|step| step.walk_edge("orgToParentOrg"))
        .collect::<RoaringBitmap>();
    ```
