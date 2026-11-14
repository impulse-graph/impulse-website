# Contributing to Impulse Graph Engine

Welcome! We are excited to have you contribute to the Impulse Graph Engine. Because our repository spans multiple languages and architectural layers, please review this guide to get your local environment configured.

## Architecture Rule: Zero Dependencies

The core engine (`impulse-storage` and `impulse-vm` in Java, `impulse-cpp`, `impulse-rust`) strictly maintains **zero third-party runtime dependencies**. 

Features like Kafka, Spring Boot, or RocksDB belong in the `impulse-platform` repository. Do not introduce network, parsing, or logging dependencies into the core engine.

## Building from Source

All repositories reside in the `~/impulse/` multi-repository workspace. Engine and verification repositories include `impulse-graph-spec` at `spec/` via Git submodules, so clone them with `--recurse-submodules`:

```bash
git clone --recurse-submodules https://github.com/impulse-graph/impulse-graph-core.git
git clone --recurse-submodules https://github.com/impulse-graph/impulse-graph-java.git
```

### Pure Java Engine (`impulse-graph-java/`)
Requires JDK 22+ (JDK 25 recommended for Vector API SIMD enhancements).
```bash
cd impulse-graph-java
mvn clean test
```

### Native C++20 & C-ABI Kernel (`impulse-graph-core/impulse-cpp/`)
Requires a C++20 compliant compiler (GCC 11+, Clang 14+, MSVC 19.30+).
```bash
cd impulse-graph-core/impulse-cpp
cmake -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

### Rust Crate (`impulse-graph-core/impulse-rust/`)
Requires stable Rust (`1.80+`).
```bash
cd impulse-graph-core/impulse-rust
cargo test
```

### Developer CLI & Compiler Suite (`impulse-graph-core/impulse-cli/`)
```bash
cd impulse-graph-core/impulse-cli
cargo build --release
cargo test
```

### Specification & Opcode Coverage (`impulse-graph-spec/`)
```bash
cd impulse-graph-spec
python3 tools/run_vm_asm_suite.py
```

### Four-Way Polyglot Validation & Fuzzing (`impulse-verification/`)
Requires pre-building the C++ kernels (`build_on` and `build_off`) and Java classes:
```bash
# 1. Build C++ kernels with optimizations ON and OFF
cd impulse-graph-core/impulse-cpp
cmake -B build_on -DCMAKE_BUILD_TYPE=Release && cmake --build build_on
cmake -B build_off -DCMAKE_BUILD_TYPE=Debug -DOPTIMIZATIONS=OFF && cmake --build build_off

# 2. Compile Java classes
cd ../../impulse-graph-java && mvn compile -DskipTests

# 3. Run Four-Way Validation
cd ../impulse-verification
python3 tools/four_way_validation.py
```

### Documentation Portal (`impulse-website/`)
Requires Python 3 and MkDocs Material.
```bash
cd impulse-website
pip install mkdocs-material
mkdocs serve
```

## Git & Data Hygiene

- **No Data Blobs**: Never commit datasets (`.csv`, `.bin`, `.imps`) into Git.
- **Datasets Folder**: Use the `datasets/` subdirectory for all local tests and benchmarks. It is excluded via `.gitignore`.
- **Branch Naming**: Use `feature/<name>`, `bugfix/<name>`, or `docs/<name>`.
