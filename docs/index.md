# Impulse Graph Engine

> High-Performance C-ABI Binary Snapshot Graph Engine for Ultra-Low Latency Traversals, AI/ML, and Enterprise Applications.

---

## Key Features

* **Zero-Copy Memory-Mapped Snapshots**: Query multi-gigabyte or terabyte-scale graphs directly from disk via `mmap` with sub-millisecond cold start.
* **C-ABI Open Specification**: Unified binary layout (Version 2.3) supporting **Java 25 (FFM)**, **C++20**, **Rust**, **Python (PyTorch)**, **C# (.NET 9)**, and **Fortran**.
* **Lock-Free SIMD Evaluation**: Parallel SIMD vector kernels (AVX2 / AVX-512 / ARM NEON / Java `VectorAPI`) executing millions of queries per second per pod.
* **Ultra-Lean Core**: 100% pure in-memory engine kernel with **zero third-party dependencies**.

---

## Ecosystem Repositories

* [**impulse-graph**](software-modules.md#2-polyglot-tri-core-architecture--repository-organization): Core polyglot engine workspace.
* [**impulse-tools**](software-modules.md#32-offline-heavy-optimizer--developer-tools-impulse-tools): Offline C++ snapshot optimizer & inspector CLI.
* [**impulse-benchmarks**](software-modules.md#5-github-organization-master-repository-sitemap): Reproducible JMH and Google Benchmark harnesses.
