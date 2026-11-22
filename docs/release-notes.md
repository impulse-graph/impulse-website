# Release Notes

Chronological technical changelog across the **Impulse Graph Engine** repositories (`impulse-graph-spec`, `impulse-graph-core`, `impulse-graph-java`, `impulse-ocaml`, and `impulse-verification`).

---

## `v0.10.0` — Multi-Lane Bit-Sliced Execution, Embedded Vamana ANN & Registry Packages

**Release Date**: November 2026  
**Format Version**: `.imps` Binary Snapshot Format `v0.10.0` (`0x000A`)

### 1. Public Package Registry Availability
* **Maven Central (`org.impulsegraph:*:0.10.0`)**: Signed artifacts (`-sources.jar`, `-javadoc.jar`) published for `impulse-spec`, `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`, `impulse-builder`, `impulse-kotlin`, `impulse-scala_3`, and `impulse-clojure`.
* **PyPI (`impulse-graph==0.10.0`)**: Pre-built `pybind11` wheels for Linux (`manylinux` `x86_64` / `aarch64`), macOS (`arm64`), and Windows (`amd64`), plus `sdist` with SLSA Level 3 build provenance attestations.
* **crates.io (`impulse-graph@0.10.0`)**: Self-contained Rust crate bundling the C++20 and Highway SIMD kernel sources (with optional `IMPULSE_SDK_DIR` override for pre-installed native SDKs).
* **GitHub Releases & Cosign v3 Attestations**: Standalone `impulse-cli` and C/C++20 SDK archives signed with Sigstore Cosign v3 (`--bundle SHA256SUMS.sigstore.json`) and GitHub Artifact Attestations.

### 2. Binary Snapshot Format `v0.10.0` (`0x000A`)
* **Embedded Vamana ANN Index (`IMP_INDEX_VAMANA_ANN = 0x08`)**: Added Section 2.6 disk-aligned Vamana proximity graph index supporting two-stage quantized routing (`BQ1` 1-bit binary, `SQ8` scalar 8-bit, `FP16` half-precision, or `NONE`) paired with exact SIMD reranking over 128-byte-aligned `[N, D]` embedding columns.
* **Domain & Relation Layout Extensions**: Added inline node domain attribute tables, virtual/flat/COO relation encodings alongside CSR/CSC, nullable attribute validity bitmaps, `INT8`/`INT16` compact primary keys, and compliance test vectors through `tc38`.

### 3. `ImpulseVM` ISA Extensions (`0xC0`..`0xCB`)
* **Multi-Lane Bit-Sliced Frontiers (`TYPE_LANE_FRONTIER = 0x10`, `0xC0`..`0xC9`)**: Generalized 1-bit node frontiers to 8-, 16-, 32-, and 64-lane bit-sliced word arrays (`OP_LANE_INIT_SEEDS`, `OP_LANE_INIT_GROUPS`, `OP_LANE_WALK`, `OP_LANE_SET_EDGE_MASK`, `OP_LANE_PRUNE_MASK`, `OP_LANE_FILTER_QUORUM`, `OP_LANE_REDUCE_AND`, `OP_LANE_REDUCE_ATTR`, `OP_LANE_SET_COVER`) to evaluate batched seed queries and $N-1$ counterfactual edge-outage sweeps in a single CSR scan without expanding the 640-byte VM register frame.
* **Vector ANN Search & Reranking (`0xCA`..`0xCB`)**: Added `OP_VECTOR_ANN_SEARCH` and `OP_VECTOR_RERANK_DOT` for single-pass hybrid graph + vector candidate retrieval inside `ImpulseVM`.
* **Four-Way Polyglot Parity**: Verified bitwise register, PC, status, and `ICTX` v1 SHA-256 state-hash identity across C++ (`-O3`), C++ (`-O0`), Pure Java 25, and the OCaml reference oracle (`166/166` active opcodes across `531` `.impas` compliance vectors).

### 4. Compiler, Query Surfaces & Runtime Hardening
* **Kleene 3-Valued Logic (3VL) & 54-Function CEL**: Implemented full Kleene `TRUE`/`FALSE`/`NULL` propagation across nullable columns, IEEE-754 `NaN`/signed-zero parity, and 54 built-in Google CEL functions across Java and C++.
* **Frontend Lowering**: Added multi-lane traversal (`MultiLaneBuilder` / `MultiLaneTraversal`) and vector ANN lowering across the Fluent API, `openCypher`, `ImpLog`, and `ImpK`.
* **Java 21 LTS & Java 22+/25 Dual-Target Runtime**: Restored full JDK 21 LTS FFM compatibility alongside JDK 22+/25 LTS, added bounded shared virtual-thread bitset/state buffer pools in `impulse-vm`, and expanded JMX / Prometheus engine telemetry.
* **CLI Consolidation & Dependency Hygiene**: Consolidated developer tooling into `impulse-graph-core/impulse-cli` (`attach-embeddings`, `convert-tensors`, `bench-vector`, `--vamana-locality`, `--quick-check`, `--deep-audit`), upgraded Rust Arrow/Parquet to `60.1.0` (removing transitive `thrift` `CVE-2026-43868`), updated `jackson-*` to `2.18.11` in non-core tooling, and added ASan/UBSan/TSan, libFuzzer, Jazzer, and OCaml Bigarray bounds checks.

---

## `v0.9.0` — Register VM, Unified In-Kernel Compiler & Read-Only Snapshot Baseline

**Format Version**: `.imps` Binary Snapshot Format `v0.9.0` (`0x0009`)

* **128-Byte Aligned `.imps` C-ABI Layout**: Fixed 4KB Page 0 header (`IMPS` magic `0x494D5053`), shared Section 2 string pool, per-domain independent dense IDs ($0 \dots N_d-1$) with configurable `uint16_t` / `uint32_t` / `uint64_t` widths, CSR/CSC adjacency slices, and Structure-of-Arrays (SoA) attribute columns with Arrow-compatible validity bitmaps.
* **64-Register `ImpulseVM` & `MethodHandle` JIT**: Fixed 64-bit `impOps` instruction encoding over registers `R0`..`R63`, C++20 Highway SIMD + OpenMP kernels, and Pure Java FFM + `jdk.incubator.vector` + `MethodHandle` combinator compilation.
* **SQLite-Style Prepared Statements**: In-kernel `ImpScheme` two-stage optimizing compiler lowering `openCypher`, `CEL`, `ImpLog`, and `ImpK` into caller-buffered `impulse_stmt_t` / `ImpulseStatement` handles (`impulse_stmt_buffer_size`) with zero hot-path heap allocations.
* **Pure Read-Only Kernel Architecture**: Removed in-memory mutable delta overlays from core execution kernels in favor of single-pass streaming `SnapshotBuilder` / `impulse build` generation and lock-free RCU Blue/Green snapshot rotation.
