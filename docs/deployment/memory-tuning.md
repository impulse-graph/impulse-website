# Memory & Performance Tuning Guide — Impulse Graph Engine (Java)

This guide covers FFM `Arena` lifecycle management, JVM heap sizing, Transparent Huge Pages, primitive integer width selection, and Vector API tuning for **`impulse-graph-java`** on Java 21 LTS and Java 22+/25.

---

## 1. FFM Off-Heap Architecture & Storage Structures (`impulse-storage`)

Impulse Graph stores graph topology and attributes completely off-heap via FFM `MemorySegment` buffers bound to a `java.lang.foreign.Arena`. The engine operates directly over memory-mapped `.imps` files without deserializing data into Java heap objects.

### 1.1 Off-Heap Segment Hierarchy

When a snapshot is loaded via `BinarySnapshotLoader.loadSnapshot(...)`:

1. **Memory Mapping**: The `.imps` file is mapped via `FileChannel.map(FileChannel.MapMode.READ_ONLY, 0, size, arena)`, producing an off-heap `MemorySegment`.
2. **Kernel Prefetching (`MADV_WILLNEED`)**: `BinarySnapshotLoader` immediately invokes `segment.load()`. At the OS level, this issues an `madvise(..., MADV_WILLNEED)` call, prefetching pages into the OS page cache asynchronously to eliminate soft page fault stalls during cold start.
3. **Relation Slices**: The root segment is sliced into sub-segments encapsulated inside `RelationSnapshot`:
   * `rowOffsetsSegment`: CSR row offsets array (`(N + 1) * edgeIndexWidth` bytes).
   * `columnTargetsSegment`: CSR target node IDs (`E * nodeIdWidth` bytes).
   * `cscRowOffsetsSegment` & `cscColumnTargetsSegment`: Optional CSC reverse transpose index buffers.
   * `attributeSegments`: Structure-of-Arrays (SoA) contiguous primitive and vector arrays.
   * `validitySegments`: Aligned bitmasks for nullable attributes.
4. **Container**: `GraphSnapshot` aggregates all domain relation snapshots and string catalog metadata.

---

## 2. FFM Arena Lifecycle Management (`java.lang.foreign.Arena`)

FFM arenas govern off-heap memory lifetimes. Choosing the proper arena determines thread-safety and memory unmapping behavior:

### 2.1 `Arena.ofShared()` vs. `Arena.ofConfined()`

| Arena Type | Thread Concurrency Model | Engine Usage | Lifecycle & Deallocation |
| :--- | :--- | :--- | :--- |
| **`Arena.ofShared()`** | Multi-Threaded | Active Graph Snapshots & SWMR Query Engines | Safe for concurrent worker and virtual carrier threads. Memory is unmapped when `close()` or `drainAndClose()` is explicitly called. |
| **`Arena.ofConfined()`** | Single-Threaded | Snapshot Builders & Scratch Computations | Strictly confined to allocating thread. Automatically unmaps memory upon `try-with-resources` block exit. Used internally by `SnapshotBuilder`. |

### 2.2 Production SWMR Snapshot Swapping & Safe Draining

In high-throughput 24/7 environments, incoming CDC streams or scheduled updates generate new `.imps` snapshots. To avoid JVM segmentation faults from unmapping off-heap memory while query threads are reading:

1. **Active Query Accounting**: `GraphSnapshot` maintains an off-heap reader count via `LongAdder`:
   * `enterQuery()`: Increments active query count.
   * `exitQuery()`: Decrements active query count.
   * `awaitDrained(timeout, unit)`: Non-blocking spin-wait until active reader count drops to 0.
   * `drainAndClose(timeout, unit)`: Waits for readers to complete, then unmaps the arena.
2. **Atomic Pointer Swapping**: Use `SnapshotSwapManager` for atomic A/B pointer swaps:

```java
// Initialize swap manager with active snapshot
SnapshotSwapManager<GraphSnapshot> swapManager = new SnapshotSwapManager<>(initialSnapshot);

// Query Path (Multi-Threaded Readers)
var holder = swapManager.acquireCurrent();
if (holder != null) {
    try {
        GraphSnapshot snap = holder.getResource();
        // Execute vector queries...
    } finally {
        holder.release(); // Decrements epoch reader count
    }
}

// Ingestion / Refresh Path (Atomic Pointer Swap)
// Note: The new Arena must NOT be closed in a try-with-resources block here.
// SnapshotSwapManager takes ownership of the arena/snapshot reference and
// asynchronously closes it once all active queries on the prior generation have drained.
Arena newArena = Arena.ofShared();
var newLoaded = BinarySnapshotLoader.loadSnapshot(Path.of("graph_v2.imps"), newArena);
GraphSnapshot newSnapshot = newLoaded.graph();

// Atomically swap current pointer. Spawns a virtual thread that awaits
// until the old epoch activeReaders reaches 0, then cleanly calls close().
swapManager.swap(newSnapshot);
```

---

## 3. Alignment & Page Layout

All CSR/CSC arrays, SoA attribute columns, and nullable validity bitmaps are padded to **128-byte boundaries** for SIMD vector loads and GPU transfers, and payload sections sit on 4KB OS page boundaries. See the [Binary Snapshot Format Specification](../reference/spec/format-specification.md) for exact byte offsets and validity bitmap padding formulas.

---

## 4. Recommended JVM Tuning Flags

Because graph topology and attributes reside completely off-heap in memory-mapped files, JVM heap sizing and configuration differ fundamentally from traditional graph database engines.

### 4.1 Production JVM Command Line

```bash
java --enable-preview \
     --add-modules jdk.incubator.vector \
     --enable-native-access=ALL-UNNAMED \
     -XX:+UnlockDiagnosticVMOptions \
     -XX:UseAVX=3 \                  # x86-64 only; omit on ARM64 / Apple Silicon
     -XX:+UseLargePages \
     -XX:LargePageSizeInBytes=2m \
     -XX:+UseZGC \
     -XX:+ZGenerational \
     -Xms2g -Xmx4g \
     -jar your-application.jar
```

### 4.2 Flag Rationale & Analysis

| JVM Argument | Purpose & Architectural Impact |
| :--- | :--- |
| **`--enable-preview`** | Enables preview features (FFM on Java 21 LTS baseline). Mandatory for preview compilation. |
| **`--add-modules jdk.incubator.vector`** | Binds the SIMD Vector API module for AVX-512, AVX2, and ARM Neon vector instruction synthesis. |
| **`--enable-native-access=ALL-UNNAMED`** | Grants zero-overhead off-heap native memory segment access and unmapping permissions. |
| **`-XX:UseAVX=3`** | Enables AVX-512 instruction generation on Intel/AMD x86-64 processors (omit on ARM64 / Apple Silicon / AWS Graviton). Sets `PREFERRED_VECTOR_BIT_WIDTH = 512`. |
| **`-XX:+UseLargePages`**<br>**`-XX:LargePageSizeInBytes=2m`** | Configures 2MB huge pages for JVM metadata and code cache, reducing TLB miss latency. |
| **`-XX:+UseZGC -XX:+ZGenerational`** | Low-latency generational garbage collection with sub-millisecond pauses for carrier and query threads. |
| **`-Xms2g -Xmx4g`** | **Lean Heap Sizing**: Keep the JVM heap small (2–4 GB) so remaining physical RAM stays free for the OS page cache backing `.imps` files. |

!!! note "Off-Heap Memory, `-XX:MaxDirectMemorySize`, and Kubernetes `cgroups v2`"
    `FileChannel.map` creates memory-mapped segments backed directly by the operating system page cache. Memory-mapped I/O is governed by OS virtual memory limits (`vm.max_map_count`) and available physical RAM, and is **not** bounded or constrained by the JVM's `-XX:MaxDirectMemorySize` flag. Note that inside Kubernetes containers, Linux `cgroups v2` accounts resident file-backed page cache toward pod `memory.max` (`resources.limits.memory`); see **[Day-2 Kubernetes, Hot-Swap Lifecycle & Schema Evolution](../ecosystems/java/kubernetes-and-lifecycle.md)** for container sizing formulas.

### 4.3 Engine Optimization Thresholds (`OptimizerConfig`)

The following Java system properties tune compiler heuristic thresholds:

```bash
# Minimum node degree required to activate 512-bit SIMD Vector API fused edge attribute filters
-Dimpulse.optimizer.simd.min_degree=64

# Multiplicity threshold for fusing 2-hop traversals directly in CPU registers (OP_CSR_WALK_2HOP)
-Dimpulse.optimizer.2hop.max_multiplicity=1.5

# Master toggle for experimental compiler optimization passes
-Dimpulse.optimizer.experimental=false

# Intra-query OpenMP-style degree of parallelism (default: Available CPU cores)
export IMPULSE_MAX_DOP=16
```

---

## 5. OS & Linux Kernel Memory Tuning

For high-concurrency production deployments hosting multi-gigabyte or terabyte snapshots:

### 5.1 Virtual Memory Mapping Limits (`vm.max_map_count`)
By default, Linux limits a process to 65,530 memory mappings. Large multi-domain graphs with many relations and tablespace partitions will fail with `java.io.IOException: Map failed` if this limit is reached.
```bash
# Persist in /etc/sysctl.conf
sudo sysctl -w vm.max_map_count=1048576
```

### 5.2 Transparent Huge Pages (THP) for Snapshot Mappings
Traversing sparse graphs (e.g. billion-edge BFS or PageRank) involves random edge offset lookups. Under standard 4KB pages, a 100GB graph requires over 26 million TLB entries, resulting in severe TLB cache thrashing. With 2MB huge pages, the TLB footprint drops 512x to ~51,200 entries:
```bash
# Enable madvise-based transparent hugepages
echo madvise | sudo tee /sys/kernel/mm/transparent_hugepage/enabled
echo advise  | sudo tee /sys/kernel/mm/transparent_hugepage/shmem_enabled
```

### 5.3 Page Cache & Swappiness
Because `.imps` files are opened in read-only mode, pages in the OS page cache are clean. Under memory pressure, the Linux kernel can drop clean pages instantly without writing them to disk swap:
```bash
# Minimize kernel swapping aggressiveness
sudo sysctl -w vm.swappiness=10
```

---

## 6. Primitive Node ID Width Selection (`uint16_t`, `uint32_t`, `uint64_t`)

In Impulse Graph, each Node Domain possesses an independent 0-indexed dense integer space ($0 \dots N_d-1$). Setting the domain ID width based on cardinality maximizes CPU cache density and memory bus utilization:

```
 64-Byte CPU Cache Line Packing Density Comparison
 ─────────────────────────────────────────────────────────────────────────
 • 16-bit (uint16_t): [ID0][ID1][ID2] ... [ID31] (32 Node IDs / 64B Line)
 • 32-bit (uint32_t): [ ID0  ][ ID1  ] ... [ ID15  ] (16 Node IDs / 64B Line)
 • 64-bit (uint64_t): [ ID0    ] ... [ ID7    ] (8 Node IDs / 64B Line)
 ─────────────────────────────────────────────────────────────────────────
```

### 6.1 Width Selection Matrix

| Width | Primitive | Max Domain Capacity | L1 Cache Density (64B) | Vector Tile (512-bit) | Memory (1B Edges) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`2` Bytes** | `uint16_t` | 65,536 nodes | **32 IDs** / line | **32 IDs** / tile | **2.0 GB** |
| **`4` Bytes** | `uint32_t` | 4,294,967,296 nodes | **16 IDs** / line | **16 IDs** / tile | **4.0 GB** |
| **`8` Bytes** | `uint64_t` | >4.29 Billion nodes | **8 IDs** / line | **8 IDs** / tile | **8.0 GB** |

To configure domain width during snapshot compilation with `SnapshotBuilder`:
```java
SnapshotBuilder.create()
    .addDomain("User", DomainDefinition.builder(65_000L)
        .idWidth(PrimitiveWidth.UINT16) // Configured with uint16 target width
        .build());
```

---

## 7. Zero Garbage Collection (GC) Guarantee & Verification

Because traversal frontiers propagate through pre-allocated `MemorySegment` buffers and `OffHeapBitSet` instances using `LongVector.SPECIES_PREFERRED`, the core engine query loop produces **zero heap allocations per traversal step**.

### 7.1 Microbenchmark & GC Verification

!!! note
    Modern JVMs (Java 9+) replace the legacy `-XX:+PrintGCDetails` option with unified JVM logging (`-Xlog:gc*`).

To verify zero-GC execution in continuous integration or microbenchmarks:
```bash
mvn test -pl impulse-vm -Dtest=BlueGreenDrainAndUnloadTest \
    -DargLine="--enable-preview --add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED -Xlog:gc*"
```

### 7.2 Zero-Allocation Enforcement with Epsilon GC
For deterministic latency and allocation profiling, run microbenchmarks with the no-op Epsilon GC. Any accidental heap allocation during traversal will cause immediate JVM termination:
```bash
java --enable-preview \
     --add-modules jdk.incubator.vector \
     --enable-native-access=ALL-UNNAMED \
     -XX:+UnlockExperimentalVMOptions \
     -XX:+UseEpsilonGC \
     -Xms1g -Xmx1g \
     -jar your-benchmark.jar
```

