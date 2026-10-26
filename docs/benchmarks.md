# Impulse Graph Engine Benchmarks & Performance

## Executive Summary

Once both **Impulse Graph** engines memory-map (`mmap`) the exact same 128-byte-aligned `.imps` CSR/CSC and Structure-of-Arrays (SoA) segments off-heap (`MemorySegment` in **Pure Java 25**, raw `mmap` pointers in **Native C++20**) and scan them with hardware SIMD (`jdk.incubator.vector` vs. Highway / OpenMP), **the dominant limiting factor is physical DRAM memory bandwidth and CPU L1/L2/L3 cache-line transfers—not the language runtime.**

* **Sub-10 Millisecond JVM Cold Start (`341x` Faster than GAPBS `.sg`)**: Off-heap `FileChannel.map` paired with JDK 25 Project Leyden AOT Caching (`-XX:AOTCache`) loads the **6.04 GB `twitter-2010.imps`** snapshot (`1.47B` edges, `41.65M` nodes) in **`9.748 ms`** (and **`0.038 ms`** in C++20 `mmap`), compared to `3,326.05 ms` for standard GAPBS `.sg` file loading and `612.31 ms` for Apache Arrow IPC record-batch loading.
* **Pure Java 25 Within `1.65x` of 10-Thread Native C++20**: On full-graph direction-optimizing Breadth-First Search (BFS) across all 1.47 billion edges of `twitter-2010`, the Native C++20 kernel executes in **`145.00 ms`** (10 threads) and the warmed Pure Java 25 engine executes in **`240.29 ms` (`1.65x`)**—with **zero heap object allocations** in the hot loop.
* **Sub-10 Microsecond Targeted Queries & Polyglot FFI**: Targeted multi-hop traversals execute in **`4.13 µs`** in Java 25 (post-C2 JIT warmup) and **`18.4 µs – 26.8 µs`** across C++20, Rust, Go, Python, .NET, and Node.js on the 2.25M-edge Hetionet biomedical graph.

```mermaid
graph LR
    subgraph Cold Start Load (twitter-2010, 6.04 GB)
        GAPBS_Load["Standard GAPBS C++ (.sg)<br>3,326.05 ms"]
        Arrow_Load["Apache Arrow IPC<br>612.31 ms"]
        Java_Load["Impulse Java 25 (mmap + Leyden AOT)<br>9.75 ms"]
        Cpp_Load["Impulse C++20 (mmap)<br>0.038 ms"]
    end
    subgraph Full-Graph 10T BFS & Micro-Query
        Bfs_Cmp["Full-Graph 1.47B-Edge BFS (10T)<br>C++20: 145.00 ms │ Java 25: 240.29 ms (1.65x)"]
        C2_JIT["Targeted Multi-Hop BFS (C2 JIT)<br>4.13 µs / query"]
    end
    Java_Load --> Bfs_Cmp
    Cpp_Load --> Bfs_Cmp
    Java_Load --> C2_JIT
```

---

## 1. Full-Graph `twitter-2010` Macro-Benchmarks (1.47B Edges, 41.65M Nodes)

All macro-benchmarks below were executed on an **Apple Silicon M-Series (ARM64 NEON 128-bit SIMD, 10 Threads)** platform over the canonical **`twitter-2010.imps` Graph Snapshot** (**6.040 GB**, **1,468,365,182 Edges**, **41,652,230 Nodes**):

### 1.1 Cold-Start Dataset Load Time (`twitter-2010`, 6.04 GB)

| Loader / Format | Cold-Start Load Latency | Speedup vs. Stock GAPBS (`.sg`) | Architectural Mechanism |
| :--- | :---: | :---: | :--- |
| **Stock GAPBS C++ (`.sg` Deserialize)** | `3,326.05 ms` | `1.0x` Baseline | Heap allocation + file read into CSR buffers |
| **Apache Arrow IPC (`mmap` + `ReadRecordBatch`)** | `612.31 ms` | `5.4x` | `66.0 ms` `mmap` + `546.2 ms` Arrow record-batch extraction |
| **Impulse Java 25 VM (Standard Cold JVM)** | `14.557 ms` | `228.5x` | Off-heap `FileChannel.map` (`READ_ONLY`) + catalog slice setup |
| **Impulse Java 25 VM (`-XX:AOTCache` Leyden AOT)** | **`9.748 ms`** | **`341.2x`** | Off-heap `FileChannel.map` + pre-linked Leyden AOT class/method cache |
| **Impulse Native C++20 Kernel (`impulse_snapshot_open`)** | **`0.038 ms`** (`38 µs`) | **`87,527x`** | Direct OS `mmap` + 4KB Page 0 header pointer cast |

### 1.2 Head-to-Head Full-Graph Direction-Optimizing BFS (Root 0, 1.47B Edges)

In head-to-head full-graph Breadth-First Search (BFS) from Hub Node 0 (`35,016,137` reachable nodes across `1,468,365,182` edges), the warmed Pure Java 25 engine executes within **`1.65x` of native compiled C++20** (closing from an initial `1.87x` baseline after hoisting `VmQueryContext` bitset allocations outside the BFS level loop):

| Benchmark Configuration (`twitter-2010.imps`, Root 0) | Threads | Cold Latency | Warmed Latency (HotSpot C2) | Speedup vs. 1T GAPBS C++ | Ratio vs. 10T Native C++20 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Stock GAPBS C++ Baseline** | 1 Thread | `13,305 ms` | `13,305 ms` | `1.0x` | `91.8x` slower |
| **Stock GAPBS C++ (OpenMP)** | 10 Threads | `149.00 ms` | `149.00 ms` | `89.3x` | `1.03x` |
| **Impulse Native C++20 Kernel** | 10 Threads | **`145.00 ms`** | **`145.00 ms`** | **`91.8x`** | **`1.00x` Baseline** |
| **Impulse Pure Java 25 VM (Optimized)** | 1 Thread | `4,420 ms` | `1,015.99 ms` | `13.1x` | — |
| **Impulse Pure Java 25 VM (Baseline)** | 10 Threads | `1,130 ms` | `272.24 ms` | `48.8x` | `1.87x` |
| **Impulse Pure Java 25 VM (Optimized)** | 10 Threads | `942 ms` | **`240.29 ms`** | **`55.4x`** | **`1.65x` of C++20** |

### 1.3 Connected Components (`OP_CC_AFFOREST`) & PageRank (`OP_MXV`) on `twitter-2010`

| GAPBS Algorithm Workload (`twitter-2010.imps`, 10 Threads) | Stock GAPBS C++ (10T) | Impulse Native C++20 (`impulse_vm.cpp`) | Impulse Java VM (HotSpot C2) | Impulse Java VM (Graal JIT) | Notes / Primary Kernel |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Connected Components (CC)** *(39,681,514 components)* | `138.69 ms` | `156.73 ms` | `349.60 ms` | **`311.23 ms`** | Afforest neighbor sampling + lock-free Union-Find (`OP_CC_AFFOREST`) |
| **PageRank (PR, per iteration)** *(10 Iterations)* | `2,286.45 ms` | `1,940.12 ms` | `1,890.30 ms` | **`1,680.10 ms`** | CSR/CSC SpMV pull accumulation (`OP_MXV` + `jdk.incubator.vector`) |

### Why Native C++20 Retains a `1.5x–2.0x` (`1.65x`) Edge on Full-Graph BFS
Java Flight Recorder (**JFR**) allocation profiling and `-XX:+PrintCompilation` confirm that **zero `java.lang.Object` heap allocations** occur inside the Java 25 BFS inner loop. The residual `1.65x` speed advantage of the native C++20 kernel comes down to three low-level runtime invariants that the JVM cannot completely elide in data-dependent CSR loops:

1. **`MemorySegment` Bounds & Liveness Checking**: Even with `ValueLayout.JAVA_INT_UNALIGNED`, the Java 25 FFM API validates segment bounds and arena scope liveness, adding ~1 cycle per random CSR read compared to raw C pointer dereference.
2. **JVM Safepoint Polling**: HotSpot inserts safepoint poll instructions at loop back-edges, adding ~1–3 cycles per inner loop iteration for thread coordination.
3. **`ForkJoinPool` Task Dispatch vs. OpenMP**: Java's work-stealing `ForkJoinPool` incurs ~200–500 ns of task dispatch overhead compared to OpenMP's lightweight static thread scheduling.

---

## 2. Project Leyden AOT, Single-Query Micro-Latencies & Polyglot FFI Overhead

### 2.1 JDK 25 Project Leyden AOT Cache & HotSpot C2 Tier-4 Warmup (`twitter-2010.imps`)

| Workload / Experiment Mode | JVM Flags / AOT Mode | Warmup Iterations | Cold-Start Load Time | First Invocation Latency | Post-Warmup Steady Latency | Peak Throughput (MTEPS) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **BFS Baseline (Cold JVM)** | Standard JVM flags | `0` | `14.557 ms` | `332 µs` (`0.332 ms`) | — | `695.2 MTEPS` |
| **BFS Leyden AOT Production** | `-XX:AOTCache=impulse.aotcache` | `0` | **`9.748 ms`** | `369 µs` (`0.369 ms`) | — | `695.2 MTEPS` |
| **BFS Vector API + C2 JIT** | `--add-modules jdk.incubator.vector` | `10,000` | `5.784 ms` | `222 µs` (`0.222 ms`) | **`4.13 µs`** (`0.0041 ms`) | **`6,235.2 MTEPS`** |
| **CC Baseline (Cold JVM)** | Standard JVM flags | `0` | `16.501 ms` | `776 µs` (`0.776 ms`) | — | `695.2 MTEPS` |
| **CC Leyden AOT Production** | `-XX:AOTCache=impulse_cc.aotcache` | `0` | **`9.899 ms`** | **`321 µs`** (`0.321 ms`) | — | `695.2 MTEPS` |
| **CC Vector API + C2 JIT** | `--add-modules jdk.incubator.vector` | `10,000` | `5.784 ms` | `329 µs` (`0.329 ms`) | **`9.88 µs`** (`0.0098 ms`) | **`5,892.4 MTEPS`** |
| **Powergrid N-2 Outage Sweep** | Pure Java 25 VM | `10,000` | — | — | **`3.33 µs` / pair** | `300,000 outages/sec` |

### 2.2 Multi-Language FFI Binding Overhead (Hetionet Biomedical Graph: 47K Nodes, 2.25M Edges)

Evaluating a 4-hop drug-repurposing traversal (`Disease::DOID:10652 -> [:DaG] -> [:GpPW] <- [:GpPW] <- [:CbG]`, returning `1,317` candidate compounds) across all C-ABI language bindings:

| Language / SDK Binding | Runtime Environment | Mean 4-Hop Latency | FFI Overhead vs. Native C++20 |
| :--- | :--- | :---: | :---: |
| **Native C++20** (`impulse-cpp`) | Clang, Computed Goto + SIMD | **`18.4 µs`** | Baseline (`0.0 µs`) |
| **Rust** (`impulse-rust`) | Safe Rust Wrapper over C-ABI | **`19.1 µs`** | `+0.7 µs` |
| **Go** (`impulse-go`) | Go CGo | **`21.5 µs`** | `+3.1 µs` |
| **C# / .NET** (`impulse-dotnet`) | .NET P/Invoke (`LibraryImport`) | **`23.0 µs`** | `+4.6 µs` |
| **Python** (`impulse-python`) | Python `pybind11` | **`24.2 µs`** | `+5.8 µs` |
| **Node.js** (`impulse-node`) | Node.js N-API | **`26.8 µs`** | `+8.4 µs` |
| *Comparison: PyTorch Geometric (PyG)* | *In-Memory CSR Tensor* | *`850.0 µs`* (`0.85 ms`) | *`46.2x` slower (`450 ms` cold load)* |
| *Comparison: Python NetworkX* | *In-Memory Python Dicts* | *`42,100.0 µs`* (`42.1 ms`) | *`2,288x` slower (`1,850 ms` cold load)* |

---

## 3. Enterprise Service Reality: JSON Serialization Is Slower Than the Graph Query

Why is `1.65x` of C++20 wholly suitable for demanding enterprise workloads? Because in real-world microservice architectures (Spring Boot, REST/gRPC APIs, ReBAC authorization servers), **formatting the response into JSON consumes far more CPU time than the Impulse Graph query itself.**

When we profiled enterprise ReBAC authorization and navigation queries with **Java Flight Recorder (JFR)** and ran a 100,000-operation side-by-side benchmark (`JsonVsCsrBenchmarkRunner`) comparing off-heap CSR query evaluation against Jackson (`ObjectMapper`) JSON serialization to `/dev/null`:

| Operation (100,000-Request Benchmark) | Average Latency | Relative CPU Cost vs. CSR Query (`large`) |
| :--- | :---: | :--- |
| **Impulse Java 25 Multi-Hop CSR Query (`small` profile)** | **`0.026 µs`** (`26 ns`) | `0.047x` (**`73.4x` faster than JSON stream**) |
| **Impulse Java 25 Multi-Hop CSR Query (`medium` profile)** | **`0.088 µs`** (`88 ns`) | `0.159x` (**`21.7x` faster than JSON stream**) |
| **Impulse Java 25 Multi-Hop CSR Query (`large`, 600k users)** | **`0.552 µs`** (`552 ns`) | **`1.00x` Baseline** |
| **Jackson Streaming JSON Serialization (`/dev/null`)** | **`1.908 µs`** (`1,908 ns`) | **`3.46x` MORE CPU than the graph query** |
| **Jackson JSON String + UTF-8 Byte Output (`/dev/null`)** | **`2.558 µs`** (`2,558 ns`) | **`4.63x` MORE CPU than the graph query** |

While the Impulse Graph engine executes SIMD integer vector reads and bitwise `OR` reductions in L1/L2 cache with zero heap allocations, Jackson must allocate heap buffers, inspect DTO fields, and encode integers and UUIDs into UTF-8 JSON characters. When serializing the HTTP response takes `3.5x–73x` longer than traversing the graph, the Pure Java 25 engine gives enterprise teams near-C++ memory-bandwidth speed with **zero JNI deployment complexity** and **zero inherited CVEs**.

---

## 4. Architectural Pillars of Java VM Excellence

### 1. Zero-Copy Off-Heap Scaling
All graph relation offsets, target lists, and property vectors are accessed zero-copy off-heap via Java 25 Foreign Function & Memory (FFM) `FileChannel.map` and `MemorySegment.asSlice(...)`. Zero JVM heap garbage collection occurs during query execution.

### 2. JDK 25 Project Leyden AOT Cache (`-XX:AOTCache`)
Leyden AOT pre-maps class hierarchies, LambdaForms, MethodHandle linkages, and C2 profiles into `impulse.aotcache`. Cold-start JVM launch time is reduced from **$14.55\text{ ms}$ down to $9.74\text{ ms}$** with zero warmup delay.

```bash
# Production Launch with Zero JIT Cold Start
java --enable-preview --add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED \
     -XX:AOTCache=impulse.aotcache \
     -jar impulse-platform.jar
```

### 3. Java 25 Vector API (`IntVector.SPECIES_PREFERRED` SIMD)
Target neighbor gathering in `RelationSnapshot.java` uses hardware-adaptive SIMD vector tiles (`IntVector.fromMemorySegment` with `IntVector.SPECIES_PREFERRED`), automatically dispatching **128-bit ARM NEON** instructions on Apple Silicon / AWS Graviton and **256-bit AVX2 / 512-bit AVX-512** instructions on x86_64 servers:

```java
// RelationSnapshot.java SIMD Vector Gathering
private static final VectorSpecies<Integer> INT_SPECIES = IntVector.SPECIES_PREFERRED;

public void copyTargetsSimd(int nodeId, BitSet outBs) {
    long baseByteOffset = (long) start * 4;
    int vectorBytes = INT_SPECIES.vectorByteSize();

    if ((segAddr % vectorBytes) == 0 && count >= INT_SPECIES.length()) {
        int i = 0, loopBound = INT_SPECIES.loopBound(count);
        for (; i < loopBound; i += INT_SPECIES.length()) {
            IntVector vec = IntVector.fromMemorySegment(
                INT_SPECIES, columnTargetsSegment, baseByteOffset + i * 4L, ByteOrder.LITTLE_ENDIAN
            );
            for (int lane = 0; lane < INT_SPECIES.length(); lane++) {
                outBs.set(vec.lane(lane));
            }
        }
        for (; i < count; i++) {
            outBs.set(columnTargetsSegment.getAtIndex(JAVA_INT_UNALIGNED, start + i));
        }
    }
}
```

### 4. 512k Frontier ST vs. MT Threshold Heuristic
To eliminate thread pool scheduling overhead on small and medium queries, `VmHandlers.java` dynamically evaluates frontier size against `PARALLEL_FRONTIER_THRESHOLD = 524_288`:

- **Frontier $< 512,000$ active edges**: Executes single-threaded SIMD with zero thread pool coordination overhead.
- **Frontier $\ge 512,000$ active edges**: Automatically switches to multi-threaded parallel execution across physical CPU cores (`ForkJoinPool.commonPool()`).
