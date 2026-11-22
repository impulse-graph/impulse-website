# Packages & Distribution

Impulse Graph `v0.10.0` is published on **Maven Central**, **PyPI**, **crates.io**, and **GitHub Releases**.

| Ecosystem | Registry | Package / Coordinate | Status | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Java 21/25 (JVM)** | Maven Central | `org.impulsegraph:impulse-spec`, `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`, `impulse-builder` | Live (`0.10.0`) | Pure Java FFM snapshot engine, VM/JIT, compiler suite, and streaming builder. |
| **Kotlin / Scala 3 / Clojure** | Maven Central | `org.impulsegraph:impulse-kotlin`, `impulse-scala_3`, `impulse-clojure` | Live (`0.10.0`) | Idiomatic JVM language DSL extensions. |
| **Python / PyTorch** | PyPI | `impulse-graph` | Live (`0.10.0`) | Pre-built `pybind11` wheels (Linux, macOS arm64, Windows) with NumPy & PyTorch interop. |
| **Rust** | crates.io | `impulse-graph` | Live (`0.10.0`) | Self-contained Rust crate (bundled C++20/Highway sources, optional `IMPULSE_SDK_DIR` override). |
| **CLI & C/C++20 SDK** | GitHub Releases | `impulse-cli`, `impulse-sdk` | Live (`v0.10.0`) | Pre-built CLI binaries, C-ABI headers (`impulse_graph.h`, `impulse_vm.h`), and static/shared libs. |
| **Go (CGo)** | Go Modules | `github.com/impulse-graph/impulse-graph/go` | Active | CGo bindings linked against `libimpulse_graph_static.a`. |
| **.NET 8+ (C# / F#)** | NuGet.org | `ImpulseGraph`, `ImpulseGraph.Native` | Staged (`v1.0`) | Managed .NET P/Invoke API and native binaries. |
| **Node.js / Bun** | npm | `impulse-graph` | Staged (`v1.0`) | TypeScript definitions and N-API native bindings. |
| **Containers** | GHCR | `ghcr.io/impulse-graph/impulse-tools`, `impulse-platform-server` | In Progress | CLI and platform server container images. |

---

## Static Linking & Build Attestations

Native CLI binaries (`impulse-cli`), Python wheels, and Node.js N-API add-ons statically embed `libimpulse_graph_static.a` / `.lib` and are built in GitHub Actions CI with SLSA Level 3 build provenance attestations (`actions/attest-build-provenance`):

* **Linux (`.deb` / `.rpm` / `tar.gz`)**: Standard packages target `glibc >= 2.28`; container tarballs target static `musl-libc`.
* **macOS (`.pkg` / Homebrew)**: Embeds the static kernel, links system `libc++.dylib` and `libSystem.B.dylib` (macOS 11.0+), and is signed and notarized via Apple Developer ID.
* **Windows (`.msi` / `.zip`)**: Built with MSVC `/MT` and signed with Authenticode (`signtool.exe`), requiring no Visual C++ Redistributable installer.
