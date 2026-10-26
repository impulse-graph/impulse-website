# Project Status, Announcements & Roadmap

This page tracks the current development status, subsystem readiness, announcements, and the path to the **`v1.0`** release across the **Impulse Graph Engine** ecosystem.

---

## Latest Announcements

!!! info "October 2026 — Unified Documentation Portal & API References"
    * **Documentation Website (`www.impulsegraph.org`)**: Overhauled the documentation portal (currently **85% complete**), integrating [Data-Oriented Design](concepts/data-oriented-design.md) guides, [Aggregated Java 25 Javadocs](/javadoc/index.html), and the [C-ABI Kernel & VM Reference](reference/c-abi.md).
    * **Pure Read-Only Engine Architecture Finalized**: Core execution kernels (`impulse-graph-java` and `impulse-graph-core`) focus 100% on read-only, lock-free vector traversals over immutable `.imps` binary snapshots.
    * **Java 25 `MethodHandle` Combinator JIT & Lua-Inspired VM**: Completed `ImpulseMethodHandleCompiler` and `ShaderCompiler` pipeline fusion in the Pure Java 25 engine alongside 100% four-way polyglot VM parity.

---

## Subsystem Readiness Matrix

| Subsystem / Repository | Status | Readiness | Notes |
| :--- | :--- | :--- | :--- |
| **[Binary Snapshot Format (`.imps`)](reference/spec/format-specification.md)** | Frozen | [=100% "100%"] | Page-aligned C-ABI layout, 128-byte SIMD alignment & compliance vectors (`tc01`..`tc36`) |
| **[Four-Way Polyglot VM Parity](contributing/polyglot-validation.md)** | Passing | [=100% "100%"] | 100% bitwise output identity across C++ (`-O3`), C++ (`-O0`), Pure Java 25, and OCaml reference oracle |
| **[Pure Java 25 Engine (`impulse-graph-java`)](reference/java-api.md)** | RC Ready | [=95% "95%"] | 100% Pure Java 25, zero dependencies, FFM off-heap (`MemorySegment`/`Arena`), Vector API, `MethodHandle` C2 JIT |
| **[Native C++20 / C-ABI Engine (`impulse-graph-core`)](reference/c-abi.md)** | RC Ready | [=95% "95%"] | Zero-dependency C++20 & C-ABI kernel (`libimpulse_graph`), Highway SIMD, OpenMP |
| **[Multi-Frontend Compiler (`ImpScheme` / `openCypher` / `CEL`)](concepts/compiler-architecture.md)** | RC Ready | [=90% "90%"] | Two-stage optimizer (logical AST rewriting + cost-based physical selection) & SQLite-style prepared statements |
| **[Documentation Portal (`impulse-website`)](index.md)** | Active | [=85% "85%"] | Core guides, specifications, Javadocs & C-ABI references live; remaining tutorials in progress |
| **[Developer CLI Suite (`impulse-graph-tooling`)](reference/cli.md)** | Beta | [=85% "85%"] | Standalone `impulse build`, `inspect`, `validate`, `compile`, `assemble`, `disassemble`, `run` |
| **[Polyglot Language SDKs](software-modules.md)** | Beta | [=80% "80%"] | Python (`pybind11` / NumPy / PyTorch), Rust (`impulse-rust`), Go (`CGo`), .NET/C# (`P/Invoke`), Node.js (`N-API`) |

---

## Polyglot Package Registry Distribution Status

Artifacts are built inside GitHub Actions CI pipelines with SLSA Level 3 cryptographic build provenance attestations (`actions/attest-build-provenance`) across **8 target package registries**:

| Package Manager / Registry | Target Ecosystem | Package Coordinates / Artifacts | Status | Readiness | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **[Maven Central](reference/packages.md)** | Java 25 / Kotlin / Scala 3 | `org.impulsegraph:impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`, `impulse-builder`, `impulse-spec` | RC Ready | [=90% "90%"] | Pure Java 25 modules & aggregated Javadocs built; GPG signing & Central Portal publishing staged for `v1.0` |
| **[PyPI](reference/python-api.md)** | Python (`>= 3.8`) | `impulse-graph` (`manylinux_2_28_x86_64`, `macosx_11_0_arm64` wheels & `sdist`) | Beta | [=85% "85%"] | Static C++20 `pybind11` wheels with zero-copy NumPy, SciPy CSR, and PyTorch `mmap` tensor views |
| **[Crates.io](reference/rust-api.md)** | Rust (`2021` Edition) | `impulse-graph`, `impulse-tools` | Beta | [=85% "85%"] | Zero-dependency Rust reader/writer crate & CLI optimizer |
| **[NuGet.org](reference/polyglot-sdks.md)** | .NET 8+ / C# / F# | `ImpulseGraph`, `ImpulseGraph.Native`, `ImpulseGraph.FSharp` | Beta | [=80% "80%"] | Managed P/Invoke SDK + cross-platform native runtime packs (`.nupkg`) |
| **[npm](reference/polyglot-sdks.md)** | Node.js / TypeScript / Bun | `impulse-graph` | Beta | [=80% "80%"] | N-API native addon + TypeScript `.d.ts` definitions |
| **[Go Modules](reference/polyglot-sdks.md)** | Go (`1.22+` CGo) | `github.com/impulse-graph/impulse-graph/go` | Beta | [=80% "80%"] | CGo bindings linked against `libimpulse_graph_static.a` |
| **[Vcpkg / Conan / Homebrew](reference/c-abi.md)** | C / C++20 & macOS/Linux CLI | `impulse-graph` (`libimpulse_graph_static.a`, `.dylib`, `.so`, `.dll`, `.deb`, `.rpm`, `.pkg`, `.msi`) | In Progress | [=75% "75%"] | CMake install targets & static packaging ready; registry port manifests staged for `v1.0` |
| **[GHCR / Docker](reference/packages.md)** | Containers / Kubernetes | `ghcr.io/impulse-graph/impulse-tools`, `impulse-platform-server` | In Progress | [=75% "75%"] | Static `musl-libc` Alpine/scratch CLI & platform server images |

---

## Goals Before `v1.0` Release

- [x] Finalize immutable `.imps` Binary Snapshot Format specification and 128-byte hardware alignment invariants
- [x] Achieve 100% four-way polyglot `ImpulseVM` test vector parity (C++ O3, C++ O0, Pure Java 25, OCaml)
- [x] Implement Lua-inspired register architecture (`R0`..`R63`) and Java 25 `MethodHandle` combinator JIT compilation
- [x] Remove in-memory delta overlay complexity to dedicate 100% of kernel hot paths to lock-free, read-only `.imps` traversal
- [x] Launch unified documentation website (`www.impulsegraph.org`) with hosted Java 25 Javadocs and C-ABI references (85% complete)
- [ ] Complete remaining 15% of documentation (expanded cookbook recipes, operational runbooks, and showcase deep dives)
- [ ] Complete end-to-end automated release pipelines with SLSA Level 3 cryptographic build provenance attestations
- [ ] Publish `v1.0` artifacts across Maven Central (`org.impulsegraph`), PyPI (`impulse-graph`), Crates.io, NuGet, and npm
- [ ] Publish complete reproducible empirical benchmark suite (`impulse-benchmarks`) across hardware targets

---

## Post-`v1.0` Roadmap

### 1. Multi-Snapshot Federated Traversals (C-ABI & Cross-Snapshot VM Opcodes)
* Note: Composite multi-file `manifest.yaml` loading into a unified `GraphSnapshot` is supported today in the Pure Java 25 engine via `BinarySnapshotLoader.loadFromManifest(manifestPath, arena)`.
* Post-`v1.0` extends this to cross-snapshot relation namespacing (`SnapshotA::RelationName`) in C-ABI and `ImpulseVM` bytecode, allowing a single VM pipeline to traverse across independently versioned `.imps` files via zero-copy dense ID translation vectors (`OP_REMAP_ID_SPACE`).

### 2. GPU & Accelerator Offload (`cuFile` GPUDirect Storage)
* Direct DMA transfers of 128-byte-aligned `.imps` CSR and SoA sections into NVIDIA GPU HBM via `cuFile` (GPUDirect Storage), bypassing host CPU page cache for multi-terabyte graph analytics and GNN neighborhood sampling.

### 3. Cost-Based Optimizer (CBO) & Adaptive Runtime Execution
* Expanded histogram and characteristic-set cardinality estimation in Section 2 catalog headers for multi-join `openCypher` and `ImpLog` Datalog rule ordering.
