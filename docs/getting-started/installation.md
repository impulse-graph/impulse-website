# Installation

Impulse Graph Engine provides pluggable, zero-dependency execution runtimes over the portable `.imps` binary snapshot format and `impOps` bytecode ISA:

* **Pure JVM Runtime (`org.impulsegraph`)**: 100% pure Java 21 LTS / 25 implementation (FFM off-heap memory segments, Vector API, and `MethodHandle` JIT) distributed on Maven Central—powering Java, Kotlin, Scala 3, and Clojure with zero JNI `.so`/`.dylib`/`.dll` libraries.
* **Native C++20 / C-ABI Runtime (`impulse-graph`)**: Native C-ABI kernel (`libimpulse_graph`) and SDK bindings for C/C++20, Rust, Python, Go, .NET/C# (P/Invoke), and Node.js.

Choose your language ecosystem below:

=== "Java 21 LTS / 25 (Maven / Gradle)"

    The pure JVM runtime is packaged under groupId `org.impulsegraph`. The core engine (`impulse-spec`, `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`) has **zero third-party runtime dependencies**.

    !!! note "Maven Central (`0.10.1`)"
        `org.impulsegraph:*:0.10.1` is published on Maven Central (release JARs are also on [GitHub Releases](https://github.com/impulse-graph/impulse-graph-java/releases/tag/v0.10.1)). To install a local snapshot from source:
        ```bash
        git clone https://github.com/impulse-graph/impulse-graph-java.git
        cd impulse-graph-java && mvn clean install -DskipTests
        ```

    !!! info "Upcoming in `v0.11`: `impulse-bom`, AOT Codegen & `impulse-j`"
        `v0.11` introduces **`org.impulsegraph:impulse-bom`** for single-version dependency management, **`impulse-maven-plugin` / `impulse-codegen`** for schema-first `.imps.schema.yaml` AOT Java code generation, **`SnapshotLifecycleManager`** for S3/Kubernetes hot-reload, and **`impulse-j`** (a pure-Java CLI requiring no native binaries). See the **[Java & JVM Ecosystem Hub](../ecosystems/java/index.md)**, **[Maven & Build Tooling](../ecosystems/java/maven-and-build-tooling.md)**, and **[AOT Code Generation](../ecosystems/java/aot-codegen.md)**.

    **Maven (`pom.xml` — `0.10.1`)**:

    ```xml
    <dependencies>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-api</artifactId>
            <version>0.10.1</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-storage</artifactId>
            <version>0.10.1</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-vm</artifactId>
            <version>0.10.1</version>
        </dependency>
        <!-- Multi-pass openCypher, CEL, and ImpScheme compiler -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-compiler</artifactId>
            <version>0.10.1</version>
        </dependency>
        <!-- Streaming .imps snapshot builder -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-builder</artifactId>
            <version>0.10.1</version>
        </dependency>
    </dependencies>
    ```

    **Gradle (`build.gradle.kts` — `0.10.1`)**:

    ```kotlin
    dependencies {
        implementation("org.impulsegraph:impulse-api:0.10.1")
        implementation("org.impulsegraph:impulse-storage:0.10.1")
        implementation("org.impulsegraph:impulse-vm:0.10.1")
        implementation("org.impulsegraph:impulse-compiler:0.10.1")
        implementation("org.impulsegraph:impulse-builder:0.10.1")
    }
    ```

=== "C / C++20 (CMake)"

    The C-ABI and C++20 engine (`impulse-graph-core/impulse-cpp`) has zero external runtime dependencies and can be integrated via CMake:

    **Via Git Submodule / `add_subdirectory`**:

    ```cmake
    add_subdirectory(impulse-graph-core/impulse-cpp)
    target_link_libraries(your_target PRIVATE impulse_graph_static)
    ```

    **Or via CMake `find_package` (after `cmake --install`)**:

    ```cmake
    find_package(impulse-graph CONFIG REQUIRED)
    target_link_libraries(your_target PRIVATE impulse-graph::impulse-graph)
    ```

    *(Official `vcpkg` and Conan port manifests are in progress for upcoming releases; see the [Native, Rust & Polyglot Hub](../ecosystems/native/index.md).)*

=== "Python"

    Install pre-built wheels directly from PyPI:

    ```bash
    pip install impulse-graph
    ```

    Or compile from source:
    ```bash
    git clone https://github.com/impulse-graph/impulse-graph-core.git
    cd impulse-graph-core/impulse-python && pip install .
    ```

    *(See the [Python & PyTorch Hub](../ecosystems/python/index.md) for Parquet snapshot building and GNN sampling.)*

=== "Rust"

    Add the self-contained crate from crates.io:

    ```bash
    cargo add impulse-graph
    ```

## Developer CLI Toolchains (`impulse-graph` & `impulse-j`)

Impulse Graph provides two CLI distributions for building (`build`), inspecting (`snapshot inspect`), validating (`snapshot validate`), optimizing (`snapshot optimize`), and running (`compile` / `run`) `.imps` snapshots:

1. **Native CLI (`impulse-graph`, aliased as `impulse`)**: Standalone native binary in `impulse-graph-core/impulse-cli` with zero JVM dependency—recommended for Python, C/C++, Rust, data engineering, and CI containers (see [Native CLI Reference](../ecosystems/native/cli-reference.md)).
2. **Pure-Java CLI (`impulse-j`, `v0.11`)**: 100% JVM CLI in `impulse-graph-java/impulse-cli` for locked-down enterprise Java environments where native executables are prohibited (see [Pure-Java CLI (`impulse-j`)](../ecosystems/java/cli-impulse-j.md)).

```bash
# Option A: Run the native CLI via Docker
docker pull ghcr.io/impulse-graph/impulse-tools:latest
docker run --rm -v $(pwd):/data ghcr.io/impulse-graph/impulse-tools:latest impulse snapshot inspect /data/snapshot.imps

# Option B: Build and install the native CLI from source (Rust 1.80+)
git clone https://github.com/impulse-graph/impulse-graph-core.git
cargo install --path impulse-graph-core/impulse-cli

# The native binary is named 'impulse-graph'. Create a shell alias if desired:
alias impulse="impulse-graph"
```
