# Data-Oriented Design: How Fast Can a Graph Traversal Go?

Impulse Graph Engine began with a single foundational question:

> **"How fast can a graph traversal possibly go?"**

When you trace that question down to the physical limits of modern hardware—CPU cache lines, hardware prefetchers, branch predictors, and SIMD vector pipelines—you quickly discover that traditional graph software is bottlenecked not by the complexity of graph algorithms, but by **how data is laid out in memory**.

To reach the hardware ceiling of memory bandwidth and instruction throughput, Impulse Graph is built from the ground up using **Data-Oriented Design (DOD)**.

---

## 1. Why Object-Oriented Graphs Hit a Memory Wall

Traditional graph libraries and databases model graphs using **Object-Oriented Design (OOD)** or **Array of Structures (AoS)**:
* Every vertex is a heap-allocated `Node` object with an object header, vtable pointer, external ID (`String` or `UUID`), a `Map<String, Object>` of properties, and a `List<Node>` of neighbor references.
* Traversing an edge means dereferencing a pointer to an arbitrary address in heap memory.

On a modern CPU:
* **L1 Cache Access**: ~1 nanosecond (4 cycles)
* **Main DRAM Access (Cache Miss)**: ~80–100 nanoseconds (300+ cycles)

When a graph is stored as heap-allocated objects connected by pointers, every hop is a random memory access that misses the CPU cache and stalls the instruction pipeline for hundreds of cycles. Worse, in managed runtimes like the JVM, millions of small `Node` and `Edge` objects trigger continuous garbage collection (GC) pauses.

---

## 2. The Five Data-Oriented Transformations in Impulse Graph

Data-Oriented Design flips the priorities: **design the physical memory layout first around how the CPU transforms data, and build the abstractions around that layout.**

Impulse Graph applies five concrete DOD transformations across its storage format and execution engines:

| Traditional Object-Oriented Approach | Impulse Data-Oriented Design (DOD) | Hardware Impact |
| :--- | :--- | :--- |
| **1. Pointer References & Global UUIDs**<br>64-bit heap pointers or hash-table lookups per hop | **Per-Domain Dense IDs ($0 \dots N_d-1$)**<br>Configurable `uint16`, `uint32`, or `uint64` indices per domain | Node ID *is* the array index ($O(1)$ lookup, zero hashing, up to 4x smaller cache footprint) |
| **2. Adjacency Lists of Object Pointers**<br>`List<Node>` scattered across the heap | **Contiguous CSR & CSC Arrays**<br>Flat `row_offsets[]` and `col_indices[]` arrays | All neighbors of a node sit contiguously in L1 cache lines; hardware prefetcher streams ahead |
| **3. Array of Structures (AoS) Properties**<br>`Map<String, Object>` attached to each node | **Structure of Arrays (SoA) Columns**<br>128-byte-aligned primitive vectors (`age[]`, `score[]`) | Filtering `.filter("node.age >= 21")` loads only `age[]` into SIMD registers; zero wasted bandwidth |
| **4. AST Interpreter / Virtual Dispatch**<br>Polymorphic `Step.next()` calls per vertex | **Flat `impOps` Bytecode & 640B Frame**<br>8-byte instructions over a 64-byte-aligned register frame (`R0`..`R63`) | Entire VM execution state fits in 10 L1 cache lines; zero heap allocations during query execution |
| **5. Deserialization & Heap Loading**<br>Parsing disk blocks into in-memory objects at startup | **The `.imps` Binary Snapshot Format**<br>On-disk bytes match the exact in-memory C-ABI layout | Instant $O(1)$ cold start via `mmap`; identical zero-copy execution in Pure Java 25 and C++20 |

---

## 3. Array of Structures (AoS) vs. Structure of Arrays (SoA)

Consider evaluating `.filter("node.age >= 21")` across 10,000,000 `User` nodes where each user has an `id`, `name`, `email`, `age`, and `created_at`:

```text
Traditional Array of Structures (AoS) / Object Heap:
┌──────────────────────────────────────────┐     ┌──────────────────────────────────────────┐
│ Object Header (16B) | id | name* | age   │ ──► │ Object Header (16B) | id | name* | age   │
└──────────────────────────────────────────┘     └──────────────────────────────────────────┘
  ▲ Every 64-byte CPU cache line pulls in headers, pointers, and unused fields.

Impulse Structure of Arrays (SoA) in .imps (128-Byte Aligned):
age[]:        [ 30 | 24 | 45 | 19 | 62 | 28 | 33 | 41 | 50 | 18 | 29 | 37 | 44 | 22 | 31 | 26 ]
                └─── Single 64-byte cache line holds 16 contiguous int32 values (100% utilization)
```

In Impulse Graph's SoA layout:
1. A single 64-byte cache line holds 16 contiguous 32-bit `age` integers (or 32 `uint16` values).
2. A single AVX-512 or Java 25 Vector API instruction compares all 16 values against `21` in one clock cycle and writes the surviving bitmask directly into an off-heap bitset word.
3. Unreferenced attributes (`name`, `email`, `created_at`) are never paged in from disk or loaded into CPU cache.

---

## 4. Bitset Frontiers Instead of Object Queues

In a textbook Breadth-First Search (BFS) or multi-hop traversal, active vertices are pushed and popped from a `Queue<Node>` or `HashSet<Long>`, allocating objects and computing hashes at every step.

In `ImpulseVM`, an active frontier over a domain of $N_d$ nodes is represented as a contiguous off-heap **BitSet** ($\lceil N_d / 64 \rceil$ 64-bit `uint64_t` words) or compressed Roaring Bitmap:
* **64 Nodes per Register Word**: Testing, uniting (`OR`), intersecting (`AND`), or differencing (`AND NOT`) 64 nodes takes a single bitwise CPU instruction—or 512 nodes per instruction with AVX-512.
* **Zero Duplicate Work**: Converging paths across high-fanout graphs automatically coalesce via bitwise `OR` without hash-set deduplication overhead.
* **Direction-Optimizing Push/Pull**: When the frontier is sparse, `ImpulseVM` walks outgoing CSR slices (**Push**); when the frontier becomes dense, it can switch to scanning incoming CSC slices (**Pull**) and terminate early as soon as a parent bit is found.

---

## 5. How Data-Oriented Design Enables Pure Java 25 Parity with C++

Historically, high-performance systems written in Java suffered from the JVM's object model: every object adds a 12-to-16-byte header, arrays are heap-allocated, and large graphs cause multi-second Garbage Collection pauses.

Because Impulse Graph is strictly Data-Oriented, **the Pure Java 25 Engine (`impulse-graph-java`) does not store nodes or edges as Java objects**:
* It maps the `.imps` binary file directly into off-heap memory using Java 25's standard **`java.lang.foreign.MemorySegment` and `Arena`**.
* It processes contiguous CSR/CSC and SoA columns using Java's **`jdk.incubator.vector` SIMD API** and **`MethodHandle` JIT combinators**.
* The Java garbage collector sees **zero graph objects**—delivering predictable, sub-microsecond latency and zero GC pauses in a 100% pure Java 25 library with zero native JNI dependencies.
