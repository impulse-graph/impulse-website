# Software Modules & Repository Map

Impulse Graph is organized around two independent execution engines that read the same `.imps` binary snapshot format:

1. **Pure Java Engine (`impulse-graph-java`)**: Java 21 LTS / 25 FFM (`MemorySegment`, `Arena`), Vector API (`jdk.incubator.vector`), and `MethodHandle` JIT combinators. No JNI or native wrappers.
2. **Native C++20 / C-ABI Engine (`impulse-graph-core`)**: C++20 kernel (`libimpulse_graph`, `impulse_graph.h`, `impulse_vm.h`) with Highway SIMD and OpenMP. Powers C/C++, Rust (`impulse-rust`), Python, Go, .NET, and Node.js SDKs.

Both engines execute the same `ImpulseVM` register ISA (`R0`..`R63`, `impOps`) and are verified for bitwise parity in [Polyglot Validation & Testing](contributing/polyglot-validation.md).

---

## 1. Core Components

* **`ImpulseGraphSnapshot`**: Read-only, thread-safe interface over a memory-mapped `.imps` file ([Binary Snapshot Spec](reference/spec/format-specification.md)).
* **`ImpulseVM`**: Register-based bytecode VM executing `impOps` instructions (`OP_CSR_WALK`, `OP_CSC_WALK`, `OP_MXV`, `OP_VXM`, `OP_CC_AFFOREST`, `OP_COLLECT_BITSET`).
* **`ImpulseGraphQuery` & `ImpulseStatement`**: Compiles fluent traversals, openCypher, CEL filters, ImpLog, and ImpK into `impOps` bytecode and prepared statements.
* **`SnapshotBuilder` & `SnapshotWriter`**: Single-pass streaming `.imps` writers for local disks and cloud object storage (S3/GCS) with $O(\text{chunk})$ RAM usage.

---

## 2. Repository Workspaces

### Pure Java Engine (`impulse-graph-java`)
```text
impulse-graph-java/
├── impulse-spec/               # Format FFM layouts & opcode constants
├── impulse-api/                # Public interfaces (ImpulseGraphSnapshot, DomainView, ImpulseStatement)
├── impulse-storage/            # FFM CSR/CSC loader & secondary indices
├── impulse-vm/                 # ImpulseVM interpreter, MethodHandle JIT & bytecode emitter
├── impulse-compiler/           # ImpScheme, openCypher & CEL optimizing compiler
├── impulse-builder/            # Streaming .imps snapshot builder
├── impulse-kotlin/             # Kotlin DSL & coroutine extensions
├── impulse-scala/              # Scala 3 DSL extensions
├── impulse-clojure/            # Clojure / S-expression DSL
└── spec/                       # Pinned impulse-graph-spec submodule
```

### Native C++20, CLI & Polyglot Workspace (`impulse-graph-core`)
```text
impulse-graph-core/
├── impulse-cpp/                # C++20 kernel, C-ABI headers & ImpulseVM (libimpulse_graph)
├── impulse-rust/               # Rust crate (impulse-graph)
├── impulse-cli/                # Standalone CLI & compiler suite (impulse / impulse-graph)
├── impulse-python/             # Python bindings (NumPy, SciPy, PyTorch)
├── impulse-dotnet/             # .NET 8+ P/Invoke API (ImpulseGraph)
├── impulse-go/                 # Go CGo bindings
├── impulse-node/               # Node.js / TypeScript N-API bindings
└── spec/                       # Pinned impulse-graph-spec submodule
```

---

## 3. CLI Utilities (`impulse-graph-core/impulse-cli`)

The standalone `impulse` / `impulse-graph` executable provides inspection, compilation, and snapshot optimization commands (see [CLI Reference](reference/cli.md)):

* `impulse compiler assemble` / `disassemble` — `.impas` text ↔ `.impb` binary bytecode.
* `impulse compiler compile` — compiles `.impscm`, `.impk`, and `.implog` into `.impas` or `.impb`.
* `impulse run` — executes bytecode or DSL scripts against an `.imps` snapshot.
* `impulse build` — compiles CSV/TSV/Parquet manifests into `.imps` files.
* `impulse snapshot inspect` / `validate` / `optimize` — header inspection, SHA-256 and alignment checks, Reverse Cuthill-McKee (RCM) reordering, and CSC generation.

---

## 4. Organization Repository Sitemap

| Repository | Role |
| :--- | :--- |
| **`impulse-graph-spec`** | `.imps` binary format, `ImpulseVM` ISA, `.impas` assembly spec, and compliance test vectors (`tc01`–`tc38`, `vm-impas/`). |
| **`impulse-graph-core`** | C++20 / C-ABI kernel (`impulse-cpp`), Rust crate (`impulse-rust`), CLI (`impulse-cli`), and FFI SDKs (Python, Go, .NET, Node.js). |
| **`impulse-graph-java`** | Pure Java 21/25 FFM engine, VM interpreter/JIT, compiler suite, streaming builder, and Kotlin/Scala/Clojure DSLs. |
| **`impulse-ocaml`** | OCaml reference implementation of `ImpulseVM` and `ICTX` v1 hashing used as a parity oracle. |
| **`impulse-verification`** | Four-way parity harness (`four_way_validation.py`), contract fuzzer (`fuzz_vm_contracts.py`), and cross-compiler parity (`cross_compiler_parity.py`). |
| **`impulse-benchmarks`** | Reproducible JMH, Google Benchmark, and Python benchmark harnesses. |
| **`impulse-website`** | Documentation site (`www.impulsegraph.org`). |
| **`impulse-platform`** | Spring Boot gRPC server, Kafka WAL ingestion, GCS/S3 snapshot sync, and RocksDB persistence. |
| **`impulse-powergrid`** | Showcase: power grid stability engine and parallel N-1 contingency simulator over MATPOWER PEGASE cases. |
| **`impulse-gnn`** | Showcase: PyTorch / PyG `mmap` tensor integration and SIMD neighborhood sampler. |
| **`impulse-authz`** | Showcase: Relationship-Based Access Control (ReBAC / Zanzibar) authorization service and benchmarks. |

For live package registry status and coordinates (Maven Central, PyPI, crates.io, GitHub Releases), see [Status & Roadmap](status.md) and [Packages & Distribution](reference/packages.md).
