# Packages & Distribution

Impulse Graph Engine is distributed via GitHub Releases (native installer packages, static archives, and SLSA Level 3 attestations), GHCR container images, and source repositories, with public package registry distribution in active staging for the upcoming `v1.0` release.

| Ecosystem | Target Registry | Package / Coordinate | Status | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-api` | Staged (v1.0) | Public interfaces (`ImpulseGraphSnapshot`, `DomainView`, `Traversal`, `ImpulseStatement`). |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-storage` | Staged (v1.0) | Zero-dependency Java 25 FFM off-heap CSR/CSC snapshot engine and `SnapshotSwapManager`. |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-vm` | Staged (v1.0) | Register-based `ImpulseVM` interpreter, `MethodHandle` JIT, and bytecode emitter. |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-compiler` | Staged (v1.0) | Multi-pass `ImpScheme`, `openCypher`, and `CEL` optimizing compiler. |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-builder` | Staged (v1.0) | Direct-to-disk streaming `.imps` snapshot builder. |
| **Java 25 / JVM** | Maven Central | `org.impulsegraph:impulse-spec` | Staged (v1.0) | Binary Snapshot Format FFM memory layouts and protocol constants. |
| **Kotlin / Scala 3** | Source Build | `impulse-kotlin`, `impulse-scala` | Source | Idiomatic Kotlin and Scala 3 extensions in `impulse-graph-java`. |
| **Python / PyTorch** | PyPI | `impulse-graph` | Staged (v1.0) | Native `pybind11` wheels with zero-copy NumPy buffer views and PyTorch tensor interop. |
| **C / C++20** | Vcpkg / Conan | `impulse-graph` | Staged (v1.0) | C-ABI headers (`impulse_graph.h`, `impulse_vm.h`), C++20 wrappers, and `libimpulse_graph_static.a`. |
| **Rust** | Crates.io | `impulse-graph`, `impulse-tools` | Staged (v1.0) | Zero-dependency Rust engine crate (`mmap` reader, SoA slices, traversal, writer) and standalone CLI tools (`impulse-cli`). |
| **Go (CGo)** | Go Modules | `github.com/impulse-graph/impulse-graph/go` | Active | CGo bindings linked against `libimpulse_graph_static.a`. |
| **.NET 8+ (C# / F#)** | NuGet.org | `ImpulseGraph`, `ImpulseGraph.Native` | Staged (v1.0) | Managed .NET 8+ API and cross-platform P/Invoke native binaries. |
| **Node.js / Bun** | npm | `impulse-graph` | Staged (v1.0) | TypeScript definitions (`index.d.ts`) and N-API native bindings. |
| **Containers** | GHCR | `ghcr.io/impulse-graph/impulse-tools:latest` | Active | Standalone CLI and compiler toolchain container image. |

---

## Static Core Engine Linking & SLSA Level 3 Attestation

All native CLI binaries (`impulse-cli`), Python wheels, and Node.js N-API add-ons statically embed the core Impulse Graph C-ABI kernel (`libimpulse_graph_static.a` / `.lib`) and are built inside GitHub Actions CI with cryptographic build provenance (`actions/attest-build-provenance`):

* **Linux (`.deb` / `.rpm` / `tar.gz`)**: Standard packages target `glibc >= 2.28`; portable container tarballs link `musl-libc` (`-static`) for zero-dependency execution in `scratch` or Alpine containers.
* **macOS (`.pkg` / Homebrew)**: Embeds the static engine kernel, links system `libc++.dylib` and `libSystem.B.dylib` (macOS 11.0+), and is signed and notarized via Apple Developer ID.
* **Windows (`.msi` / `.zip`)**: Built with MSVC `/MT` (`LIBCMT.lib`) and signed with Authenticode (`signtool.exe`), requiring zero external Visual C++ Redistributable installers.
