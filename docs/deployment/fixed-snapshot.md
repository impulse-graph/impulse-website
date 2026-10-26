# Archetype 2: Fixed-Snapshot Analytical Process

The **Fixed-Snapshot Analytical Process** archetype is built for heavy offline compute workloads where the graph topology does not change during the execution run. This pattern is widely used in High-Performance Computing (HPC), machine learning pipelines, and complex systems simulations like the **Electrical Power Grid N-2 Contingency Simulation**.

This architecture typically leverages **C++20** or **Rust** to achieve maximum instruction throughput, utilizing compile-time query plans and stack-allocated scratch space.

## The Consistent World Assumption

In a fixed-snapshot environment, the engine memory-maps the base `.imps` file exactly once at startup. Because there is no concurrent writer mutating a delta layer, the engine enjoys a **consistent world assumption**:

- **No Locks**: No read-write locks or concurrency checks on the hot path.
- **No Tombstone Masking**: Traversals read directly from the contiguous Compressed Sparse Row (CSR) arrays.
- **Cache Friendly**: Hardware prefetchers can aggressively stream adjacency lists.

## Pre-Compiled `ImpulseVM` Bytecode Execution

When the schema is fixed for an analytical run, queries are compiled once into an immutable `CompiledQuery` (`impulse::vm::CompiledQuery` in C++20 or `MethodHandle` in Java 25) and executed across thousands of simulation seeds with zero per-query compilation overhead:

=== "C++20 (`impulse_vm_fluent.hpp`)"
    ```cpp
    #include "impulse_graph.h"
    #include "impulse_vm_fluent.hpp"

    using namespace impulse::vm;

    // Compile the island detection pipeline once at startup
    CompiledQuery islandDetector = QueryBuilder()
        .inputNode(0)
        .repeatUntilStable([](QueryBuilder& b) {
            b.walkEdge(/*BUS_TO_BUS=*/ 0);
        })
        .collectBitset()
        .compile();
    ```

## Reusable Thread-Local Execution Contexts

Because analytical processes often run parallel simulations (e.g., Monte Carlo or N-1/N-2 contingency sweeps across OpenMP threads), avoiding per-iteration heap allocation is critical. In C++ and Java, each worker thread reuses its own `impulse_vm_context_t` / `VmQueryContext` and stack-allocated `impulse_vm_state_t` register frame:

=== "C++20"
    ```cpp
    // Allocated once per worker thread
    impulse_vm_context_t* ctx = impulse_vm_context_create(snap);
    impulse_vm_state_t state{};

    // Hot simulation loop: 640-byte stack frame + reusable bitset pool
    for (uint64_t seedBusId : contingencySeeds) {
        QueryResult res = islandDetector.executeWithContext(ctx, &state, seedBusId);
    }

    impulse_vm_context_destroy(ctx);
    ```
