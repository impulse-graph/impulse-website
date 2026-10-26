# Packages & Distribution

Impulse Graph Engine is distributed across **8 package registries** supporting JVM, native, and managed runtimes.

| Ecosystem | Registry | Package / Coordinate | Description |
| :--- | :--- | :--- | :--- |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-api` | Public interfaces (`ImpulseGraphSnapshot`, `DomainView`, `Traversal`, `ImpulseStatement`). |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-storage` | Zero-dependency Java 25 FFM off-heap CSR/CSC snapshot engine and `SnapshotSwapManager`. |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-vm` | Register-based `ImpulseVM` interpreter, `MethodHandle` JIT, and bytecode emitter. |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-compiler` | Multi-pass `ImpScheme`, `openCypher`, and `CEL` optimizing compiler. |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-builder` | Direct-to-disk streaming `.imps` snapshot builder. |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-spec` | Binary Snapshot Format FFM memory layouts and protocol constants. |
| **Kotlin / Scala 3** | Maven Central | `org.impulsegraph:impulse-kotlin`, `impulse-scala_3` | Idiomatic Kotlin and Scala 3 extensions. |
| **Python / PyTorch** | PyPI | `impulse-graph` | Native `pybind11` wheels with zero-copy NumPy and PyTorch DLPack tensor views. |
| **C / C++20** | Vcpkg / Conan | `impulse-graph` | C-ABI headers (`impulse_graph.h`, `impulse_vm.h`), C++20 wrappers, and `libimpulse_graph_static.a`. |
| **Rust** | Crates.io | `impulse-graph`, `impulse-graph-tooling` | Zero-dependency Rust engine crate (`mmap` reader, SoA slices, traversal, writer) and CLI tools. |
| **Go (CGo)** | Go Modules | `github.com/impulse-graph/impulse-graph-core/impulse-go` | CGo bindings linked against `libimpulse_graph_static.a`. |
| **.NET 8+ (C# / F#)** | NuGet.org | `ImpulseGraph`, `ImpulseGraph.Native` | Managed .NET 8+ API and cross-platform P/Invoke native binaries. |
| **Node.js / Bun** | npm | `impulse-graph` | TypeScript definitions (`index.d.ts`) and N-API native bindings. |
| **Containers** | GHCR | `ghcr.io/impulse-graph/impulse-tools:latest` | Standalone CLI and compiler toolchain container image. |

---

## Static Core Engine Linking & SLSA Level 3 Attestation

All native CLI binaries (`impulse-graph-tooling`), Python wheels, and Node.js N-API add-ons statically embed the core Impulse Graph C-ABI kernel (`libimpulse_graph_static.a` / `.lib`) and are built inside GitHub Actions CI with cryptographic build provenance (`actions/attest-build-provenance`):

* **Linux (`.deb` / `.rpm` / `tar.gz`)**: Standard packages target `glibc >= 2.28`; portable container tarballs link `musl-libc` (`-static`) for zero-dependency execution in `scratch` or Alpine containers.
* **macOS (`.pkg` / Homebrew)**: Embeds the static engine kernel, links system `libc++.dylib` and `libSystem.B.dylib` (macOS 11.0+), and is signed and notarized via Apple Developer ID.
* **Windows (`.msi` / `.zip`)**: Built with MSVC `/MT` (`LIBCMT.lib`) and signed with Authenticode (`signtool.exe`), requiring zero external Visual C++ Redistributable installers.
