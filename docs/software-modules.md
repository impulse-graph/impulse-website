# Software Modules & Repository Map

Impulse Graph decouples its **normative binary format and bytecode specification** (`impulse-graph-spec`) from **independent execution runtimes** that evaluate the same `.imps` snapshot files and 64-register `impOps` ISA:

1. **Normative Specification & Test Vectors (`impulse-graph-spec`)**: Layer 0 C-ABI `.imps` binary layout, `.imps.schema.yaml` contract rules, `impOps` opcode catalog, and `.impas` compliance vectors (`tc01`–`tc38`, `vm-impas/`). Zero downstream dependencies.
2. **Pure JVM Runtime (`impulse-graph-java`)**: Java 21 LTS / 25 FFM (`MemorySegment`, `Arena`), Vector API (`jdk.incubator.vector`), and `MethodHandle` JIT combinators—plus Kotlin, Scala 3, and Clojure DSLs. Zero JNI and zero third-party runtime dependencies in the core engine.
3. **Native C++20 / C-ABI Runtime (`impulse-graph-core`)**: C++20 kernel (`libimpulse_graph`, `impulse_graph.h`, `impulse_vm.h`) with Highway SIMD and OpenMP. Powers C/C++, Rust (`impulse-rust`), Python, Go, .NET (P/Invoke), and Node.js SDKs.
4. **Formal Reference Oracle (`impulse-ocaml`)**: Pure functional OCaml implementation of `ImpulseVM` and `ICTX` v1 deterministic state hashing.

All runtimes execute the same `ImpulseVM` register ISA (`R0`..`R63`, `impOps`) and are verified for bitwise parity in [Polyglot Validation & Testing](contributing/polyglot-validation.md). Because `.imps` and `impOps` contain no engine-specific object headers, future standalone runtimes (such as pure managed `.NET` or `WebAssembly`) can implement the specification directly.

---

## 1. Core Components

* **`ImpulseGraphSnapshot`**: Read-only, thread-safe interface over a memory-mapped `.imps` file ([Binary Snapshot Spec](reference/spec/format-specification.md)).
* **`ImpulseVM`**: Register-based bytecode VM executing `impOps` instructions (`OP_CSR_WALK`, `OP_CSC_WALK`, `OP_MXV`, `OP_VXM`, `OP_CC_AFFOREST`, `OP_COLLECT_BITSET`).
* **`ImpulseGraphQuery` & `ImpulseStatement`**: Compiles fluent traversals, openCypher, CEL filters, ImpLog, and ImpK into `impOps` bytecode and prepared statements.
* **`SnapshotBuilder` & `SnapshotWriter`**: Single-pass streaming `.imps` writers for local disks and cloud object storage (S3/GCS) with $O(\text{chunk})$ RAM usage.

---

## 2. Repository Workspaces

### Pure JVM Engine & Tooling (`impulse-graph-java`)
```text
impulse-graph-java/
├── impulse-bom/                # Bill of Materials POM aligning all org.impulsegraph versions (v0.11)
├── impulse-spec/               # Format FFM layouts & opcode constants
├── impulse-api/                # Public interfaces (ImpulseGraphSnapshot, DomainView, ImpulseStatement)
├── impulse-storage/            # FFM CSR/CSC loader, secondary indices & lifecycle managers
├── impulse-vm/                 # ImpulseVM interpreter, MethodHandle JIT & bytecode emitter
├── impulse-compiler/           # ImpScheme, openCypher & CEL optimizing compiler
├── impulse-builder/            # Streaming .imps snapshot builder
├── impulse-codegen/            # AOT Java domain/traversal code generator from .imps.schema.yaml (v0.11)
├── impulse-maven-plugin/       # Maven build plugin for schema validation & AOT codegen (v0.11)
├── impulse-gradle-plugin/      # Gradle build plugin for schema validation & AOT codegen
├── impulse-cli/                # Pure-Java CLI ('impulse-j') for JVM-only environments (v0.11)
├── impulse-kotlin/             # Kotlin DSL & coroutine extensions
├── impulse-scala/              # Scala 3 DSL extensions
├── impulse-clojure/            # Clojure / S-expression DSL
└── spec/                       # Pinned impulse-graph-spec submodule
```
*(See the [Java & JVM Ecosystem Hub](ecosystems/java/index.md), [Maven & Build Tooling](ecosystems/java/maven-and-build-tooling.md), and [AOT Code Generation](ecosystems/java/aot-codegen.md).)*

### Native C++20, CLI & Polyglot Workspace (`impulse-graph-core`)
```text
impulse-graph-core/
├── impulse-cpp/                # C++20 kernel, C-ABI headers & ImpulseVM (libimpulse_graph)
├── impulse-rust/               # Rust crate (impulse-graph)
├── impulse-cli/                # Standalone native CLI & compiler suite (impulse / impulse-graph)
├── impulse-python/             # Python bindings (NumPy, SciPy, PyTorch)
├── impulse-dotnet/             # .NET 8+ P/Invoke API (ImpulseGraph)
├── impulse-go/                 # Go CGo bindings
├── impulse-node/               # Node.js / TypeScript N-API bindings
└── spec/                       # Pinned impulse-graph-spec submodule
```
*(See the [Python & PyTorch Hub](ecosystems/python/index.md) and [Native, Rust & Polyglot Hub](ecosystems/native/index.md).)*

---

## 3. Developer CLI Toolchains (`impulse` & `impulse-j`)

Impulse Graph provides two CLI distributions that share command parity (verified via `cli_side_by_side_parity.py`):

* **Native CLI (`impulse-graph` / `impulse` in `impulse-graph-core/impulse-cli`)**: Zero-JVM native executable for Python, C/C++, Rust, data engineering, and container pipelines (see [Native CLI Reference](ecosystems/native/cli-reference.md) and [CLI Reference](reference/cli.md)).
* **Pure-Java CLI (`impulse-j` in `impulse-graph-java/impulse-cli`)**: 100% JVM CLI for enterprise Java environments where native binaries are restricted (see [Pure-Java CLI (`impulse-j`)](ecosystems/java/cli-impulse-j.md)).

Core subcommands include:

* `compiler assemble` / `disassemble` — `.impas` text ↔ `.impb` binary bytecode.
* `compiler compile` — compiles `.impscm`, `.impk`, and `.implog` into `.impas` or `.impb`.
* `run` — executes bytecode or DSL scripts against an `.imps` snapshot.
* `build` — compiles CSV/TSV/Parquet manifests and `.imps.schema.yaml` contracts into `.imps` files.
* `snapshot inspect` / `validate` / `optimize` — header inspection, SHA-256 and 128-byte alignment checks, Reverse Cuthill-McKee (RCM) reordering, and CSC generation.

---

## 4. Organization Repository Sitemap

| Repository | Role |
| :--- | :--- |
| **`impulse-graph-spec`** | Layer 0 `.imps` binary format, `.imps.schema.yaml` spec, `ImpulseVM` ISA, `.impas` assembly spec, and compliance test vectors (`tc01`–`tc38`, `vm-impas/`). |
| **`impulse-graph-core`** | C++20 / C-ABI kernel (`impulse-cpp`), Rust crate (`impulse-rust`), native CLI (`impulse-cli`), and FFI SDKs (Python, Go, .NET, Node.js). |
| **`impulse-graph-java`** | Pure Java 21/25 FFM engine, VM interpreter/JIT, compiler suite, streaming builder, `impulse-bom`, AOT `impulse-codegen`, `impulse-maven-plugin`, `impulse-j` CLI, and Kotlin/Scala/Clojure DSLs. |
| **`impulse-ocaml`** | OCaml reference implementation of `ImpulseVM` and `ICTX` v1 hashing used as a formal parity oracle. |
| **`impulse-verification`** | Four-way VM parity harness (`four_way_validation.py`), side-by-side CLI parity suite (`cli_side_by_side_parity.py`), contract fuzzer (`fuzz_vm_contracts.py`), and cross-compiler parity (`cross_compiler_parity.py`). |
| **`impulse-benchmarks`** | Reproducible JMH, Google Benchmark, and Python benchmark harnesses. |
| **`impulse-website`** | Documentation site (`www.impulsegraph.org`). |
| **`impulse-platform`** | Spring Boot gRPC server, Kafka WAL ingestion, GCS/S3 snapshot sync, and RocksDB persistence. |
| **`impulse-powergrid`** | Showcase: power grid stability engine and parallel N-1 contingency simulator over MATPOWER PEGASE cases. |
| **`impulse-gnn`** | Showcase: PyTorch / PyG `mmap` tensor integration and SIMD neighborhood sampler. |
| **`impulse-authz`** | Showcase: Relationship-Based Access Control (ReBAC / Zanzibar) authorization service and benchmarks. |

For live package registry status and coordinates (Maven Central, PyPI, crates.io, GitHub Releases), see [Status & Roadmap](status.md) and [Packages & Distribution](reference/packages.md).
