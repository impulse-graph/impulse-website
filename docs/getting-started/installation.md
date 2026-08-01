# Installation

The Impulse Graph Engine is distributed across major package managers, ensuring a native integration experience regardless of your stack. The engine uses a shared C-ABI core, meaning performance is universally exceptional.

Choose your language ecosystem below to install Impulse Graph:

=== "Java"

    For JVM projects (Java 25+, Kotlin, Scala), Impulse Graph is available via Maven Central. We utilize Java's Foreign Function & Memory API (FFM) for zero-copy native interoperability.
    
    Add the following to your `pom.xml`:
    
    ```xml
    <dependency>
        <groupId>io.impulse.graph</groupId>
        <artifactId>impulse-core</artifactId>
        <version>2.3.0</version>
    </dependency>
    ```
    
    For Gradle users (`build.gradle.kts`):
    
    ```kotlin
    implementation("io.impulse.graph:impulse-core:2.3.0")
    ```

=== "C++"

    For C++20 projects, you can integrate Impulse Graph Engine via CMake using `vcpkg` or by building from source. The core library has zero external dependencies.
    
    Using **vcpkg**:
    
    ```bash
    vcpkg install impulse-graph
    ```
    
    In your `CMakeLists.txt`:
    
    ```cmake
    find_package(impulse-graph CONFIG REQUIRED)
    target_link_libraries(your_target PRIVATE impulse-graph::impulse-graph)
    ```

=== "Rust"

    For Rust projects, Impulse Graph is available on `crates.io`.
    
    Add the dependency to your `Cargo.toml`:
    
    ```toml
    [dependencies]
    impulse-graph = "2.3.0"
    ```
    
    Or run:
    
    ```bash
    cargo add impulse-graph
    ```

## Developer Tools (CLI)

The optimizer and inspector utilities (`impulse-opt`, `impulse-inspect`) can be pulled globally via Docker:

```bash
docker pull ghcr.io/impulse-graph/impulse-tools:latest
docker run --rm -v $(pwd):/data ghcr.io/impulse-graph/impulse-tools:latest impulse-inspect /data/snapshot.imps
```
