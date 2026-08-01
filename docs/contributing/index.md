# Contributing to Impulse Graph Engine

Welcome! We are excited to have you contribute to the Impulse Graph Engine. Because our repository spans multiple languages and architectural layers, please review this guide to get your local environment configured.

## Architecture Rule: Zero Dependencies

The core engine (`impulse-core` in Java, `impulse-cpp`, `impulse-rust`) strictly maintains **zero third-party runtime dependencies**. 

Features like Kafka, Spring Boot, or RocksDB belong in the `impulse-platform` repository. Do not introduce network, parsing, or logging dependencies into the core engine.

## Building from Source

All projects reside in the `~/impulse/` workspace.

### Java Core (`impulse-graph/impulse-java/`)
Requires JDK 25+. 
```bash
cd impulse-graph/impulse-java
mvn clean test
```

### C++ Kernel (`impulse-graph/impulse-cpp/`)
Requires a C++20 compliant compiler (GCC 11+, Clang 14+, MSVC 19.30+).
```bash
cd impulse-graph/impulse-cpp
cmake -B build
cmake --build build
```

### Rust Crate (`impulse-graph/impulse-rust/`)
Requires latest stable Rust.
```bash
cd impulse-graph/impulse-rust
cargo test
```

### Developer Tools (`impulse-tools/`)
```bash
cd impulse-tools
cmake -B build
cmake --build build
```

### Documentation (`impulse-website/`)
Requires Python and MkDocs Material.
```bash
cd impulse-website
pip install mkdocs-material
mkdocs serve
```

## Git & Data Hygiene

- **No Data Blobs**: Never commit datasets (`.csv`, `.bin`, `.imps`) into Git.
- **Datasets Folder**: Use the `datasets/` subdirectory for all local tests and benchmarks. It is excluded via `.gitignore`.
- **Branch Naming**: Use `feature/<name>`, `bugfix/<name>`, or `docs/<name>`.
