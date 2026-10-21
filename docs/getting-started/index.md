# Getting Started with Impulse Graph Engine

Welcome to the official documentation for the **Impulse Graph Engine**.

Impulse Graph decouples static and streaming-updated graph analytics from heavy database servers through the **Impulse Binary Snapshot Format (`.imps`)** and **two equivalent, first-class execution engines**:

1. **Pure Java 25 Engine (`impulse-graph-java`)**: A 100% pure Java 25 implementation using the Foreign Function & Memory (FFM) API (`MemorySegment`, `Arena`), Vector API, and `MethodHandle` JIT combinators. Ready for enterprise production with **zero third-party runtime dependencies**, **zero JNI native libraries**, and **zero GC pauses**.
2. **Native C++20 / C-ABI Engine (`impulse-graph-core`)**: A zero-dependency C++20 kernel exposing a canonical C-ABI (`impulse_graph.h`, `impulse_vm.h`) that powers C/C++ applications and polyglot SDKs for Rust, Python, Go, .NET/C#, and Node.js/TypeScript.

Both engines execute the same register-based **`ImpulseVM`** (`impOps` bytecode) directly over memory-mapped `.imps` files with 100% bitwise-identical results.

---

## Core Architectural Principles

* **The Binary Snapshot Format (`.imps`)**: Page-aligned (4KB header) and 128-byte section-aligned binary files containing Compressed Sparse Row (CSR) forward matrices, Compressed Sparse Column (CSC) reverse matrices, Structure-of-Arrays (SoA) columnar attributes, and secondary indices.
* **Instant Cold Start via `mmap`**: Snapshots map directly from NVMe disk into process virtual address space in sub-milliseconds without parsing or object deserialization.
* **Off-Heap, Lock-Free Execution**: Queries execute over immutable off-heap memory segments and pre-allocated 640-byte VM register frames without heap allocations or GC pauses.
* **Direct-to-Disk Streaming Generation**: `SnapshotBuilder` (Java) and `impulse_writer_t` (C-ABI) stream `.imps` files direct to disk or cloud object storage (S3/GCS) in $O(\text{chunk})$ physical RAM.
* **Live Delta Overlays**: `DeltaLayer` overlays and `SnapshotSwapManager` enable concurrent edge additions, tombstones, and zero-downtime atomic snapshot rotation.

---

## Where to Start

- **[Core Concepts & Glossary](core-concepts.md)**: Understand the `.imps` binary snapshot layout, CSR/CSC sparse matrices, per-domain dense IDs, and SoA columnar attributes.
- **[Installation](installation.md)**: Add the pure Java 25 engine (`org.impulsegraph`), C/C++ C-ABI kernel, or polyglot SDKs to your project.
- **[Quickstart](quickstart.md)**: Mount an `.imps` snapshot and execute domain-bound traversals and prepared statements in Java 25, C++20, and Rust.
- **[Building Snapshots Walkthrough (Java)](building-snapshots.md)**: End-to-end tutorial constructing `.imps` binary snapshots with `SnapshotBuilder` and JDBC streaming.
