# Package Registry & Distribution

Impulse Graph is distributed across a wide variety of package managers and registries, supporting a truly polyglot ecosystem.

| Ecosystem | Registry | Package Name | Description |
|-----------|----------|--------------|-------------|
| **Java / JVM** | Maven Central | `io.impulse.graph:impulse-core` | Core Java engine, Zero-dependency. |
| **Java / JVM** | Maven Central | `io.impulse.graph:impulse-api` | Public interfaces and AST builders. |
| **Scala** | Maven Central | `io.impulse.graph:impulse-scala_3` | Scala 3 Idiomatic wrappers. |
| **Kotlin** | Maven Central | `io.impulse.graph:impulse-kotlin` | Kotlin extension functions and coroutines. |
| **Rust** | Crates.io | `impulse-graph` | Core engine crate (zero-cost). |
| **Rust** | Crates.io | `impulse-tools` | Developer tools (`impulse-opt`, `impulse-inspect`). |
| **Python** | PyPI | `impulse-graph` | Native wheels for Python, PyTorch GNN integration. |
| **.NET / C#** | NuGet.org | `ImpulseGraph` | Managed API for .NET. |
| **.NET / C#** | NuGet.org | `ImpulseGraph.Native` | Cross-platform embedded native binaries. |
| **F#** | NuGet.org | `ImpulseGraph.FSharp` | F# idiomatic bindings. |
| **Node.js** | npm | `impulse-graph` | TypeScript definitions & N-API bindings. |
| **C / C++** | Vcpkg / Conan | `impulse-graph` | C-ABI headers (`impulse_graph.h`) and static/shared libs. |
| **Docker** | GHCR | `ghcr.io/impulse-graph/impulse-platform-server:latest` | Enterprise cloud infrastructure platform. |

## Static Core Engine Linking

All native binaries (`impulse-tools`, Python wheels, Node N-API) statically embed the core Impulse Graph C-ABI kernel (`libimpulse_graph_static.a`). 
- **Linux**: Targets `glibc >= 2.28`, with `musl` fully static alternatives available.
- **Windows**: Built with MSVC `/MT` to eliminate runtime installer requirements.
- **macOS**: Embeds static engine kernel, links standard `libc++.dylib`.
