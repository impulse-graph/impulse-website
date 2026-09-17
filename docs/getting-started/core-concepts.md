# Core Concepts & Architecture Primer

Getting started with the **Impulse Graph Engine** doesn't require a background in advanced linear algebra or compiler design. However, understanding a few foundational concepts will help you design high-performance graph models and understand why Impulse is capable of sub-millisecond cold starts and sub-microsecond traversals.

Whether you are writing Java, C++, Rust, or Python, the exact same underlying mental model applies.

---

## 1. Why Graph Analytics Needs a Different Approach

In traditional application development, graphs are usually modeled in one of two ways:

1. **Object Pointers**: In-memory objects where a `Node` has a list of references to other nodes (`List<Node> neighbors`).
2. **Relational Database Tables**: A `nodes` table and an `edges` join table containing `(source_id, target_id)`.

Both approaches hit severe bottlenecks when analytics scale to millions or billions of edges:
* **Object pointer-chasing** causes constant CPU cache misses. In languages with managed memory (like Java), millions of edge objects cause heavy garbage collection (GC) thrashing and high heap overhead.
* **Relational `JOIN` queries** require expensive disk I/O, hash-join tables, and index lookups for every traversal hop.

**Impulse Graph solves this by treating the graph as a Sparse Matrix** stored in a contiguous, zero-copy, memory-mapped binary format (`.imps`).

---

## 2. Sparse Matrices for Graph Topology

Imagine a graph where rows represent **Source Nodes** and columns represent **Target Nodes**. An edge between Node $A$ and Node $B$ is represented by a `1` at coordinate $(A, B)$. This is an **Adjacency Matrix**.

```
          Target User
          0   1   2   3
Src   0 ┌ 0   1   1   0 ┐  --> User 0 follows User 1 and User 2
User  1 │ 0   0   1   0 │  --> User 1 follows User 2
      2 │ 0   0   0   0 │  --> User 2 follows nobody
      3 └ 1   1   1   0 ┘  --> User 3 follows User 0, 1, and 2
```

### The Problem with Dense 2D Matrices
If you have 1,000,000 users and each user has 50 friends:
* A standard 2D matrix would require $1,000,000 \times 1,000,000 = 1,000,000,000,000$ (1 Trillion) cells!
* That would consume **~1 Terabyte of RAM**, where **99.995% of the cells are empty zeros**.

Graphs in the real world are almost always **sparse**—most possible connections do not exist. Therefore, we store only the actual connections using **Compressed Sparse Row (CSR)** and **Compressed Sparse Column (CSC)**.

---

## 3. Compressed Sparse Row (CSR): The Forward Topology

**CSR (Compressed Sparse Row)** is the industry standard format for representing sparse matrices and graph adjacencies. It compresses the 2D grid into **two flat, contiguous integer arrays**:

1. **`row_offsets`**: Points to where each source node's target list begins and ends.
2. **`column_targets`**: Contains the actual target node IDs packed contiguously.

### Concrete Example

Let's look at the 4-node graph from above:
* **Node 0** links to: `1, 2` (2 edges)
* **Node 1** links to: `2` (1 edge)
* **Node 2** links to: `(none)` (0 edges)
* **Node 3** links to: `0, 1, 2` (3 edges)

Total edges: $2 + 1 + 0 + 3 = 6$.

In CSR format, this entire graph is stored in two compact arrays:

```
row_offsets:    [ 0,    2,    3,    3,    6 ]
                  │     │     │     │     │
Node Index:       0     1     2     3    (end)

column_targets: [ 1, 2, │ 2, │ (none), │ 0, 1, 2 ]
                  ──────  ───          ───────────
                  Node 0  Node 1         Node 3
```

### How an Edge Lookup Works in $O(1)$
To find the outgoing edges for **Node 0**:
1. Read offset range: `start = row_offsets[0]` ($0$), `end = row_offsets[1]` ($2$).
2. Slice `column_targets[0..2]`: `[1, 2]`.

To find the outgoing edges for **Node 2**:
1. Read offset range: `start = row_offsets[2]` ($3$), `end = row_offsets[3]` ($3$).
2. Because `start == end`, Node 2 has **0 outgoing edges**.

### Why CSR is Lightning Fast
* **Instant Degree Calculation**: The degree (edge count) of Node $u$ is simply `row_offsets[u + 1] - row_offsets[u]`—an instant scalar subtraction requiring zero edge traversals.
* **CPU Cache Perfection**: All neighbors of a node sit side-by-side in contiguous memory. The CPU prefetcher loads them into L1 cache in a single memory cycle.
* **Vector SIMD Friendly**: CPU vector registers (AVX-512, ARM Neon) can process 8 to 16 neighbor IDs simultaneously.
* **Primary Use**: Forward traversals (`.out("FOLLOWS")`, BFS, PageRank push).

---

## 4. Compressed Sparse Column (CSC): The Reverse Topology

While CSR makes asking *"Who does User 0 follow?"* instant, asking the reverse—*"Who follows User 2?"*—would require scanning every row in the CSR matrix.

To make incoming traversals just as fast, Impulse Graph supports **CSC (Compressed Sparse Column)**.

* **CSC is the exact transpose of CSR**.
* In CSC, the offsets array points to **Target Nodes**, and the targets array stores the **Source Nodes** that point to them.
* In our example above, looking up the incoming edges for Node 2 in CSC yields: `[0, 1, 3]` in $O(1)$ time.
* **Primary Use**: Incoming traversals (`.in("FOLLOWS")`, reverse reachability, PageRank pull).

> [!TIP]
> When building an `.imps` snapshot, CSR is mandatory. You can optionally include CSC with a single method call (`.addTopology(Topology.CSC, CompressionScheme.RAW)`). If your edge stream is sorted by source ID, the Impulse builder automatically stages and inverts the stream into CSC using external sort.

---

## 5. Universal Node Architecture: Domains & Dense IDs

One of the most important architectural rules in Impulse Graph is **Per-Domain Dense ID Independence**:

### There is NO Global Flattened ID Space
In many graph databases, every node in the entire database is assigned a synthetic global 64-bit ID (e.g., node 1000 is a User, node 1001 is a Product, node 1002 is a Store). 

Impulse Graph does not use global IDs. Instead, **each Node Domain possesses its own independent, zero-indexed dense integer space ($0 \dots N_d - 1$)**:

```
┌─────────────────────────┐         ┌─────────────────────────┐
│       User Domain       │         │     Account Domain      │
│  Cardinality: 10,000    │         │   Cardinality: 50,000   │
├─────────────────────────┤         ├─────────────────────────┤
│ Dense IDs: 0 .. 9,999   │         │ Dense IDs: 0 .. 49,999  │
│ User 0 ≠ Account 0      │         │ Account 0 ≠ User 0      │
└─────────────────────────┘         └─────────────────────────┘
```

### Why Independent Dense IDs?
1. **Direct Array Indexing**: If the `User` domain has 10,000 nodes, its `row_offsets` array has exactly 10,001 entries. Looking up User ID `42` is a direct array access (`offsets[42]`), requiring zero hash tables or ID translation.
2. **Compact Integer Widths**:
   - Small domains (e.g., categories, states, roles) with $< 65,536$ entities can use 16-bit integers (`PrimitiveWidth.UINT16`), cutting memory usage in half.
   - Standard domains use 32-bit integers (`PrimitiveWidth.UINT32`), supporting up to 4.29 billion nodes.
   - Hyperscale domains use 64-bit integers (`PrimitiveWidth.UINT64`).
3. **Domain-Bound Traversals**: Every traversal begins by binding an explicit domain context:
   ```java
   snap.domain("User").from(42).out("OWNS").toList();
   ```

---

## 6. Business Keys vs. Dense IDs (Primary Key Index)

In production databases, entities rarely have continuous 0-indexed integer IDs. You usually have:
* **UUIDs**: `"550e8400-e29b-41d4-a716-446655440000"`
* **String Business Keys**: `"USR-98421"`, `"alice@example.com"`
* **Sparse Relational IDs**: `102, 594, 100024, 8847192`

### How the Primary Key Index Works
When constructing a domain in `SnapshotBuilder`, you can enable the primary key index:

```java
DomainDefinition.builder(100_000L)
    .idWidth(PrimitiveWidth.UINT32)
    .withPrimaryKeyIndex(true)
    .build();
```

The builder writes a compact, zero-copy reverse index inside the `.imps` file that maps `External String/UUID Key -> Dense ID (0 .. N-1)`.

* **At Query Time**: You can resolve `"alice@example.com"` to Dense ID `0` in a single lookup.
* **During Traversal**: All multi-hop vector traversals execute entirely on fast primitive integers.
* **At Result Materialization**: You can map target Dense IDs back to external business keys when returning results to your API callers.

---

## 7. Columnar Attributes: Structure of Arrays (SoA)

Traditional graph databases store node and edge properties as key-value property maps inside the node object.

Impulse Graph stores attributes using a **Structure of Arrays (SoA)** columnar layout:

```
Row-Oriented (Traditional):
[ { id: 0, age: 30, score: 9.5 }, { id: 1, age: 24, score: 7.2 }, ... ]

Columnar SoA (Impulse Graph):
age[]:   [ 30,   24,   45,   19,   62, ... ]  <-- Contiguous 32-bit integers
score[]: [ 9.5,  7.2,  8.8,  6.1,  9.0, ... ]  <-- Contiguous 32-bit floats
```

### Why SoA Matters for Filtering
When evaluating a traversal filter like `.filter("node.age >= 21")`:
* The CPU loads **only** the `age` vector directly into AVX-512 SIMD registers.
* The CPU never reads `score`, names, or edge pointers from disk/RAM.
* A single vector instruction evaluates 16 node filters simultaneously, producing a bitmask in nanoseconds.

---

## 8. The Impulse Binary Snapshot (`.imps`)

All of the above primitives—CSR matrices, CSC matrices, domain catalogs, string pools, and columnar attributes—are serialized into a single immutable file ending with `.imps` (C-ABI Binary Snapshot Specification v0.9.0).

* **Page 0 (4KB)**: Fixed header with magic bytes `0x494D5053` (`IMPS`), version `0x0009`, and hardware flags.
* **128-Byte Hardware Alignment**: All sections, matrices, and attribute arrays are strictly aligned to 128-byte boundaries. This matches AVX-512 cache lines and GPU warp memory coalescing (NVIDIA GPUDirect Storage `cuFile`).
* **Zero-Copy Memory-Mapped (`mmap`)**: When your application starts, the operating system maps the `.imps` file into virtual memory in sub-milliseconds ($O(1)$). No data is copied into JVM heap or user space until traversed.

---

## 9. Conceptual Glossary Summary

| Term | Canonical Definition | Role in Impulse Graph |
| :--- | :--- | :--- |
| **`.imps`** | Impulse Binary Snapshot File (v0.9.0). | Immutable, page-aligned, zero-copy binary file format. |
| **Node Domain** | A distinct entity namespace (e.g., `User`, `Account`). | Defines an independent dense ID space $0 \dots N_d - 1$. |
| **Dense ID** | A zero-indexed primitive integer ($0 \dots N-1$). | Direct index into CSR offsets and columnar attribute arrays. |
| **Relation** | A directed edge type connecting a source domain to a target domain. | Encodes graph connections (e.g., `User -[:OWNS]-> Account`). |
| **CSR** | Compressed Sparse Row matrix format. | Contiguous `row_offsets` + `column_targets` for fast forward walks (`out`). |
| **CSC** | Compressed Sparse Column matrix format. | Transpose of CSR for fast reverse/incoming walks (`in`). |
| **COO** | Coordinate format (`src, tgt` pairs). | Stream ingestion format used before CSR/CSC compaction. |
| **Primary Key Index** | Reverse index mapping external keys (UUID, String) to Dense IDs. | Translates external business identifiers to dense integer coordinates. |
| **SoA Attributes** | Structure of Arrays columnar property storage. | Contiguous primitive vectors enabling AVX-512 SIMD filtering. |
| **`SnapshotBuilder`** | Fluent Java builder (`org.impulsegraph:impulse-builder`). | Single-pass streaming generator that builds `.imps` files direct to disk or S3. |

---

## Next Steps

Now that you understand the foundational architecture, dive into the hands-on walkthrough:

* **[Building Snapshots Walkthrough (Java)](building-snapshots.md)**: A soup-to-nuts, step-by-step tutorial building an `.imps` snapshot incrementally and streaming from JDBC relational databases.
* **[Quickstart](quickstart.md)**: Learn how to load `.imps` files and execute fluent vector traversals.
