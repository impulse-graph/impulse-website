# Installation

Impulse Graph Engine provides two equivalent, zero-dependency core engines over the `.imps` binary snapshot format:

* **Pure Java 25 Engine (`org.impulsegraph`)**: 100% pure Java 25 implementation (FFM off-heap memory segments & Vector API) distributed on Maven Central. Requires no native `.so`/`.dylib`/`.dll` libraries.
* **Native C++20 / C-ABI Engine (`impulse-graph`)**: Native C-ABI kernel (`libimpulse_graph`) and language bindings for C++, Rust, Python, Go, .NET/C#, and Node.js.

Choose your language ecosystem below:

=== "Java 25 (Maven / Gradle)"

    The pure Java 25 engine is published to Maven Central under groupId `org.impulsegraph`. The core runtime (`impulse-spec`, `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`) has **zero third-party runtime dependencies**.

    **Maven (`pom.xml`)**:

    ```xml
    <dependencies>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-api</artifactId>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-storage</artifactId>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-vm</artifactId>
        </dependency>
        <!-- Multi-pass openCypher, CEL, and ImpScheme compiler -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-compiler</artifactId>
        </dependency>
        <!-- Optional: Streaming .imps snapshot builder -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-builder</artifactId>
        </dependency>
    </dependencies>
    ```

    **Gradle (`build.gradle.kts`)**:

    ```kotlin
    dependencies {
        implementation("org.impulsegraph:impulse-api")
        implementation("org.impulsegraph:impulse-storage")
        implementation("org.impulsegraph:impulse-vm")
        implementation("org.impulsegraph:impulse-compiler")
        implementation("org.impulsegraph:impulse-builder")
    }
    ```

=== "C / C++20 (CMake / vcpkg)"

    The C-ABI and C++20 engine (`impulse-graph-core/impulse-cpp`) has zero external runtime dependencies and can be integrated via CMake or `vcpkg`.

    **Using `vcpkg`**:

    ```bash
    vcpkg install impulse-graph
    ```

    **In `CMakeLists.txt`**:

    ```cmake
    find_package(impulse-graph CONFIG REQUIRED)
    target_link_libraries(your_target PRIVATE impulse-graph::impulse-graph)
    ```

=== "Python"

    Install the pre-compiled wheel (with zero-copy NumPy and PyTorch `mmap` tensor views) from PyPI:

    ```bash
    pip install impulse-graph
    ```

## Developer CLI (`impulse-graph-tooling`)

The CLI toolchain (`impulse build`, `impulse compile`, `impulse run`, `impulse snapshot inspect`, `impulse snapshot validate`) can be run via Docker or installed as a standalone static binary:

```bash
docker pull ghcr.io/impulse-graph/impulse-tools:latest
docker run --rm -v $(pwd):/data ghcr.io/impulse-graph/impulse-tools:latest impulse snapshot inspect /data/snapshot.imps
```
