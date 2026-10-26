# Enterprise JVM Ecosystem Guide: HotSpot, GraalVM, Corretto, Azul Prime & OpenJ9

Because the **Pure Java 25 Impulse Graph Engine** (`impulse-graph-java`) has **zero third-party runtime dependencies** and relies strictly on standard JDK APIs—**Foreign Function & Memory (`java.lang.foreign`)**, **Vector API (`jdk.incubator.vector`)**, and **`java.lang.invoke.MethodHandle`**—it runs across all compliant Java 21 LTS+ and Java 25 LTS enterprise JVM distributions.

This guide summarizes our verified empirical JVM measurements alongside architectural compatibility and tuning guidance for the major enterprise JVM runtimes.

---

## 1. Verified Empirical Baseline: OpenJDK HotSpot C2 vs. Oracle GraalVM JIT

Evaluated on **Apple Silicon M-Series (ARM64 NEON, 10 Threads)** over the **6.04 GB `twitter-2010.imps`** snapshot (`41.65M` nodes, `1.47B` edges; see [HotSpot vs. GraalVM Report](java-hotspot-vs-graal.md) and [Main Benchmarks](../benchmarks.md) for full reproduction commands):

| Empirical Metric (`twitter-2010.imps`) | OpenJDK HotSpot C2 (JDK 25 + `-XX:AOTCache`) | Oracle GraalVM JIT (JVM Mode) | Key Takeaway |
| :--- | :---: | :---: | :--- |
| **Cold-Start Snapshot Load (`mmap` + AOT)** | **`9.748 ms`** (`7.869 ms` warm) | `16.703 ms` | Leyden `-XX:AOTCache` delivers `< 10 ms` JVM cold start. |
| **2-Hop Targeted BFS Micro-Latency** | **`2.8 µs – 4.13 µs`** | `3.7 µs` | HotSpot C2 inlines `MethodHandle` combinator chains with zero heap allocations. |
| **Full-Graph Connected Components (10T)** | `349.60 ms` (`4,200.1 MTEPS`) | **`311.23 ms`** (`4,717.9 MTEPS`) | Graal JIT's loop unrolling accelerates `OP_CC_AFFOREST` by `1.12x`. |
| **Full-Graph PageRank SpMV (10T)** | `1,890.30 ms` / iter | **`1,680.10 ms`** / iter | Graal JIT accelerates float vector pull accumulation (`OP_MXV`) by `1.13x`. |
| **Hot-Path Heap GC Pauses** | **`0.00 ms`** (Zero Heap Allocations) | **`0.00 ms`** (Zero Heap Allocations) | Topology and VM registers live 100% off-heap in FFM `MemorySegment`s. |

---

## 2. Enterprise JVM Runtime Compatibility & Architecture Matrix

| JVM Distribution | FFM (`MemorySegment`) Support | Vector API (`jdk.incubator.vector`) SIMD | Cold-Start Acceleration Mechanism | Primary Production Target |
| :--- | :--- | :--- | :--- | :--- |
| **OpenJDK 25 (HotSpot C2)** | Full (`AMD64` & `ARM64`) | Full (`AVX-512`, `AVX2`, `ARM NEON`) | **Project Leyden AOT Cache** (`-XX:AOTCache`) | Reference standard for Linux/macOS/Windows enterprise deployments |
| **Amazon Corretto 25** | Full (`AMD64` & `ARM64`) | Full (`AVX-512`, `AVX2`, `ARM NEON` / SVE) | **Project Leyden AOT Cache** (`-XX:AOTCache`) | AWS EC2 Graviton3 / Graviton4 (`ARM64` Neoverse) & EKS |
| **Oracle GraalVM JIT (JVM Mode)** | Full (`AMD64` & `ARM64`) | Full (Graal Vectorizer + Vector API) | JVM CDS / AOT Cache | Compute-intensive graph analytics (PageRank, Connected Components) |
| **GraalVM Native Image (`native-image`)** | **AMD64 (`x86_64`) Only** (`-H:+ForeignAPISupport`; unsupported on `ARM64`) | Experimental on `native-image` | AOT Native Binary (No JVM warmup) | Serverless / CLI containers on `x86_64` Linux |
| **Azul Platform Prime (Zing)** | Full (`x86_64` & `ARM64` Linux) | LLVM Falcon JIT auto-vectorization + Vector API | Falcon ReadyNow! profile log | Strict SLA financial trading & fraud services with large auxiliary heaps (C4 GC) |
| **Eclipse OpenJ9 / IBM Semeru** | Supported (JDK 21+) | Supported via OMR JIT | Shared Classes Cache (`-Xshareclasses`) | Memory-constrained Kubernetes pod packing where minimal base JVM RSS is required |

---

## 3. Runtime-Specific Deployment Notes

### 1. OpenJDK 25 & Amazon Corretto 25 (Recommended Default)
* **Why**: Zero custom build steps, full support for `IntVector.SPECIES_PREFERRED` SIMD intrinsics on both x86_64 (`AVX-512`/`AVX2`) and ARM64 (`NEON`), and sub-10ms cold start via Project Leyden (`-XX:AOTCache`).
* **Recommended Flags**:
  ```bash
  java --add-modules jdk.incubator.vector \
       --enable-native-access=ALL-UNNAMED \
       -XX:+UseZGC -XX:+ZGenerational \
       -XX:AOTCache=impulse.aotcache \
       -Xms2g -Xmx4g \
       -jar application.jar
  ```

### 2. Azul Platform Prime (Falcon LLVM JIT + C4 GC)
* **Why**: While Impulse Graph itself performs **zero heap allocations** on the query hot path, enterprise applications often co-locate graph traversal alongside heavy heap-allocating frameworks (Spring Boot, Jackson JSON serialization, Kafka consumers, gRPC protobuf marshaling). Azul Prime's C4 collector eliminates GC tail-latency spikes from those surrounding application layers, while the LLVM-based Falcon JIT aggressively vectorizes off-heap loops.

### 3. Eclipse OpenJ9 / IBM Semeru
* **Why**: OpenJ9's Shared Classes Cache (`-Xshareclasses`) and compact internal metadata reduce the baseline JVM RSS overhead of the host microservice container, leaving more physical node RAM available for the OS page cache (`mmap` `.imps` pages).

### 4. GraalVM Native Image (`x86_64` Only)
* **Constraint**: As detailed in the [HotSpot vs. GraalVM Report](java-hotspot-vs-graal.md#4-building-graalvm-native-image-distributables-architectural-constraints), GraalVM `native-image`'s `-H:+ForeignAPISupport` flag is currently restricted to **AMD64 (`x86_64`)** and throws an `UnsupportedFeatureException` at build time on ARM64 / Apple Silicon. For ARM64 deployments requiring instant startup, use OpenJDK 25 with `-XX:AOTCache` or the native C-ABI / Rust engine.
