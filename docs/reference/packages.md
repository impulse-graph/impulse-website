# Package Registry & Distribution

Impulse Graph Engine (`0.9.0`) is distributed across 7 package registries supporting JVM, native, and managed runtimes.

| Ecosystem | Registry | Package / Coordinate | Description |
| :--- | :--- | :--- | :--- |
| **Java / JVM** | Maven Central | `org.impulsegraph:impulse-api:0.9.0` | Public interfaces, `DomainView`, `Traversal`, `ImpulseStatement`, and AST contracts. |
| **Java / JVM** | Maven Central | `org.impulsegraph:impulse-storage:0.9.0` | Zero-dependency Java 21/25 FFM off-heap CSR/CSC snapshot engine. |
| **Java / JVM** | Maven Central | `org.impulsegraph:impulse-vm:0.9.0` | Register-based `ImpulseVM` interpreter, `MethodHandle` JIT, and bytecode emitter. |
| **Java / JVM** | Maven Central | `org.impulsegraph:impulse-compiler:0.9.0` | Multi-pass `ImpScheme`, `openCypher`, and `CEL` optimizing compiler. |
| **Java / JVM** | Maven Central | `org.impulsegraph:impulse-builder:0.9.0` | Direct-to-disk streaming `.imps` v0.9.0 snapshot builder. |
| **Java / JVM** | Maven Central | `org.impulsegraph:impulse-spec:0.9.0` | C-ABI Binary Snapshot Specification v0.9.0 FFM layouts and constants. |
| **Kotlin** | Maven Central | `org.impulsegraph:impulse-kotlin:0.9.0` | Kotlin DSL builders and coroutine extensions. |
| **Scala 3** | Maven Central | `org.impulsegraph:impulse-scala_3:0.9.0` | Scala 3 idiomatic typeclasses and given instances. |
| **Rust** | Crates.io | `impulse-graph` | Zero-dependency Rust engine crate (`mmap` reader, SoA slices, traversal, writer). |
| **Rust** | Crates.io | `impulse-tools` | Developer CLI utilities (`impulse-opt`, `impulse-inspect`). |
| **Python** | PyPI | `impulse-graph` | Native `pybind11` wheels with zero-copy NumPy and PyTorch tensor views. |
| **.NET / C#** | NuGet.org | `ImpulseGraph` / `ImpulseGraph.Native` | Managed .NET 8+ API and cross-platform P/Invoke native binaries. |
| **F#** | NuGet.org | `ImpulseGraph.FSharp` | Idiomatic F# computation expressions and pipeline operators. |
| **Node.js / Bun** | npm | `impulse-graph` | TypeScript definitions (`index.d.ts`) and N-API native bindings. |
| **C / C++** | Vcpkg / Conan | `impulse-graph` | C-ABI headers (`impulse_graph.h`, `impulse_vm.h`), C++20 headers, and `libimpulse_graph_static.a`. |
| **Containers** | GHCR | `ghcr.io/impulse-graph/impulse-tools:latest` | Standalone CLI and compiler toolchain container image. |
| **Containers** | GHCR | `ghcr.io/impulse-graph/impulse-platform-server:latest` | Enterprise gRPC server, Kafka WAL consumer, and S3/GCS snapshot sync. |

## Static Core Engine Linking

All native CLI binaries (`impulse-graph-tooling`), Python wheels, and Node.js N-API add-ons statically embed the core Impulse Graph C-ABI kernel (`libimpulse_graph_static.a` / `.lib`):

* **Linux (`.deb` / `.rpm`)**: Targets `glibc >= 2.28`; portable container tarballs link `musl-libc` (`-static`).
* **macOS (`.pkg` / Homebrew)**: Embeds static engine kernel; links system `libc++.dylib` and `libSystem.B.dylib` (macOS 11.0+).
* **Windows (`.msi` / `.zip`)**: Built with MSVC `/MT` (`LIBCMT.lib`) with zero external redistributable requirements.
