# Impulse Graph Engine: Software Modules & Dual-Engine Architecture

This document defines the logical software module organization, dual-engine architecture (**Pure Java 25** and **Native C++20 / C-ABI**), polyglot workspace, and repository sitemap for **Impulse Graph Engine**.

---

## 1. Dual-Engine Architecture over `.imps` Binary Snapshots

Impulse Graph centers on the **Impulse Binary Snapshot Format (`.imps`)**—an immutable, page-aligned, 128-byte hardware-aligned binary file format—and provides **two equivalent, first-class execution engines**:

1. **Pure Java 25 Engine (`impulse-graph-java`)**:
   - A 100% pure Java 25 implementation built on the Java 25 Foreign Function & Memory (FFM) API (`MemorySegment`, `Arena`), Vector API (`jdk.incubator.vector`), and `MethodHandle` C2 JIT combinators.
   - **Enterprise-Ready**: Strictly **zero third-party runtime dependencies**, **zero JNI / native library dependencies**, and **zero GC pauses** (all CSR/CSC topologies, SoA attributes, bitsets, and the 640-byte `ImpulseVM` register frame live off-heap).
2. **Native C++20 & C-ABI Engine (`impulse-graph-core`)**:
   - A zero-dependency C++20 and C-ABI kernel (`libimpulse_graph`, `impulse_graph.h`, `impulse_vm.h`) with Highway SIMD and OpenMP parallelization.
   - Powers native C/C++ applications and the polyglot FFI SDKs (`impulse-rust`, `impulse-python`, `impulse-go`, `impulse-dotnet`, `impulse-node`).

Both engines implement the exact same `ImpulseVM` register architecture (`R0`..`R63`) and `impOps` bytecode instruction set over the same `.imps` binary files, validated to produce 100% bitwise-identical outputs.

---

## 2. Core Logical Software Modules & Classes

### 2.1 `ImpulseGraphSnapshot` (Read-Only Binary Snapshot Interface)
* **Purpose**: Provides a read-only, zero-copy interface for querying immutable graph snapshots.
* **Underlying Storage**: Backed directly by memory-mapped (`mmap`) off-heap files conforming to the [Impulse Binary Snapshot Specification](reference/spec/format-specification.md).
* **Guarantees**: Thread-safe, lock-free, zero-allocation reads; 128-byte SIMD / GPU hardware alignment and 4KB page boundary alignment.

### 2.2 `ImpulseVM` (Register-Based Bytecode Virtual Machine)
* **Purpose**: Executes `impOps` bytecode queries over immutable `ImpulseGraphSnapshot` instances.
* **Opcode Instruction Set (`impOps`)**: Formal opcode ISA defining instruction contracts for traversals (`OP_CSR_WALK`, `OP_CSC_WALK`), GraphBLAS matrix-vector math (`OP_MXV`, `OP_VXM`), connected components (`OP_CC_AFFOREST`), and SIMD bitset filtering (`OP_COLLECT_BITSET`).
* **Dual-Engine Execution**: Pure Java 25 FFM `MethodHandle` JIT-inlined interpreter (`ImpulseVmInterpreter.java`) and direct-threaded C++20 runtime (`impulse_vm.cpp`) with OpenMP parallelization.

### 2.3 `ImpulseGraphQuery` & `ImpulseStatement` (Query AST, Compiler & Prepared Statements)
* **Purpose**: Compiles domain-bound fluent traversals, `openCypher` queries, `Google CEL` filters, `ImpLog` Datalog rules, and `ImpK` GraphBLAS programs into `impOps` bytecode executed on `ImpulseVM`.

### 2.4 `SnapshotBuilder` & `SnapshotWriter` (Single-Pass Streaming Generator)
* **Purpose**: Builds immutable `.imps` binary snapshots direct-to-disk or cloud object storage (S3/GCS).
* **Memory & Storage Strategy**:
  - **Single-Pass Streaming Write**: Streams binary snapshot sections (`Header`, `Shared String Table`, `CSR/CSC Topology`, `Key Catalogs`, `SoA Attributes`, `Secondary Indices`) sequentially in page-aligned blocks while computing SHA-256 payload checksums.
  - **Bounded Memory Footprint**: Bounds physical RAM usage to $O(\text{chunk})$ rather than $O(|V| + |E|)$, enabling generation of multi-hundred-gigabyte or terabyte-scale (TB+) snapshots without Out-Of-Memory (OOM) failures.

---

## 3. Repository Organization

### 3.1 Pure Java 25 Workspace (`impulse-graph-java`)
```text
impulse-graph-java/
├── impulse-spec/               # Binary Snapshot Format FFM memory layouts & opcode constants
├── impulse-api/                # Public interfaces (ImpulseGraphSnapshot, DomainView, Traversal, ImpulseStatement)
├── impulse-storage/            # Zero-dependency Java 25 FFM CSR/CSC loader, DeltaLayer & Secondary Indices
├── impulse-vm/                 # Pure Java 25 ImpulseVM interpreter, MethodHandle JIT & bytecode emitter
├── impulse-compiler/           # Multi-pass ImpScheme, openCypher & CEL optimizing compiler
└── impulse-builder/            # Direct-to-disk streaming .imps snapshot builder
```

### 3.2 Native C++20 & Polyglot FFI Workspace (`impulse-graph-core`)
```text
impulse-graph-core/
├── impulse-cpp/                # C++20 Native Engine Kernel, C-ABI Headers & ImpulseVM (libimpulse_graph)
├── impulse-rust/               # Zero-dependency Rust Engine Crate (impulse-graph)
├── impulse-python/             # Python Bindings & PyTorch Zero-Copy mmap Tensors
├── impulse-dotnet/             # .NET 8+ P/Invoke Managed API (ImpulseGraph)
├── impulse-go/                 # Go CGo Zero-Copy C-ABI Bindings
└── impulse-node/               # Node.js / TypeScript N-API Native Bindings
```

---

## 4. Developer Utilities & ImpVM Suite (`impulse-graph-tooling`)

Developer inspection, compilation, and layout optimization utilities are consolidated into `impulse-graph-tooling`:

* **`impulse compiler assemble` / `disassemble`**: Assembles `.impas` text into `.impb` binary bytecode and disassembles `.impb` back to annotated `.impas`.
* **`impulse compiler compile`**: Compiles DSL scripts (`.impscm`, `.impk`, `.implog`) into `.impas` or `.impb`.
* **`impulse run`**: Executes compiled bytecode or source scripts against an `.imps` binary snapshot.
* **`impulse snapshot build`**: Streams CSV/TSV/Parquet dataset manifests into `.imps` binary snapshots.
* **`impulse snapshot inspect` & `validate` & `optimize`**: Zero-copy header inspection, SHA-256 and 128-byte alignment validation, Reverse Cuthill-McKee (RCM) reordering, and CSC generation.

---

## 5. GitHub Organization Repository Sitemap

| Repository | Role & Description |
| :--- | :--- |
| **`impulse-graph-java`** | **Pure Java 25 Engine**. Zero-dependency Java 25 FFM off-heap snapshot engine, `ImpulseVM` JIT interpreter, multi-pass compiler, and streaming `SnapshotBuilder`. |
| **`impulse-graph-core`** | **C++20 / C-ABI Kernel & FFI Bindings**. C++20 zero-copy memory-mapped kernel, Rust engine crate (`impulse-rust`), and polyglot FFI SDKs (Python, C#, Go, Node.js). |
| **`impulse-graph-spec`** | **Normative Specifications & Test Vectors**. Canonical `.imps` binary format, `ImpulseVM` ISA, `.impas` assembly specification, and four-way polyglot compliance vectors. |
| **`impulse-graph-tooling`** | **Developer CLI Suite**. `impulse build`, `impulse compile`, `impulse run`, `impulse snapshot inspect`, `validate`, and `optimize`. |
| **`impulse-benchmarks`** | **Performance & Macro Benchmark Suite**. Reproducible JMH, Google Benchmark, and Python benchmark harnesses. |
| **`impulse-website`** | **Documentation Portal**. Official documentation website (`docs.impulsegraph.io`). |
| **`impulse-platform`** | **Enterprise Cloud Infrastructure**. Spring Boot gRPC server, Kafka WAL ingestion, GCS/S3 snapshot sync, and RocksDB persistence. |
| **`impulse-powergrid`** | **Showcase**: Electrical power grid stability engine, CIM XML compiler, and parallel N-1 contingency simulator. |
| **`impulse-gnn`** | **Showcase**: Python PyTorch / PyG zero-copy `mmap` tensor integration and SIMD neighborhood sampler. |
| **`impulse-authz`** | **Showcase**: Relationship-Based Access Control (ReBAC / Zanzibar) authorization server with live CDC sync. |

---

## 6. Package Registry Distribution Matrix

| Registry | Ecosystem / Language | Published Artifact Name | Description |
| :--- | :--- | :--- | :--- |
| **Maven Central** | Java 25 (JVM) | `org.impulsegraph:impulse-api`<br>`org.impulsegraph:impulse-storage`<br>`org.impulsegraph:impulse-vm`<br>`org.impulsegraph:impulse-compiler`<br>`org.impulsegraph:impulse-builder`<br>`org.impulsegraph:impulse-spec` | Pure Java 25 FFM engine modules (zero runtime dependencies, zero GC pauses). |
| **Crates.io** | Rust | `impulse-graph` / `impulse-tools` | Zero-dependency Rust engine crate & CLI tools. |
| **PyPI** | Python | `impulse-graph` | Pre-compiled wheels with NumPy & PyTorch zero-copy `mmap` tensors. |
| **NuGet.org** | .NET (C# / F#) | `ImpulseGraph` / `ImpulseGraph.Native` | Managed .NET API and cross-platform native C-ABI binaries. |
| **npm** | Node.js / Bun | `impulse-graph` | TypeScript definitions & N-API native bindings. |
| **Vcpkg / Conan** | C / C++20 | `impulse-graph` | C-ABI headers (`impulse_graph.h`, `impulse_vm.h`) & static/shared libraries. |
| **GHCR** | Containers | `ghcr.io/impulse-graph/impulse-tools:latest`<br>`ghcr.io/impulse-graph/impulse-platform-server:latest` | Standalone CLI toolchain and enterprise platform server containers. |
