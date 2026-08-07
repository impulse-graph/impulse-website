# Impulse Graph Engine: Software Modules & Repository Architecture

This document defines the logical software module organization, class boundaries, polyglot workspace, and repository sitemap for **Impulse Graph Engine**.

> **Naming Notice**: The project and codebase are strictly named **Impulse Graph Engine** (`impulse-graph`). Legacy terminology (`abac-engine`, `impulse-engine`) is retired.

---

## 1. Core Logical Software Modules & Classes

### 1.1 `ImpulseGraphSnapshot` (Read-Only Binary Snapshot Interface)
* **Purpose**: Provides a read-only, zero-copy interface for querying immutable graph snapshots.
* **Underlying Storage**: Backed directly by memory-mapped (`mmap`) off-heap files conforming to the [C-ABI Binary Snapshot Specification v0.9.0](reference/spec/v0.9.0.md).
* **Guarantees**: Thread-safe, lock-free, zero-allocation reads; 128-byte SIMD / GPU hardware alignment and 4KB page boundary aligned.

### 1.2 `ImpulseVM` (High-Performance Bytecode Virtual Machine)
* **Purpose**: Executes `impOps` bytecode queries over immutable `ImpulseGraphSnapshot` instances.
* **Opcode Instruction Set (`impOps`)**: Formal opcode ISA (`0x01`..`0x6A`) defining instruction contracts for traversals (`OP_CSR_WALK`, `OP_CSC_WALK`), GraphBLAS matrix-vector math (`OP_MXV`, `OP_VXM`), connected components (`OP_CC_AFFOREST`), and SIMD bitset filtering (`OP_COLLECT_BITSET`).
* **Polyglot Execution**: Direct-threaded C++ runtime (`impulse_vm.cpp`) with OpenMP parallelization & Java 25 FFM `MethodHandle` C2 JIT-inlined interpreter (`ImpulseVmInterpreter.java`).

### 1.3 `ImpulseGraphQuery` (Immutable Query AST & VM Compiler)
* **Purpose**: Strongly-typed, serializable representation of a graph query (e.g. reachability, transitive closure, set intersection, neighborhood extraction, bitwise attribute filtering).
* **Read-Only**: Immutable intent definition, completely decoupled from execution logic. Compiles directly into `impOps` bytecode programs evaluated by `ImpulseVM`.

### 1.4 `SnapshotBuilder` & `SnapshotWriter` (Single-Pass S3 Streaming Generator)
* **Purpose**: Builds brand-new immutable binary snapshots direct-to-disk or cloud object storage (S3/GCS).
* **Memory & Storage Strategy**:
  - **Single-Pass S3 Streaming Write**: Streams binary snapshot sections (`Header`, `Section 2 Shared String Table`, `CSR Topology`, `ID Mappings`, `DTO Payloads`) sequentially to cloud storage in page-aligned blocks while computing SHA-256 payload checksums.
  - **Scale & Memory Footprint**: Bounds physical RAM usage to $O(\text{chunk})$ rather than $O(|V| + |E|)$, enabling generation of multi-hundred-gigabyte or terabyte-scale (TB+) snapshots without Out-Of-Memory (OOM) risk.

---

## 2. Polyglot Architecture & Repository Organization

The core engine is structured as a **Unified Polyglot Workspace** in the `impulse-graph-core` repository:

```
impulse-graph-core/
├── impulse-cpp/                # C++20 Native Engine Kernel & ImpulseVM (CMake & libimpulse_graph)
├── impulse-rust/               # Rust Native Engine Kernel & Crate
├── impulse-python/             # Python Bindings & PyTorch Zero-Copy mmap Tensors
├── impulse-csharp/             # .NET 9 P/Invoke Managed API
├── impulse-golang/             # Go cgo Zero-Copy C-ABI bindings
└── impulse-nodejs/             # Node.js N-API Native Bindings
```

---

## 3. Developer Utilities & ImpVM Suite (`impulse-graph-tooling`)

Developer inspection, compilation, and layout optimization utilities are consolidated into `impulse-graph-tooling`:

```
+------------------+       Single-Pass        +--------------------+
| Live Ingestion / | -----------------------> | Impulse Binary     |
| Parquet Stream   |       S3 Stream Write    | Snapshot (.imps)   |
+------------------+                          +--------------------+
                                                        │
                                                        ▼
                                              +--------------------+
                                              | impulse-tooling    | (C++ / Rust Suite)
                                              | • impulse assemble | (Compile text .imp)
                                              | • impulse disasm   | (Disassemble .bin)
                                              | • impulse run      | (Execute VM query)
                                              | • impulse compile  | (Parquet/CSV stream)
                                              | • impulse inspect  | (Zero-copy header)
                                              | • impulse opt      | (RCM / SIMD reorder)
                                              +--------------------+
                                                        │
                                                        ▼
+------------------+        Zero-Copy         +--------------------+
| High-Speed Pods  | <----------------------- | Optimized Binary   |
| (Java/C++/Rust)  |        mmap Read         | Snapshot v0.9.0    |
+------------------+                          +--------------------+
```

#### What `impulse-graph-tooling` provides:
* **`impulse assemble`**: Text assembly compiler building bytecode scripts into `.impb` binary VM scripts.
* **`impulse disassemble`**: Bytecode disassembler converting binary VM scripts into human-readable `.impas` assembly.
* **`impulse run`**: High-speed command-line runner executing `impOps` query scripts directly against `.imps` snapshot targets.
* **`impulse compile`**: CSV/TSV/Parquet streaming snapshot compiler conforming to Spec v0.9.0.
* **`impulse inspect` & `impulse opt`**: Zero-copy header inspection, SHA-256 integrity validation, RCM reordering, and layout optimization.

---

## 4. Ecosystem Showcase Repositories

Four dedicated **Showcase Repositories** highlight real-world use cases across key industries:

```
                               ┌───────────────────────────────────┐
                               │     impulse-graph (Core Spec)     │
                               └─────────────────┬─────────────────┘
                                                 │
      ┌──────────────────────┬───────────────────┼───────────────────┬──────────────────────┐
      ▼                      ▼                   ▼                   ▼                      ▼
┌───────────┐          ┌───────────┐       ┌───────────┐       ┌───────────┐          ┌───────────┐
│ impulse-  │          │ impulse-  │       │ impulse-  │       │ impulse-  │          │ impulse-  │
│ powergrid │          │    gnn    │       │   authz   │       │  fintech  │          │ platform  │
└───────────┘          └───────────┘       └───────────┘       └───────────┘          └───────────┘
```

### 4.1 `impulse-powergrid` — Critical Infrastructure & Grid Stability
* **Domain**: Real-time electrical power systems engineering, Balancing Authority monitoring, and grid reliability.
* **Key Features**: MATPOWER / CIM XML converter to C-ABI `.imps` v0.9.0 snapshots, ARM NEON / AVX2 SIMD connected-component island detector, 1,000,000+ N-1 / N-2 contingency simulator (361x faster than PYPOWER), and inter-BA tie-line analyzer.

### 4.2 `impulse-gnn` — Python PyTorch AI/ML Graph Acceleration
* **Domain**: High-performance Graph Neural Network (GNN) training and LLM knowledge graph embeddings.
* **Key Features**: Zero-copy PyTorch `torch.sparse_csr_tensor` `mmap` integration and native SIMD C++ neighborhood sampler (`torch.ops.impulse.sample_neighbors`).

### 4.3 `impulse-authz` — Enterprise Fine-Grained Authorization (ReBAC / Zanzibar)
* **Domain**: Real-time Relationship-Based Access Control (ReBAC) & ABAC for SaaS and cloud platforms.
* **Key Features**: Sub-microsecond permission graph evaluation (5,000,000+ checks/sec/pod) with live Debezium CDC streaming sync.

### 4.4 `impulse-fintech` — Real-Time Anti-Money Laundering (AML) & Fraud Detection
* **Domain**: Financial crime detection, synthetic identity detection, and transaction flow analysis.
* **Key Features**: Real-time circular money laundering loop detection (A -> B -> C -> A) and high-speed transaction graph pattern matching.

---

## 5. GitHub Organization Master Repository Sitemap

The following **11 repositories** form the complete **Impulse Graph Ecosystem** in the GitHub organization:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                 GitHub Organization Repository Sitemap                   │
├──────────────────────────────────────────────────────────────────────────┤
│ CORE KERNEL & SPECIFICATION                                              │
│  1. impulse-graph-core --> Core polyglot kernel (C++, Rust, Python, Go)  │
│  2. impulse-graph-java --> Standalone Java 25 FFM / Vector API VM        │
│  3. impulse-graph-spec --> Normative v0.9.0 specification & test vectors │
│  4. impulse-graph-tooling --> Assembler, disassembler, compile, inspect  │
│  5. impulse-benchmarks --> Reproducible micro & macro benchmark suite    │
│                                                                          │
│ ENTERPRISE CLOUD PLATFORM                                                │
│  6. impulse-platform   --> Spring Boot, K8s, GCS/S3, Kafka, RocksDB store │
│                                                                          │
│ INDUSTRY SHOWCASE REPOS                                                  │
│  7. impulse-powergrid  --> Electrical grid stability & N-1 simulator     │
│  8. impulse-gnn        --> PyTorch / PyG zero-copy GNN acceleration      │
│  9. impulse-authz      --> ReBAC / Zanzibar fine-grained authorization  │
│ 10. impulse-vm         --> Standalone C++ direct-threaded VM reference    │
│                                                                          │
│ GOVERNANCE & DOCUMENTATION                                               │
│ 11. impulse-website    --> Official documentation site (docs.impulse...)  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Public Package Manager Artifacts & Distribution Matrix

```
┌──────────────────────────────────────────────────────────────────────────┐
│              Public Package Registry Distribution Matrix                 │
├──────────────────────────────────────────────────────────────────────────┤
│ 1. Maven Central (JVM) --> io.impulse.graph:impulse-core / impulse-api   │
│ 2. Crates.io (Rust)    --> cargo install impulse-graph / impulse-tools   │
│ 3. PyPI (Python)       --> pip install impulse-graph                     │
│ 4. NuGet (C# / .NET)   --> dotnet add package ImpulseGraph                │
│ 5. npm (Node.js/Bun)   --> npm install impulse-graph                     │
│ 6. Vcpkg / Conan (C++) --> vcpkg install impulse-graph / libimpulse_graph│
│ 7. GHCR / Docker       --> docker pull ghcr.io/impulse-graph/server      │
└──────────────────────────────────────────────────────────────────────────┘
```

### Complete Artifact Publishing Table

| Registry | Ecosystem / Language | Published Artifact Name | Description & Installation Command |
| :--- | :--- | :--- | :--- |
| **Maven Central** | Java (JVM) | `io.impulse.graph:impulse-spec`<br>`io.impulse.graph:impulse-api`<br>`io.impulse.graph:impulse-core` | Core Java 25 FFM engine (0 dependencies).<br>`<dependency><groupId>io.impulse.graph</groupId><artifactId>impulse-core</artifactId></dependency>` |
| **Crates.io** | Rust | `impulse-graph` | Pure Rust crate & C-ABI FFI bindings (`cargo add impulse-graph`). |
| **Crates.io** | Rust Tools / CLI | `impulse-tools` | Developer CLI & optimizer tool suite (`cargo install impulse-tools`). |
| **PyPI** | Python | `impulse-graph` | Pre-compiled wheels for PyTorch `mmap` zero-copy tensors.<br>`pip install impulse-graph` |
| **NuGet.org** | .NET (C#) | `ImpulseGraph` | Managed .NET 9 API wrapper (`dotnet add package ImpulseGraph`). |
| **npm** | Node.js / Bun / Deno | `impulse-graph` | TypeScript definitions & N-API native bindings.<br>`npm install impulse-graph` |
| **Vcpkg / Conan** | C / C++ | `impulse-graph` | C-ABI header `impulse_graph.h` & `libimpulse_graph.so` / `.dylib` / `.dll`.<br>`vcpkg install impulse-graph` |
| **GitHub Releases** | C / C++ Native Tarballs | `impulse-graph-v0.9.0-linux-x64.tar.gz`<br>`impulse-graph-v0.9.0-darwin-arm64.tar.gz` | Pre-compiled C-ABI shared library tarballs. |
| **GHCR / Docker Hub**| Docker Containers | `ghcr.io/impulse-graph/impulse-platform-server:v0.9.0`<br>`ghcr.io/impulse-graph/impulse-tools:v0.9.0` | Standalone Spring Boot gRPC server & `impulse-opt` optimizer CLI containers. |
