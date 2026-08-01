# Archetype 2: Fixed-Snapshot Analytical Process

The **Fixed-Snapshot Analytical Process** archetype is built for heavy offline compute workloads where the graph topology does not change during the execution run. This pattern is widely used in High-Performance Computing (HPC), machine learning pipelines, and complex systems simulations like the **Electrical Power Grid N-2 Contingency Simulation**.

This architecture typically leverages **C++20** or **Rust** to achieve maximum instruction throughput, utilizing compile-time query plans and stack-allocated scratch space.

## The Consistent World Assumption

In a fixed-snapshot environment, the engine memory-maps the base `.imps` file exactly once at startup. Because there is no concurrent writer mutating a delta layer, the engine enjoys a **consistent world assumption**:

- **No Locks**: No read-write locks or concurrency checks on the hot path.
- **No Tombstone Masking**: Traversals read directly from the contiguous Compressed Sparse Row (CSR) arrays.
- **Cache Friendly**: Hardware prefetchers can aggressively stream adjacency lists.

## C++20 Template Chain Execution

When the schema is known at compile time (`constexpr`), C++20 template metaprogramming can generate a zero-overhead, fully inlined execution plan. 

=== "C++"
    ```cpp
    // Schema defined as constexpr
    namespace schema {
        constexpr EntityType BUS { .id = 0x01, .name = "Bus" };
        constexpr Relation BUS_TO_BUS { .id = 0x10, .src = BUS, .dst = BUS };
    }
    
    // Type-level query chain
    using IslandDetector = Collect<RoaringBitmap,
        RepeatUntilStable<
            WalkEdge<schema::BUS_TO_BUS,
                Input<schema::BUS, SingleNodeArg>>>>;
                
    // Execute: fully inlined, zero virtual dispatch
    RoaringBitmap island = IslandDetector::execute(view, seedBusId);
    ```

## Stack-Allocated Scratch Buffers

Because analytical processes often run parallel simulations (e.g., Monte Carlo simulations), avoiding heap allocation is critical. In C++ and Rust, you can allocate the query execution context directly on the stack or reuse pre-allocated thread-local arenas.

=== "C++"
    ```cpp
    // Context sized exactly for the required intermediate bitsets
    QueryContext<IslandDetector> ctx; // Stack allocated
    
    RoaringBitmap island = IslandDetector::execute(ctx, view, seedBusId);
    ```

## Hypothetical Contingency Overlays

While the base snapshot is immutable, analytical processes often test "what-if" scenarios by applying lightweight, thread-local deltas over the base view.

=== "C++"
    ```cpp
    // Simulate removing transmission line 42 and 87
    ImpulseGraphDelta contingency;
    contingency.removeEdge(42, schema::BUS_TO_BUS);
    contingency.removeEdge(87, schema::BUS_TO_BUS);
    
    // Thread-safe hypothetical view
    GraphView hypotheticalView = GraphView::of(baseSnapshot, contingency);
    ```
