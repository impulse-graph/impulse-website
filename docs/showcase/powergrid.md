# Showcase: Power Grid N-2 Contingency Simulation

The **impulse-powergrid** module is a high-performance C++20 engine designed for real-time electrical grid stability analysis. It consumes live 60Hz PMU (Phasor Measurement Unit) streams and runs parallel contingency simulations to predict cascading failures.

## The Challenge: N-k Contingencies

Grid operators must ensure the grid remains stable even if equipment fails.
- **N-1**: What happens if any *one* transmission line fails?
- **N-2**: What happens if any *two* lines fail simultaneously?

An N-2 simulation requires evaluating $\binom{L}{2}$ combinations. For a grid with 10,000 lines, that's nearly 50 million hypothetical scenarios. They must be evaluated incredibly fast to be useful in real-time operations.

## Island Detection

The primary topological concern in grid stability is "islanding" — a subset of the grid becoming physically disconnected from the main generation sources, leading to a blackout in that sector.

=== "C++"
    ```cpp
    // Compile-time query for island detection
    using IslandDetector = Collect<RoaringBitmap,
        RepeatUntilStable<
            Union<
                WalkEdge<schema::BUS_TO_BUS>,
                WalkEdge<schema::BUS_TO_GENERATOR>
            >
        >
    >;
    ```

## `ImpulseGraphDelta` for Hypothetical Removals

Instead of cloning the entire grid graph 50 million times, Impulse Graph uses `ImpulseGraphDelta` to apply thread-local, zero-copy topological masks.

=== "C++"
    ```cpp
    // Evaluate scenarios in a parallel loop
    std::for_each(std::execution::par, contingencies.begin(), contingencies.end(), 
        [&](const auto& pairOfLines) {
            
            // 1. Create a lightweight delta removing the two hypothetical lines
            ImpulseGraphDelta delta;
            delta.removeEdge(pairOfLines.line1, schema::BUS_TO_BUS);
            delta.removeEdge(pairOfLines.line2, schema::BUS_TO_BUS);
            
            // 2. Wrap the base snapshot with the delta mask
            GraphView hypotheticalView = GraphView::of(baseSnapshot, delta);
            
            // 3. Execute the detector (stack allocated context)
            QueryContext<IslandDetector> ctx;
            RoaringBitmap connectedSet = IslandDetector::execute(ctx, hypotheticalView, seedBusId);
            
            // 4. Analyze island status
            if (connectedSet.cardinality() < TOTAL_EXPECTED_BUSES) {
                alertSystem.fireN2Violation(pairOfLines);
            }
        });
    ```

## Performance

By leveraging C++20 template metaprogramming, SIMD vectorization, and stack allocation, the `impulse-powergrid` engine can evaluate tens of thousands of N-2 scenarios per second on a standard multi-core workstation.
