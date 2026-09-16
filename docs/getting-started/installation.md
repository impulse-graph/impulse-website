# Installation

The Impulse Graph Engine is distributed across major package managers, ensuring a native integration experience regardless of your stack. The engine uses a shared C-ABI core, meaning performance is universally exceptional.

Choose your language ecosystem below to install Impulse Graph:

=== "Java"

    For JVM projects (Java 21 LTS, Java 22+, and Java 25 LTS), Impulse Graph is available directly via Maven Central under groupId `org.impulsegraph`. We utilize Java's Foreign Function & Memory API (FFM) for zero-copy native interoperability.
    
    Add the following to your `pom.xml`:
    
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
        <!-- Optional: Add impulse-compiler for openCypher parsing and query optimizations -->
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-compiler</artifactId>
            <version>0.9.0</version>
        </dependency>
    </dependencies>
    ```
    
    For Gradle users (`build.gradle.kts`):
    
    ```kotlin
    implementation("org.impulsegraph:impulse-api:0.9.0")
    implementation("org.impulsegraph:impulse-storage:0.9.0")
    implementation("org.impulsegraph:impulse-vm:0.9.0")
    implementation("org.impulsegraph:impulse-compiler:0.9.0") // Optional
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
    impulse-graph = "0.9.0"
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
