# Release Notes

Chronological technical changelog across the **Impulse Graph Engine** repositories (`impulse-graph-spec`, `impulse-graph-core`, `impulse-graph-java`, `impulse-ocaml`, and `impulse-verification`).

---

## `v0.11.0` — Unified `impOps` v0.11 ISA, `.imps` v0.11 COO Layout & 2-Buffer Zero-Allocation Lifecycle

**Format Version**: `.imps` Binary Snapshot Format `v0.11.0` (`0x000B`, backward-compatible reader for `v0.9.0` and `v0.10.0`)  
**Bytecode Container**: `.impb` v11 (32-byte header + fixed 64-bit nibble-encoded instruction words)

### 1. `ImpulseVM` v0.11 Architecture & ISA Cutover
* **Compact 78-Opcode ISA (452 Subops)**: Consolidated the retired v0.10 ISA into 78 active opcodes + `0xFF` extension payload (`isa_v0_11.yaml` single source of truth generating C++, Java, OCaml, and Rust ISA tables).
* **256-Byte Hot Frame & 3-Bank Register File**: Partitioned registers into 16 scalars (`R0..R15` with Kleene 3VL validity mask & 4-bit type word), 16 frontiers (`F0..F15` with adaptive Tier-0/Tier-1/Tier-2 representation), and 16 vectors (`V0..V15`).
* **Deterministic 2-Buffer Caller-Owned Lifecycle**: `impulse_vm_plan_memory` computes static worst-case scratch and result buffer bounds; `impulse_workspace_init` placement-initializes caller-owned 128-byte-aligned scratch memory once per worker thread with zero heap allocations on hot query execution.
* **Morsel-Driven Graph Traversal**: Added `OP_WALK_MORSEL`, `OP_FILTER_MORSEL`, `OP_MORSEL_COMMIT`, and `OP_MORSEL_END` for bounded-working-set fused traversal, attribute gathering, Kleene 3VL filtering, and monoidic reduction.

### 2. `.imps` Binary Snapshot Format `v0.11.0` (`0x000B`)
* **192-Byte Relation Directory Entry**: Extended relation descriptors with dedicated 128-byte-aligned COO source, target, and edge-id arrays (`coo_src`, `coo_tgt`, `coo_edge_id`) and `coo_order` flags (`SRC_MAJOR`, `TGT_MAJOR`, `UNSORTED`, `EDGE_ID_SORTED`).
* **CLI & Writer Support**: Added v0.11 COO serialization to `impulse-rust` (`SnapshotWriter::set_relation_coo_v11`, `set_domain_dense_id_width`) and updated `impulse-cli` (`assemble`, `disassemble`, `compile`, `run`) to canonical `.impb` v11.

### 3. Polyglot FFI & Verification Gate
* **Polyglot FFI Bindings**: Migrated `impulse-rust`, `impulse-python`, `impulse-node`, `impulse-go`, and `impulse-dotnet` to `impulse_vm_v11.h` (`VmWorkspace` / `impulse_vm_execute_v11` / `impulse_vm_plan_memory`).
* **Empirical Verification Results (4-Way Parity: C++ `-O3`, C++ `-O0`, Java 25, OCaml)**:
  * **Spec Compliance Suite**: `682/682` `.impas` vectors PASS (`116` metamorphic checks across geometry profiles `P0..P3`), `78/78` opcodes (100%), `452/452` subops (100%).
  * **Metamorphic Property Gate**: `2,000/2,000` PASS across 18 algebraic/structural laws × 4 engines (`5.01s`).
  * **4-Way Differential Fuzzer**: `20,000/20,000` random fixtures (`0` divergences) + `500,000/500,000` corpus mutation iterations (`0` divergences, `14,269.9` iters/s, Dual ICTX v2 logical+physical digest identity).
  * **E2E Graph500 Benchmark (`16,384` nodes, `261,829` edges)**: C++ `2hop = 142.96 µs`, `bfs = 171.58 µs`; Java 25 `2hop = 107.63 µs`, `bfs = 181.38 µs` (exact cardinality parity: `10,308` and `10,918`).

---

## `v0.10.1` — Fast-Follow Patch: VM Parity, Arena/C-ABI Lifetimes & FFI Safety

**Release Date**: November 2026  
**Format Version**: `.imps` Binary Snapshot Format `v0.10.0` (`0x000A`) — *100% binary and API compatible; zero breaking changes*

`v0.10.1` is a fast-follow patch release consolidating four-way `ImpulseVM` differential-fuzzing fixes, off-heap arena and C-ABI memory-lifetime hardening, and multi-language FFI safety improvements across `impulse-graph-core` and `impulse-graph-java`. Existing `.imps` `v0.10.0` snapshots, `.impb` bytecode, and user queries require no changes.

### 1. Updated Registry Artifacts (`0.10.1`)
* **Maven Central (`org.impulsegraph:*:0.10.1`)**: Published `impulse-spec`, `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`, `impulse-builder`, `impulse-kotlin` (pinned to Kotlin `2.1.10` for `0.10.x` patch ABI compatibility), `impulse-scala_3`, and `impulse-clojure`, with `-sources.jar` and `-javadoc.jar` attached across all JVM language modules.
* **PyPI (`impulse-graph==0.10.1`)**, **crates.io (`impulse-graph@0.10.1`)**, & **GitHub Releases (`v0.10.1`)**: Updated pre-built wheels, self-contained Rust crate, standalone `impulse-cli` binaries, and native C/C++20 `impulse-sdk` archives.

### 2. Four-Way `ImpulseVM` Parity & Opcode Contract Fixes (`553` `.impas` Vectors)
* **38-Opcode Edge-Case Hardening**: Aligned register aliasing (`dst == src`), logical vector lengths (`0x39`, `0x43`, `0x44`), zero-length vector bounds, and `ICTX` v1 SHA-256 state hashes across C++ (`-O3`/`-O0`), Java 25, and OCaml (`impulse-ocaml`).
* **Canonical Arithmetic, Coalesce & Degree Contracts**: Enforced canonical operand ordering in `OP_VEC_MATH_UNARY` and `0x2E`/`0x2F`, mixed `f32`/`f64` promotion, empty-vector preservation in `OP_COALESCE` (`0x3B`), IEEE-754 `-0.0f` sign-bit preservation in `OP_REDUCE` (`MUL`), short input vector handling and `relId >= 16` preservation in `OP_MXV`/`OP_VXM`, literal relation fallback in `OP_KCORE_DECOMPOSITION`, and `TYPE_NODE_VECTOR` contract acceptance in `OP_CSR_DEGREE` (`0x12`).
* **Expanded Differential & Metamorphic Verification**: Added 22 `.impas` regression vectors (`531` $\to$ `553` total) surfaced by 10-profile contract fuzzing (`fuzz_vm_contracts.py`), 25-law metamorphic testing (`metamorphic_vm_test.py`), and corpus mutation (`mutate_corpus_fuzzer.py`).

### 3. Pure Java Engine Hardening (`impulse-graph-java` `0.10.1`)
* **Arena & Bitset Leak Remediation**: Eliminated `GLOBAL_POOL_ARENA` and `COMPILER_ARENA` retention leaks, cached compiled `ImpulseStatement` plans, and released temporary bitsets in `OP_SET_DIFFERENCE`.
* **Swap & Boundary Safety**: Guarded `null` `executionArena` on empty-result fallback paths, added atomic drain gating and bounded swap close in `impulse-storage`, enforced `Math.toIntExact` overflow guards, and removed silent exception swallowing in `impulse-core`.

### 4. Native C-ABI, Rust & Polyglot FFI Hardening (`impulse-graph-core` `v0.10.1`)
* **Zero-Allocation `impulse_stmt_execute()` & C-ABI Exception Guards**: Wrapped all `extern "C"` entrypoints with `IMPULSE_C_ABI_CATCH_*` barriers, replaced `std::cerr` writes in `impulse_compile_to_impas()` with thread-local `g_last_error`, eliminated the per-call `impulse_exec()` heap leak via a thread-local execution buffer, and attached a reusable `impulse_vm_context_t` to `impulse_stmt_t` (with context-owned scratch for `0xCB` `FP16`, `0x92`, and `0x93`) so repeated executions perform zero heap allocations.
* **Secondary Index & CMake Fixes**: Enforced IEEE-754 total-order `NaN`-last sorting and `NaN` range skipping in `impulse_index_build_permutation`, added strict `int64_t` outward rounding and base-type validation in `impulse_index_build_zone_map`, and installed missing `impulse_opcode_*.hpp` / `impulse_sexpr.hpp` CMake headers.
* **Rust & CLI Bounds Fixes**: Replaced unchecked metadata footer offset math in `SnapshotReader::get_metadata()` with `checked_add` slice bounds and replaced `MIN`/`MAX` integer sentinels with `Option<i64>` in `impulse-rust` / `impulse-cli` statistics.
* **Python, Go & .NET FFI Safety**: Pinned Python zero-copy `memoryview` exports with a refcounted `SnapshotLease` owner (preventing use-after-free after `Snapshot.close()`), released the Python GIL (`py::gil_scoped_release`) across native traversal/sampling/query calls, fixed `impulse_graph.__version__`, added `poolMu.RLock` + `runtime.KeepAlive` + safe slice copies in Go, and added atomic `Interlocked.Exchange` / `GC.KeepAlive` handle guards in .NET.

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
