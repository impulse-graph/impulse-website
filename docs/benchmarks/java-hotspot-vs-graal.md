# Java VM Benchmark: OpenJDK HotSpot C2 vs. Oracle GraalVM JIT & Project Leyden AOT

This benchmark report presents empirical performance comparisons for the **Impulse Graph Java VM Engine** across **OpenJDK HotSpot C2** (with JDK 25 Project Leyden `-XX:AOTCache`) and **Oracle GraalVM JIT**, alongside architectural build notes for **GraalVM Native Image (`native-image`)**.

---

## 1. Empirical `twitter-2010` Benchmark Suite Matrix (41.65M Nodes, 1.47B Edges, 10 Threads)

All evaluations below were conducted on **Apple Silicon M-Series (ARM64 NEON 128-bit SIMD, 10 Threads)** over the **`twitter-2010.imps` Graph Snapshot** (**41,652,230 Nodes**, **1,468,365,182 Edges**, **6.040 GB** zero-copy memory-mapped binary snapshot):

| Benchmark Workload (`twitter-2010.imps`, 10 Threads) | C++ GAPBS Reference (10 Threads) | Impulse C++20 Kernel (`impulse_vm.cpp`) | Impulse Java VM HotSpot C2 (OpenJDK) | Impulse Java VM Graal JIT | Best Engine / Primary Architectural Driver |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **0. Off-Heap `mmap` Dataset Load Time** | `0.047 ms` *(pre-mapped)* | **`0.038 ms`** | `7.869 ms` (`9.748 ms` cold w/ Leyden AOT) | `16.703 ms` | **Impulse C++20** (`0.038 ms` direct `mmap`) |
| **1A. Full-Graph Direction-Optimizing BFS** *(Root 0, Optimized CSR+CSC Hybrid)* | `149.00 ms` | **`145.00 ms`** | **`240.29 ms`** (`1.65x` of C++20) | — | **Impulse C++20** (`145.00 ms`) / **Java 25** (`1.65x` parity) |
| **1B. Full-Graph Parallel BFS** *(Root 613, Pre-Hoist Baseline)* | `2,476.26 ms` (`593.0 MTEPS`) | **`779.37 ms`** (`1,884.0 MTEPS`) | `3,191.67 ms` (`443.6 MTEPS`) | `3,668.51 ms` (`385.9 MTEPS`) | **Impulse C++20** (Pre-hoist baseline before `VmQueryContext` bitset reuse) |
| **2. 2-Hop Targeted BFS Micro-Query** *(Steady-State Micro-Latency)* | N/A | — | **`2.8 µs – 4.13 µs`** | `3.7 µs` | **Java HotSpot C2** (`MethodHandle` Combinator Fusion) |
| **3. CC (Connected Components)** *(39,681,514 Components via `OP_CC_AFFOREST`)* | **`138.69 ms`** (`10,587.3 MTEPS`) | `156.73 ms` (`9,368.6 MTEPS`) | `349.60 ms` (`4,200.1 MTEPS`) | **`311.23 ms`** (`4,717.9 MTEPS`) | **Graal JIT** (`1.12x` faster than HotSpot C2 via Union-Find loop unrolling) |
| **4. PR (PageRank per iteration)** *(10 Iterations via `OP_MXV`)* | `2,286.45 ms` / iter | `1,940.12 ms` / iter | `1,890.30 ms` / iter | **`1,680.10 ms`** / iter | **Graal JIT** (`1.13x` faster than HotSpot C2 on float SpMV pull pass) |

!!! note
    **Why Row 1A (`240.29 ms`) is `13.3x` faster than Row 1B (`3,191.67 ms`)**:
    Row 1B reflects an earlier baseline (`Twitter2010BfsVmBenchmarkTest` from Root 613) where per-level frontier arrays were allocated inside the BFS loop. Hoisting off-heap bitset buffers into a reusable `VmQueryContext` and applying direction-optimizing push/pull switching reduced 10-thread Java 25 BFS latency to **`240.29 ms`** (`1.65x` of the `145.00 ms` C++20 kernel; see [Benchmarks](../benchmarks.md)).

---

## 2. JDK 25 Project Leyden AOT Cache (`-XX:AOTCache`) vs. Cold JVM Startup

Recording and pre-linking class metadata, `MethodHandle` combinators, and C2 JIT profiles into a Project Leyden AOT cache (`-XX:AOTMode=record` / `-XX:AOTMode=create` / `-XX:AOTCache=...`) eliminates cold-start warmup penalties:

| Workload / Experiment Mode (`twitter-2010.imps`) | JVM Flags / AOT Mode | Warmup Iterations | Cold-Start Load Time | First Invocation Latency | Post-Warmup Latency (10k iters) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **BFS Baseline (Cold JVM)** | Standard JVM flags | `0` | `14.557 ms` | `332 µs` (`0.332 ms`) | — |
| **BFS Leyden AOT Production** | `-XX:AOTCache=impulse.aotcache` | `0` | **`9.748 ms`** (`1.49x` faster) | `369 µs` (`0.369 ms`) | — |
| **BFS Post-C2 JIT (Vector API)** | `--add-modules jdk.incubator.vector` | `10,000` | `5.784 ms` | `222 µs` (`0.222 ms`) | **`4.13 µs`** (`0.0041 ms`) |
| **CC Baseline (Cold JVM)** | Standard JVM flags | `0` | `16.501 ms` | `776 µs` (`0.776 ms`) | — |
| **CC Leyden AOT Production** | `-XX:AOTCache=impulse_cc.aotcache` | `0` | **`9.899 ms`** (`1.67x` faster) | **`321 µs`** (**`2.42x` faster cold**) | — |
| **CC Post-C2 JIT (Vector API)** | `--add-modules jdk.incubator.vector` | `10,000` | `5.784 ms` | `329 µs` (`0.329 ms`) | **`9.88 µs`** (`0.0098 ms`) |

---

## 3. Deployment Recommendations: HotSpot C2 vs. GraalVM JIT

* **OpenJDK HotSpot C2 + Project Leyden (`-XX:AOTCache`)**: Recommended default for standard enterprise microservices, Spring Boot applications, and container deployments on both **ARM64 (Apple Silicon / AWS Graviton)** and **AMD64 (x86_64)**. Achieves **`9.75 ms`** cold snapshot load times and **`2.8 µs – 4.13 µs`** targeted multi-hop query latencies via `ImpulseMethodHandleCompiler`.
* **Oracle GraalVM JIT (JVM Mode)**: Recommended for compute-heavy analytical batch sweeps such as full-graph **Connected Components (`OP_CC_AFFOREST`)** and **PageRank (`OP_MXV`)**, where Graal's aggressive loop unrolling and bounds-check elimination provide a **`12%–13%` throughput advantage** over HotSpot C2.

---

## 4. Building GraalVM Native Image Distributables & Architectural Constraints

!!! warning
    **Empirical Architecture Constraint (ARM64 vs. AMD64 for GraalVM `native-image`)**:

    - **GraalVM JIT (JVM mode)**: Full 100% support for Java 25 Foreign Function & Memory (FFM) API across both **ARM64** (Apple Silicon / AWS Graviton) and **AMD64** (`x86_64`).
    - **GraalVM Native Image AOT (`native-image`)**: FFM Foreign API support (`-H:+ForeignAPISupport`) is currently supported **exclusively on AMD64 (`x86_64`) architectures**. Attempting to build a `native-image` binary with FFM on ARM64 / Apple Silicon fails at build time with:
      `Error: Support for the Foreign Function and Memory API is currently available only on the AMD64 architecture.`
    - On ARM64 platforms, use **OpenJDK 25 with Project Leyden AOT Cache (`-XX:AOTCache`)** for fast startup (`9.75 ms`), or use the native C++20/Rust CLI (`impulse`).

### Build Command (AMD64 Linux / macOS `x86_64` Only)
```bash
native-image \
    --enable-preview \
    --add-modules jdk.incubator.vector \
    -H:+UnlockExperimentalVMOptions \
    -H:+ForeignAPISupport \
    -H:+EnableURLProtocols \
    --enable-native-access=ALL-UNNAMED \
    -O3 \
    -jar target/impulse-server-executable.jar \
    -o impulse-native-server
```

---

## 5. Benchmark Execution Commands

To re-run the `twitter-2010` Java VM benchmark suite locally:

```bash
# 1. Full-Graph BFS Benchmark
mvn test -pl impulse-vm -Dtest=Twitter2010BfsVmBenchmarkTest

# 2. Connected Components (OP_CC_AFFOREST) Benchmark
mvn test -pl impulse-vm -Dtest=Twitter2010CcVmBenchmarkTest

# 3. PageRank SIMD SpMV (OP_MXV) Benchmark
mvn test -pl impulse-vm -Dtest=Twitter2010PrVmBenchmarkTest
```
