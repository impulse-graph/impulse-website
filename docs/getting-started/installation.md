# Installation

Impulse Graph Engine provides two equivalent, zero-dependency core engines over the `.imps` binary snapshot format:

* **Pure Java 25 Engine (`org.impulsegraph`)**: 100% pure Java 25 implementation (FFM off-heap memory segments & Vector API) distributed on Maven Central. Requires no native `.so`/`.dylib`/`.dll` libraries.
* **Native C++20 / C-ABI Engine (`impulse-graph`)**: Native C-ABI kernel (`libimpulse_graph`) and language bindings for C++, Rust, Python, Go, .NET/C#, and Node.js.

Choose your language ecosystem below:

=== "Java 22+ / 25 (Maven / Gradle)"

    The pure Java engine is packaged under groupId `org.impulsegraph`. The core runtime (`impulse-spec`, `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`) has **zero third-party runtime dependencies**.

    !!! note "Maven Central (`0.10.0`)"
        `org.impulsegraph:*:0.10.0` is published on Maven Central (release JARs are also on [GitHub Releases](https://github.com/impulse-graph/impulse-graph-java/releases/tag/v0.10.0)). To install a local snapshot from source:
        ```bash
        git clone https://github.com/impulse-graph/impulse-graph-java.git
        cd impulse-graph-java && mvn clean install -DskipTests
        ```

    **Maven (`pom.xml`)**:

    ```xml
    <dependencies>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-api</artifactId>
            <version>0.10.0</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-storage</artifactId>
            <version>0.10.0</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-vm</artifactId>
            <version>0.10.0</version>
        </dependency>
        <!-- Multi-pass openCypher, CEL, and ImpScheme compiler -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-compiler</artifactId>
            <version>0.10.0</version>
        </dependency>
        <!-- Streaming .imps snapshot builder -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-builder</artifactId>
            <version>0.10.0</version>
        </dependency>
    </dependencies>
    ```

    **Gradle (`build.gradle.kts`)**:

    ```kotlin
    dependencies {
        implementation("org.impulsegraph:impulse-api:0.10.0")
        implementation("org.impulsegraph:impulse-storage:0.10.0")
        implementation("org.impulsegraph:impulse-vm:0.10.0")
        implementation("org.impulsegraph:impulse-compiler:0.10.0")
        implementation("org.impulsegraph:impulse-builder:0.10.0")
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

    *(Official `vcpkg` and Conan port manifests are in progress for upcoming releases.)*

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

=== "Rust"

    Add the self-contained crate from crates.io:

    ```bash
    cargo add impulse-graph
    ```

## Developer CLI (`impulse-cli`)

The CLI toolchain (`impulse build`, `impulse compile`, `impulse run`, `impulse snapshot inspect`, `impulse snapshot validate`) lives in `impulse-graph-core/impulse-cli` (binary name: `impulse-graph`) and can be run via Docker or compiled from source:

```bash
# Run via Docker
docker pull ghcr.io/impulse-graph/impulse-tools:latest
docker run --rm -v $(pwd):/data ghcr.io/impulse-graph/impulse-tools:latest impulse snapshot inspect /data/snapshot.imps

# Or build and install from source (Rust 1.80+)
git clone https://github.com/impulse-graph/impulse-graph-core.git
cargo install --path impulse-graph-core/impulse-cli

# The binary is named 'impulse-graph'. You can create a shell alias:
alias impulse="impulse-graph"
```
