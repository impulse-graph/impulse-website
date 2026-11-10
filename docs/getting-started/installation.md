# Installation

Impulse Graph Engine provides two equivalent, zero-dependency core engines over the `.imps` binary snapshot format:

* **Pure Java 25 Engine (`org.impulsegraph`)**: 100% pure Java 25 implementation (FFM off-heap memory segments & Vector API) distributed on Maven Central. Requires no native `.so`/`.dylib`/`.dll` libraries.
* **Native C++20 / C-ABI Engine (`impulse-graph`)**: Native C-ABI kernel (`libimpulse_graph`) and language bindings for C++, Rust, Python, Go, .NET/C#, and Node.js.

Choose your language ecosystem below:

=== "Java 22+ / 25 (Maven / Gradle)"

    The pure Java engine is packaged under groupId `org.impulsegraph`. The core runtime (`impulse-spec`, `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`) has **zero third-party runtime dependencies**.

    !!! note "Pre-v1.0 Local Installation & Maven Central"
        Artifacts can be installed to your local `~/.m2` repository in seconds:
        ```bash
        git clone https://github.com/impulse-graph/impulse-graph-java.git
        cd impulse-graph-java && mvn clean install -DskipTests
        ```
        Central repository indexing for `org.impulsegraph:0.9.0` is staged for the upcoming general release.

    **Maven (`pom.xml`)**:

    ```xml
    <dependencies>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-api</artifactId>
            <version>0.9.0</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-storage</artifactId>
            <version>0.9.0</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-vm</artifactId>
            <version>0.9.0</version>
        </dependency>
        <!-- Multi-pass openCypher, CEL, and ImpScheme compiler -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-compiler</artifactId>
            <version>0.9.0</version>
        </dependency>
        <!-- Streaming .imps snapshot builder -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-builder</artifactId>
            <version>0.9.0</version>
        </dependency>
    </dependencies>
    ```

    **Gradle (`build.gradle.kts`)**:

    ```kotlin
    dependencies {
        implementation("org.impulsegraph:impulse-api:0.9.0")
        implementation("org.impulsegraph:impulse-storage:0.9.0")
        implementation("org.impulsegraph:impulse-vm:0.9.0")
        implementation("org.impulsegraph:impulse-compiler:0.9.0")
        implementation("org.impulsegraph:impulse-builder:0.9.0")
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

    Pre-compiled wheels can be downloaded from GitHub Releases, or compiled from source:

    ```bash
    # Install from source:
    git clone https://github.com/impulse-graph/impulse-graph-core.git
    cd impulse-graph-core/impulse-python && pip install .
    ```

    *(PyPI registry distribution under `impulse-graph` is staged for the upcoming v1.0 release.)*

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
