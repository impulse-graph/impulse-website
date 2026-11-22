# Project Status, Announcements & Roadmap

This page tracks the current development status, subsystem readiness, announcements, and the path to the **`v1.0`** release across the **Impulse Graph Engine** ecosystem. For version-by-version changelogs, see **[Release Notes](release-notes.md)**.

---

## Latest Announcements

!!! success "November 2026 — Official `v0.10.0` Packages Live on PyPI, Maven Central & crates.io"
    `v0.10.0` packages are now published and installable directly from public language registries:

    * **PyPI (`pip install impulse-graph==0.10.0`)**: Pre-built wheels for Linux (`x86_64` / `aarch64`), macOS (`arm64`), and Windows (`amd64`), plus `sdist` with SLSA Level 3 provenance attestations.
    * **Maven Central (`org.impulsegraph:*:0.10.0`)**: Published `impulse-spec`, `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`, `impulse-builder`, `impulse-kotlin`, `impulse-scala_3`, and `impulse-clojure` with `-sources.jar` and `-javadoc.jar` artifacts.
    * **crates.io (`cargo add impulse-graph@0.10.0`)**: Self-contained `.crate` bundling the C++20/Highway kernel sources (with optional `IMPULSE_SDK_DIR` prebuilt SDK override).

!!! tip "November 2026 — Impulse Graph `v0.10.0` Released"
    Tagged `v0.10.0` across `impulse-graph-spec`, `impulse-graph-core`, `impulse-graph-java`, `impulse-ocaml`, and `impulse-verification`:

    * **Binary Snapshot Format `v0.10.0` (`0x000A`)**: Inline node domain attributes, virtual/flat/COO relation layouts, nullable attribute bitmaps, `INT8`/`INT16` primary keys, and Section 2.6 `IMP_INDEX_VAMANA_ANN = 0x08`.
    * **Multi-Lane Bit-Sliced Frontiers (`TYPE_LANE_FRONTIER = 0x10`, `0xC0`..`0xC9`) & Embedded Vamana ANN (`0xCA`..`0xCB`)**: 8/16/32/64-bit bit-sliced multi-lane execution, counterfactual edge trip masks, delta-frontier fixpoint tracking, `BQ1`/`SQ8`/`FP16` quantized routing, and exact SIMD reranking across C++, Java, Rust, and OCaml.
    * **Kleene 3VL, 54-Function CEL & Compiler Parity**: Full Kleene 3-valued logic, `VmCelEvaluator` / `kleisli_json_runner`, NaN/signed-zero/nullability parity, and `ImpK` / `ImpLog` / `CypherCompiler` lowering for multi-lane and vector ANN queries.
    * **Unified `impulse-cli`, Security & Compatibility**: Consolidated `impulse-cli` inside `impulse-graph-core`, eliminated `thrift` (`CVE-2026-43868`) via Arrow/Parquet `60.1.0`, updated `jackson-*` to `2.18.11`, restored JDK 21 LTS FFM compatibility alongside JDK 22+/25 LTS, and hardened parsers/VM with ASan/UBSan/TSan, libFuzzer, and Jazzer.

!!! info "October 2026 — Unified Documentation Portal & API References"
    * **Documentation Website (`www.impulsegraph.org`)**: Overhauled the documentation portal (currently **85% complete**), integrating [Data-Oriented Design](concepts/data-oriented-design.md) guides, [Aggregated Java Javadocs](/javadoc/index.html), and the [C-ABI Kernel & VM Reference](reference/c-abi.md).
    * **Pure Read-Only Engine Architecture Finalized**: Core execution kernels (`impulse-graph-java` and `impulse-graph-core`) focus 100% on read-only, lock-free vector traversals over immutable `.imps` binary snapshots.
    * **Java `MethodHandle` Combinator JIT & Lua-Inspired VM**: Completed `ImpulseMethodHandleCompiler` and `ShaderCompiler` pipeline fusion in the Pure Java engine alongside four-way polyglot VM parity.

---

## Subsystem Readiness Matrix

| Subsystem / Repository | Status | Readiness | Notes |
| :--- | :--- | :--- | :--- |
| **[Binary Snapshot Format (`.imps`)](reference/spec/format-specification.md)** | Frozen (`v0.10.0`) | [=100% "100%"] | Format `v0.10.0` (`tc01`–`tc38` vectors) and Section 2.6 `IMP_INDEX_VAMANA_ANN` (`0x08`) |
| **[Four-Way Polyglot VM Parity](contributing/polyglot-validation.md)** | Passing | [=100% "100%"] | Bitwise consensus across C++ (`-O3`/`-O0`), Java 25, and OCaml (`166/166` opcodes, `531` `.impas` vectors via `ICTX` v1) |
| **[Pure Java Engine (`impulse-graph-java`)](reference/java-api.md)** | `v0.10.0` Live | [=95% "95%"] | Dual-target JDK 21 LTS & JDK 22+/25 LTS, FFM off-heap engine, `MethodHandle` JIT, Multi-Lane & Vamana ANN |
| **[Native C++20 / C-ABI Engine (`impulse-graph-core`)](reference/c-abi.md)** | `v0.10.0` Live | [=95% "95%"] | C++20 & C-ABI kernel (`libimpulse_graph`), Highway SIMD, OpenMP, `TYPE_LANE_FRONTIER` & `0xC0`..`0xCB` |
| **[Multi-Frontend Compiler (`ImpScheme` / `openCypher` / `CEL`)](concepts/compiler-architecture.md)** | `v0.10.0` Tagged | [=90% "90%"] | Two-stage optimizer (logical AST rewriting + cost-based physical selection), Multi-Lane width selection & SQLite-style prepared statements |
| **[Documentation Portal (`impulse-website`)](index.md)** | Active | [=85% "85%"] | Core guides, specifications, Javadocs & C-ABI references live; remaining tutorials in progress |
| **[Developer CLI Suite (`impulse-cli`)](reference/cli.md)** | `v0.10.0` Tagged | [=90% "90%"] | Consolidated in `impulse-graph-core/impulse-cli`: `build`, `inspect`, `validate`, `compile`, `assemble`, `disassemble`, `run`, `index`, `sample`, `transmute`, `attach-embeddings`, `bench-vector`, `opt` |
| **[Polyglot Language SDKs](software-modules.md)** | Beta | [=80% "80%"] | Python (`pybind11` / NumPy / PyTorch), Rust (`impulse-rust`), Go (`CGo`), .NET/C# (`P/Invoke`), Node.js (`N-API`) |

---

## Target Package Registry Distribution Status

!!! note "Registry & Pre-v1.0 Distribution"
    **Maven Central**, **PyPI**, and **crates.io** are live for `v0.10.0`. Pre-built CLI/SDK binaries (`.deb`, `.rpm`, `.pkg`, `.msi`, `.tar.gz`) are available on GitHub Releases, while **NuGet** and **npm** registry publishing is staged for `v1.0`.

| Package Manager / Registry | Target Ecosystem | Package Coordinates / Artifacts | Status | Readiness | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **[Maven Central](reference/packages.md)** | Java 25 / Kotlin / Scala 3 / Clojure | `org.impulsegraph:impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`, `impulse-builder`, `impulse-spec`, `impulse-kotlin`, `impulse-scala_3`, `impulse-clojure` | Live (`0.10.0`) | [=100% "100%"] | Signed & published on Maven Central with `-sources.jar` and `-javadoc.jar` |
| **[PyPI](reference/python-api.md)** | Python (`>= 3.9`) | `impulse-graph` (`manylinux`, `macosx_11_0_arm64`, `win_amd64` wheels & `sdist`) | Live (`0.10.0`) | [=100% "100%"] | Static C++20 `pybind11` wheels with zero-copy NumPy, SciPy CSR, and PyTorch `mmap` tensor views |
| **[Crates.io](reference/rust-api.md)** | Rust (`2021` Edition) | `impulse-graph` | Live (`0.10.0`) | [=100% "100%"] | Self-contained Rust crate (`cargo add impulse-graph@0.10.0`) with bundled C++20/Highway sources |
| **[NuGet.org](reference/polyglot-sdks.md)** | .NET 8+ / C# / F# | `ImpulseGraph`, `ImpulseGraph.Native`, `ImpulseGraph.FSharp` | Beta | [=80% "80%"] | Managed P/Invoke SDK + cross-platform native runtime packs (staged for `v1.0`) |
| **[npm](reference/polyglot-sdks.md)** | Node.js / TypeScript / Bun | `impulse-graph` | Beta | [=80% "80%"] | N-API native addon + TypeScript `.d.ts` definitions (staged for `v1.0`) |
| **[Go Modules](reference/polyglot-sdks.md)** | Go (`1.22+` CGo) | `github.com/impulse-graph/impulse-graph/go` | Beta | [=80% "80%"] | CGo bindings linked against `libimpulse_graph_static.a` |
| **[Vcpkg / Conan / Homebrew](reference/c-abi.md)** | C / C++20 & macOS/Linux CLI | `impulse-graph` (`libimpulse_graph_static.a`, `.dylib`, `.so`, `.dll`, `.deb`, `.rpm`, `.pkg`, `.msi`) | In Progress | [=75% "75%"] | CMake install targets & static packaging ready; registry port manifests staged for `v1.0` |
| **[GHCR / Docker](reference/packages.md)** | Containers / Kubernetes | `ghcr.io/impulse-graph/impulse-tools`, `impulse-platform-server` | In Progress | [=75% "75%"] | Static `musl-libc` Alpine/scratch CLI & platform server images |

---

## Goals Before `v1.0` Release

- [x] Finalize `.imps` Binary Snapshot Format (`v0.10.0`)
- [x] Achieve four-way VM parity across C++, Java 25, and OCaml ([Polyglot Validation](contributing/polyglot-validation.md))
- [x] Implement 64-register VM (`R0`..`R63`) and Java 25 `MethodHandle` JIT compilation
- [x] Focus core kernels on lock-free, read-only `.imps` traversal
- [x] Launch documentation site (`www.impulsegraph.org`) with Javadocs and C-ABI references
- [x] Release `v0.10.0` across all core repos (Multi-Lane `0xC0`..`0xC9`, Vamana ANN `0x08` / `0xCA`..`0xCB`, Kleene 3VL & 54-func CEL)
- [x] Publish `0.10.0` packages to Maven Central, PyPI, and crates.io
- [ ] Complete remaining documentation (cookbooks, operational runbooks, and showcase deep dives)
- [ ] Publish NuGet and npm packages and finalize `v1.0` release pipelines
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
