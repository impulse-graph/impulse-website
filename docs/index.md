# Impulse Graph Engine

![Impulse Graph Engine Banner](assets/banner_letterbox.jpg)

**Impulse Graph Engine** is an embedded, read-only graph engine built around an immutable binary snapshot format (**`.imps`**) and a 64-register bytecode virtual machine (**`ImpulseVM`**).

---

## 1. Core Design

* **Single-File `.imps` Snapshots**: Compile a graph once into an immutable binary file and `mmap` it directly from disk—no server process, no deserialization, and no heap loading.
* **Pre-Allocated Query Memory**: Because domain sizes are fixed per snapshot, the exact scratch and result buffer footprint is known at `prepare` time (`impulse_stmt_buffer_size`) and passed in by the caller—avoiding per-hop heap allocations and GC pauses in the hot path.
* **Two Zero-Dependency Engines**: Both the **Pure Java 21/25** engine (FFM + Vector API) and the **Native C++20 / C-ABI** engine have zero third-party runtime dependencies and execute the same 64-bit `impOps` bytecode with bitwise parity.
* **One VM, Multiple Query Frontends**: Fluent Traversal API, read-only parameterized **openCypher**, Datalog (**ImpLog**), GraphBLAS (**ImpK**), and **Google CEL** filters all compile through `ImpScheme` IR into `impOps`.
* **`v0.10.0` Capabilities**: 8/16/32/64-lane bit-sliced frontiers (`0xC0`..`0xC9`) for batched seeds and $N-1$ contingency walks, plus embedded Vamana ANN vector search (`0x08`, `0xCA`..`0xCB`).

For the architectural story and Java-vs-C++ performance breakdown, see **[Why Impulse Graph?](concepts/why-impulse.md)** and **[Benchmarks](benchmarks.md)**.

---

## 2. Dual-Engine Overview

| Capability | Pure Java Engine (`impulse-graph-java`) | Native C++20 / C-ABI (`impulse-graph-core`) |
| :--- | :--- | :--- |
| **Implementation** | Pure Java 21 LTS / 25 (no JNI wrappers) | C++20 with `extern "C"` ABI (`impulse_graph.h`) |
| **Memory & Buffers** | Java FFM (`MemorySegment`, `Arena`) | OS `mmap` + caller-supplied buffers |
| **VM & SIMD** | `ImpulseVM` + `MethodHandle` JIT + Vector API | `ImpulseVM` + Google Highway SIMD + OpenMP |
| **Ecosystem** | Java, Kotlin, Scala 3, Clojure | C, C++20, Rust, Python (NumPy/PyTorch), Go, .NET, Node.js |
| **Registries (`0.10.0`)** | Maven Central (`org.impulsegraph`) | PyPI (`impulse-graph`), crates.io (`impulse-graph`), GitHub Releases |

---

## 3. See It in Action

=== "Java 25 (Fluent API)"
    ```java
    try (Arena arena = Arena.ofShared()) {
        ImpulseGraphSnapshot snap = BinarySnapshotLoader.loadSnapshot(Path.of("social.imps"), arena).getGraph();

        List<Long> friends = snap.domain("User")
            .fromKey("usr_alice")
            .out("FOLLOWS")
            .filter("node.age >= 21 && node.active == true")
            .toList();
    }
    ```

=== "Java 25 (openCypher)"
    ```java
    try (ImpulseStatement stmt = snap.prepare(
            "MATCH (u:User)-[:FOLLOWS]->(f:User) WHERE u.id = $uid AND f.age >= $minAge RETURN f.id")) {
        stmt.bindNode("uid", 42L).bindLong("minAge", 21L);
        try (RowReader rows = stmt.execute()) {
            while (rows.next()) {
                long friendId = rows.getNodeId(0);
            }
        }
    }
    ```

=== "C / C++20 (C-ABI)"
    ```c
    impulse_stmt_t* stmt = NULL;
    impulse_stmt_prepare(snap, "MATCH (u:User)-[:FOLLOWS]->(f:User) WHERE u.id = $uid RETURN f.id", &stmt);

    size_t buf_size = impulse_stmt_buffer_size(stmt);
    impulse_stmt_bind_node(stmt, "uid", 42);
    impulse_stmt_execute(stmt, preallocated_buffer, buf_size);

    const uint64_t* ids = (const uint64_t*)impulse_stmt_column_data(stmt, 0);
    impulse_stmt_finalize(stmt);
    ```

=== "Python"
    ```python
    from impulse_graph import Snapshot

    with Snapshot("social.imps") as snap:
        followed = snap.traverse(start_node=42, catalog={"FOLLOWS": 0}).out("FOLLOWS").to_list()
        friend_ids = snap.cypher(
            "MATCH (u:User)-[:FOLLOWS]->(f:User) WHERE u.id = $uid RETURN f",
            params={"uid": 42},
            catalog={"FOLLOWS": 0},
        )
        row_offsets = snap.get_row_offsets_array(0)
        col_indices = snap.get_col_indices_array(0)
    ```

---

## Explore the Documentation

* **[Getting Started](getting-started/index.md)**: Installation, Quickstart, and Snapshot Builders.
* **[Why Impulse Graph?](concepts/why-impulse.md)**: Architectural motivation, format trade-offs, and Java vs. C++ performance analysis.
* **[Data-Oriented Design](concepts/data-oriented-design.md)**: Dense IDs, CSR/CSC locality, SoA columns, and pre-allocated query buffers.
* **[SDK References](reference/java-api.md)**: [Java](reference/java-api.md) ([Javadocs](/javadoc/index.html)), [Python](reference/python-api.md), [C / C++20](reference/c-abi.md), [Rust](reference/rust-api.md), and [CLI](reference/cli.md).
* **[Specifications & Validation](reference/spec/format-specification.md)**: [`.imps` Format](reference/spec/format-specification.md), [ImpulseVM ISA](reference/spec/vm-specification.md), [Polyglot Validation](contributing/polyglot-validation.md), and [Benchmarks](benchmarks.md).
