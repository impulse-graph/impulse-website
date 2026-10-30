# Data-Oriented Design: Hardware-Native Graph Execution

> **Design the physical memory layout first around how the CPU transforms data, and build the abstractions around that layout.**

For the origin story of why Impulse Graph was built, how `.imps` fills the gap between Apache Parquet and Apache Arrow, and how SQLite and the Lua VM shaped our architecture, see **[Why Impulse Graph?](why-impulse.md)**. This page focuses strictly on the **physical memory layout and CPU execution mechanics** that make Impulse Graph fast.

---

## 1. Why Object-Oriented Graphs Hit a Memory Wall

Traditional graph libraries and databases model graphs using **Object-Oriented Design (OOD)** or **Array of Structures (AoS)**:

* Every vertex is a heap-allocated `Node` object with an object header, vtable pointer, external ID (`String` or `UUID`), a `Map<String, Object>` of properties, and a `List<Node>` of neighbor references.
* Traversing an edge means dereferencing a pointer to an arbitrary address in heap memory.

On a modern CPU:

* **L1 Cache Access**: ~1 nanosecond (~4 cycles)
* **Main DRAM Access (Cache Miss)**: ~80–100 nanoseconds (300+ cycles)

When a graph is stored as heap-allocated objects connected by pointers, every hop is a random memory access that misses the CPU cache and stalls the instruction pipeline for hundreds of cycles. Worse, in managed runtimes like the JVM, millions of small `Node` and `Edge` objects trigger continuous garbage collection (GC) pauses.

---

## 2. Summary: The Six Data-Oriented Transformations

Impulse Graph eliminates pointer chasing, heap allocations, and interpreter overhead through six concrete Data-Oriented Design (DOD) transformations:

| Traditional Object-Oriented Approach | Impulse Data-Oriented Design (DOD) | Hardware Impact |
| :--- | :--- | :--- |
| **1. Pointer References & Global UUIDs**<br>64-bit heap pointers or hash-table lookups per hop | **Per-Domain Dense IDs ($0 \dots N_d-1$)**<br>Configurable `uint16`, `uint32`, or `uint64` indices per domain | Node ID *is* the array index ($O(1)$ lookup, zero hashing, up to 4x smaller cache footprint) |
| **2. Adjacency Lists of Object Pointers**<br>`List<Node>` scattered across the heap | **Contiguous CSR & CSC Arrays**<br>128-byte-aligned `row_offsets[]` and `col_indices[]` in `.imps` | All neighbors of a node sit contiguously in L1 cache lines; hardware prefetcher streams ahead |
| **3. Array of Structures (AoS) Properties**<br>`Map<String, Object>` attached to each node | **Structure of Arrays (SoA) Columns**<br>128-byte-aligned primitive vectors (`age[]`, `score[]`) | Filtering `.filter("node.age >= 21")` loads only `age[]` into SIMD registers; zero wasted bandwidth |
| **4. Object Queues & Hash-Set Deduplication**<br>`Queue<Node>` and `HashSet<Long>` per BFS hop | **Off-Heap Bitset & Multi-Lane Frontiers**<br>$\lceil N_d / 64 \rceil$ 64-bit words, Roaring Bitmaps, or 8/16/32/64-bit `TYPE_LANE_FRONTIER` (`v0.9.1`) | 64 nodes tested/merged per CPU instruction (or 64 independent walks fused in one CSR pass); automatic path deduplication |
| **5. Dynamic Heap Allocations per Query**<br>Resizing lists, hash tables, and boxed objects | **Pre-Determined, Caller-Allocated Buffers**<br>Exact scratch + result size known at `prepare` time | Zero allocations (`malloc`/`new`) in the hot query path; lock-free, GC-free extreme concurrency |
| **6. AST Interpreter / Stack Machine**<br>Polymorphic `Step.next()` or `PUSH`/`POP` stack traffic | **640-Byte Register VM & `MethodHandle` JIT**<br>64-bit instructions over `R0`..`R63` (`impulse_vm_state_t`) | Entire VM state fits in 10 L1 cache lines; Java 25 C2 JIT fuses shaders into native machine code |

---

## 3. Transformation 1: Per-Domain Dense IDs ($0 \dots N_d - 1$)

Instead of assigning 64-bit memory pointers or global UUIDs to every vertex, every **Node Domain** (`User`, `Account`, `Resource`) in an `.imps` snapshot has its own independent, 0-indexed dense integer space $0 \dots N_d - 1$:

* **The ID Is the Offset**: Looking up node `k`'s outgoing edges or attribute value requires zero hashing and zero B-tree searches—it is a direct $O(1)$ array read at index `k`.
* **Configurable Integer Widths**: Each domain configures its physical integer width based on cardinality (`uint16` up to 65K nodes, `uint32` up to 4.29B nodes, or `uint64`), packing up to 4x more target IDs into every 64-byte CPU cache line.
* **Boundary Key Resolution**: External business keys (`UUID`, `String`, `int64`) are resolved to Dense IDs once at the start of the query (`fromKey` / `OP_MAP_KEYS_TO_DENSE`) and mapped back at materialization (`toKeyList` / `OP_MAP_DENSE_TO_KEYS`), keeping the entire traversal loop on dense integers.

---

## 4. Transformation 2: Contiguous CSR & CSC Adjacency Matrices

In an `.imps` snapshot, every directed relation $R: D_{\text{src}} \to D_{\text{tgt}}$ is stored as a **128-byte-aligned Compressed Sparse Row (CSR)** matrix (and optional **Compressed Sparse Column (CSC)** transpose for reverse traversals):

```text
CSR Layout in .imps (128-Byte Aligned Off-Heap Memory):
row_offsets[]: [ 0 | 3 | 5 | ... ]   ◄── Node 0's neighbors are at indices [0..3)
                 │       └────────────── Node 1's neighbors are at indices [3..5)
                 ▼
col_indices[]: [ 12 | 47 | 109 | 8 | 47 | ... ]
                 └─────┴─────┘   └───┴──► Contiguous in L1 cache; hardware prefetcher streams ahead
```

* **Zero Pointer Chasing**: Walking all outgoing edges of node `u` reads `start = row_offsets[u]` and `end = row_offsets[u + 1]`, then scans the contiguous slice `col_indices[start..end]`.
* **"Mmap and Go"**: Because `row_offsets[]` and `col_indices[]` sit at 128-byte-aligned offsets inside the `.imps` file, mounting the graph is a single OS `mmap` call.

---

## 5. Transformation 3: Structure of Arrays (SoA) vs. Array of Structures (AoS)

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

1. A single 64-byte cache line holds **16 contiguous 32-bit `age` integers** (or 32 `uint16` values).
2. A single AVX-512 or Java 25 Vector API instruction compares all 16 values against `21` in one clock cycle and writes the surviving bitmask directly into an off-heap bitset word.
3. Unreferenced attributes (`name`, `email`, `created_at`) are never paged in from disk or loaded into CPU cache.

---

## 6. Transformation 4: Bitset Frontiers & Push/Pull Direction Optimization

In a textbook Breadth-First Search (BFS) or multi-hop database join, active vertices are pushed and popped from a `Queue<Node>` or `HashSet<Long>`, allocating objects and computing hashes on every hop.

In `ImpulseVM`, an active frontier over a domain of $N_d$ nodes is represented as a contiguous off-heap **BitSet** ($\lceil N_d / 64 \rceil$ 64-bit `uint64_t` words) or compressed Roaring Bitmap:

* **64 Nodes per Register Word**: Testing, uniting (`OR`), intersecting (`AND`), or differencing (`AND NOT`) 64 nodes takes a single bitwise CPU instruction—or 512 nodes per instruction with AVX-512.
* **Zero Duplicate Work**: Converging paths across high-fanout graphs automatically coalesce via bitwise `OR` without hash-set deduplication overhead.
* **Direction-Optimizing Push/Pull**: When the frontier is sparse, `ImpulseVM` walks outgoing CSR slices (**Push**); when the frontier becomes dense, it can switch to scanning incoming CSC slices (**Pull**) and terminate early as soon as a parent bit is found.

### 6.1 Multi-Lane Bit-Sliced Frontiers (Planned `v0.9.1`: `0xC0`..`0xC9`)

When a workload evaluates up to 64 independent seed queries, concept-group expansions, or counterfactual $N-1$ edge-outage contingencies over the same graph, running 64 separate 1-bit BFS passes streams `row_offsets[]` and `col_indices[]` from DRAM 64 times.

In `v0.9.1` (Planned), `TYPE_LANE_FRONTIER` (`0x10`) transposes the frontier layout into a **bit-sliced array** (`uint8_t[N]`, `uint16_t[N]`, `uint32_t[N]`, or `uint64_t[N]`), assigning each concurrent walk or contingency to bit position $b \in [0, 63]$:

```c
// Single-pass 64-lane CSR propagation with per-edge counterfactual trip masks (OP_LANE_CSR_WALK 0xC3)
uint64_t u_lanes = current_lanes[u] & active_mask;
if (u_lanes != 0) {
    for (uint64_t e = row_offsets[u]; e < row_offsets[u + 1]; ++e) {
        uint32_t v = col_indices[e];
        next_lanes[v] |= (u_lanes & ~edge_trip_mask[e]);
    }
}
```

* **64 Walks per CSR Read**: Because `row_offsets[u]` and `col_indices[e]` are fetched once from memory and shared across all 64 bitwise lanes, memory bandwidth is amortized across up to 64 simultaneous traversals. In the Pure Java 25 `MultiLaneVmBenchmarkTest` (`50,000` nodes, `400,000` edges, 2-hop walk), wall-clock latency remains nearly flat at **`~0.23 ms`** from $L=1$ to $L=64$ lanes, scaling effective throughput from **`2,229.5 Effective Lane-MTEPS`** ($L=1$) to **`138,979.4 Effective Lane-MTEPS`** ($L=64$, a **`62.3x`** throughput multiplier over sequential single-lane execution).
* **Locality-Preserving Node Reordering (`--vamana-locality`)**: For hybrid vector-graph workloads using Section 2.6 `IMP_INDEX_VAMANA_ANN` (`0x08`, `v0.9.1`), running `impulse opt --vamana-locality` reorders dense Node IDs by a BFS traversal from the Vamana medoid $m^*$, permuting the CSR/CSC arrays, `[N, D]` `FLOAT32` embeddings, and Vamana adjacency/quantized slabs in lockstep so neighbor expansions during greedy beam search (`OP_VECTOR_ANN_SEARCH` `0xCA`) hit adjacent cache lines.

---

## 7. Transformation 5: Pre-Determined Query Memory & Zero-Allocation Hot Path

A foundational design rule of Impulse Graph is **zero memory allocations in the hot query path**:

1. **Deterministic Footprint at `prepare` Time**: Because an `.imps` snapshot is immutable and every domain's cardinality $N_d$ is fixed, the exact workspace memory required to execute a query—its 640-byte `impulse_vm_state_t` register frame, its scratch bitsets ($4 \times \lceil N_d / 64 \rceil \times 8\text{ bytes}$), and its output column projection area—is **explicitly calculated when the query is prepared** (`impulse_stmt_buffer_size(stmt)`, enforced in bytecode via `OP_ALLOC_SCRATCH` and `OP_ASSERT_SCRATCH_BYTES`).
2. **Pre-Allocated & Passed In by the Caller**:
   * **C / C++20 C-ABI**: The caller queries `impulse_stmt_buffer_size(stmt)` once, pre-allocates a reusable buffer (thread-local, stack, or arena), and passes it into `impulse_stmt_execute(stmt, buffer, buffer_size)` (see [Zero-Alloc Buffers & Projections](key-mapping-and-projections.md)).
   * **Pure Java 25**: `ImpulseVmInterpreter.execute(programSeg, instructionCount, snapshot, input, arena)` and `ImpulseStatement.execute()` operate over off-heap `MemorySegment` slices (`VmStateLayout.VM_STATE_LAYOUT` and `OffHeapBitSet`), recycling bitset handles (`acquireBitset()` / `releaseBitset()`) and ping-ponging frontiers in place via `OP_SWAP_REG`.
3. **Lock-Free, GC-Free Extreme Concurrency**: Because the `.imps` graph topology is read-only and every query executes inside its own isolated, caller-supplied workspace and 640-byte register frame, **thousands of OS threads or Java 25 Virtual Threads can execute queries concurrently over the same mapped snapshot with zero locks, zero mutex contention, and zero GC pauses.**

---

## 8. Transformation 6: The 640-Byte Register VM & Java 25 `MethodHandle` JIT

Once the graph layout is contiguous and cache-aligned, the execution engine itself must not become the bottleneck:

* **640-Byte Cache-Aligned Register Frame (`impulse_vm_state_t`)**: Inspired by the Lua VM, `ImpulseVM` uses 64 general-purpose registers (`R0`..`R63`) and fixed 64-bit `impOps` instructions (`opcode[8] | flags[8] | dst_reg[16] | payload[32]`). The entire VM execution state is exactly **640 bytes** (10 CPU cache lines), staying hot in L1 cache throughout execution.
* **Java 25 `MethodHandle` Combinator JIT (`ImpulseMethodHandleCompiler` & `ShaderCompiler`)**: Instead of interpreting bytecode in a `switch` loop at query time, the Pure Java 25 engine compiles `impOps` programs and stream-walk filter/projection shaders (`OP_CSR_WALK_STREAM`, `OP_CSC_WALK_STREAM`) into trees of `java.lang.invoke.MethodHandle` combinators using `MethodHandles.insertArguments` and `MethodHandles.foldArguments`. When invoked, the JVM's **C2 JIT compiler** constant-folds the register offsets and inlines the entire chain of shader operations into a single contiguous block of native machine code with **zero interpreter dispatch overhead**.
