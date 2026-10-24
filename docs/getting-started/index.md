# Getting Started

Impulse Graph Engine was built to answer a simple question:

> **"How fast can you traverse a graph?"**

Its goal is to provide **world-class performance for traversing read-only graphs.** Instead of running a heavyweight database server or storing millions of heap-allocated `Node` and `Edge` objects, Impulse Graph uses **[Data-Oriented Design](../concepts/data-oriented-design.md)**:

1. **You build an immutable `.imps` Binary Snapshot file** containing contiguous CSR/CSC adjacency arrays and columnar Structure-of-Arrays (SoA) attributes.
2. **You memory-map (`mmap`) the `.imps` file** directly into your application in under a millisecond—with zero parsing and zero heap object allocation.
3. **You execute queries off-heap** using either of Impulse's **two equivalent, first-class engines**:
   - **Pure Java 25 Engine (`impulse-graph-java`)**: A 100% pure Java 25 implementation (FFM `MemorySegment`/`Arena`, Vector API, and `MethodHandle` JIT combinators) with **zero runtime dependencies**, **zero JNI wrappers**, and **zero GC pauses**.
   - **Native C++20 / C-ABI Engine (`impulse-graph-core`)**: A zero-dependency C++20 and C-ABI kernel (`libimpulse_graph`) that powers C, C++, Rust, Python, Go, .NET/C#, and Node.js.

---

## Step-by-Step Guide

1. **[Installation](installation.md)**: Add the Pure Java 25 Maven/Gradle dependencies, C/C++ CMake package, or Python wheel.
2. **[Quickstart](quickstart.md)**: Mount an `.imps` file and run your first traversal or prepared statement in < 20 lines of code.
3. **[Core Concepts & Glossary](core-concepts.md)**: A clear, visual primer on CSR/CSC matrices, per-domain dense IDs ($0 \dots N_d-1$), primary key catalogs, and SoA attributes.
4. **[Building Snapshots Walkthrough (Java)](building-snapshots.md)**: A complete tutorial building `.imps` snapshots from in-memory collections and streaming JDBC queries.
5. **[Snapshot Builder Reference](snapshot-builder-reference.md)** & **[Ingestion Strategies](ingestion-strategies.md)**: Deep dives into schema definitions, topologies, and $O(\text{chunk})$ streaming ingestion.
