# Impulse Graph Java Engine Integration Walkthrough

This walkthrough guides you through integrating the **Impulse Graph Java** (`impulse-graph-java`) library into an existing Java application. It covers cloning and building the native FFM engine, publishing it to your local Maven cache, configuring your project dependencies and JVM runtime flags, and querying a binary snapshot (`.imps`) file containing Role-Based Access Control (RBAC) data using the fluent query builder API.

---

## Prerequisites

Before beginning, ensure your environment meets the following requirements:

* **JDK 25** or higher with support for Foreign Function & Memory (FFM) API and Vector API (`jdk.incubator.vector`).
* **Apache Maven 3.9+** (or **Gradle 8.5+**).
* **Git** CLI.
* An existing Java project configured for Java 25.

---

## Step 1: Clone the Repository

Clone the `impulse-graph-java` repository from GitHub into your local workspace:

```bash
git clone https://github.com/impulse-graph/impulse-graph-java.git
cd impulse-graph-java
```

> [!NOTE]
> If you are working locally within the `~/impulse` multi-repository ecosystem, the code is available at `~/impulse/impulse-graph-java`.

---

## Step 2: Build and Install to Local Maven Cache (`~/.m2/repository`)

`impulse-graph-java` is structured as a multi-module Maven project:
* `impulse-spec`: Binary Snapshot v2.4 layout and schema specifications.
* `impulse-api`: Fluent query builder, `IdMapper`, and query AST definitions.
* `impulse-core`: Pure Java 25 off-heap Foreign Function & Memory (FFM) CSR execution kernel.

Execute `mvn clean install` to compile the modules and install artifacts to your local Maven cache (`~/.m2/repository`):

```bash
mvn clean install -DskipTests
```

Upon completion, the following artifacts will be available in your local repository:
* `io.impulse.graph:impulse-spec:2.3.0-SNAPSHOT`
* `io.impulse.graph:impulse-api:2.3.0-SNAPSHOT`
* `io.impulse.graph:impulse-core:2.3.0-SNAPSHOT`

---

## Step 3: Configure Project Dependencies & JVM Runtime Flags

### Maven Configuration (`pom.xml`)

Add `impulse-core` to your project's `pom.xml`. `impulse-core` transitively pulls in `impulse-api` and `impulse-spec`:

```xml
<dependencies>
    <dependency>
        <groupId>io.impulse.graph</groupId>
        <artifactId>impulse-core</artifactId>
        <version>2.3.0-SNAPSHOT</version>
    </dependency>
</dependencies>
```

> [!IMPORTANT]
> Impulse Graph Java relies on Java 25 FFM off-heap memory segments and SIMD vector operations. You **must** configure compiler and surefire execution args in your `pom.xml`:

```xml
<build>
    <plugins>
        <!-- Java 25 Compiler Plugin -->
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>25</release>
                <compilerArgs>
                    <arg>--enable-preview</arg>
                    <arg>--add-modules</arg>
                    <arg>jdk.incubator.vector</arg>
                </compilerArgs>
            </configuration>
        </plugin>

        <!-- Test execution flags for off-heap native access -->
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.2.5</version>
            <configuration>
                <argLine>
                    --enable-preview 
                    --add-modules jdk.incubator.vector 
                    --enable-native-access=ALL-UNNAMED
                </argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

---

### Alternative: Gradle Configuration (`build.gradle`)

If your project uses Gradle, update `build.gradle` as follows:

```groovy
repositories {
    mavenLocal()
    mavenCentral()
}

dependencies {
    implementation 'io.impulse.graph:impulse-core:2.3.0-SNAPSHOT'
}

tasks.withType(JavaCompile) {
    options.compilerArgs += [
        '--enable-preview',
        '--add-modules', 'jdk.incubator.vector'
    ]
}

tasks.withType(JavaExec) {
    jvmArgs += [
        '--enable-preview',
        '--add-modules', 'jdk.incubator.vector',
        '--enable-native-access=ALL-UNNAMED'
    ]
}
```

---

## Step 4: Load a Downloaded Binary Snapshot (`.imps`) File

Impulse Graph loads binary snapshot files (`.imps`) direct-to-disk using zero-copy memory-mapped regions. Off-heap memory is safely scoped using Java 25's `java.lang.foreign.Arena`.

To load a snapshot file downloaded separately (e.g., `rbac_snapshot.imps` containing sample RBAC data):

```java
import org.impulsegraph.core.csr.BinarySnapshotLoader;
import org.impulsegraph.core.csr.GraphSnapshot;
import java.lang.foreign.Arena;
import java.nio.file.Path;
import java.nio.file.Paths;

Path snapshotPath = Paths.get("datasets/rbac_snapshot.imps");

// Arena.ofShared() ensures thread-safe off-heap memory allocation and predictable cleanup
try (Arena arena = Arena.ofShared()) {
    BinarySnapshotLoader.LoadedSnapshot loadedSnapshot = BinarySnapshotLoader.loadSnapshot(snapshotPath, arena);
    
    System.out.printf("Loaded snapshot version %d with %d domains and %d relations.%n",
            loadedSnapshot.version(),
            loadedSnapshot.domainCount(),
            loadedSnapshot.relationCount());
            
    GraphSnapshot graph = loadedSnapshot.graph();
    // Snapshot is ready for querying...
}
```

---

## Step 5: Build and Execute Queries Using the Fluent Query Builder

Impulse Graph provides a fluent AST query builder (`ImpulseGraphQuery.builder()`) to define declarative, vector-accelerated graph traversals.

### 3-Tier RBAC Graph Traversal Example

In a standard 3-tier ReBAC/RBAC model:
1. `USER` nodes are linked to `GROUP` nodes via `userToGroup` edges.
2. `GROUP` nodes are linked to `ROLE` nodes via `groupToRole` edges.

The query pipeline traverses from an input set of User IDs to collect all associated Role IDs:

```java
import org.impulsegraph.api.ArgType;
import org.impulsegraph.api.ImpulseGraphQuery;
import org.impulsegraph.api.ReturnType;

// 1. Construct immutable query AST using the fluent builder
ImpulseGraphQuery<Object> rbacQuery = ImpulseGraphQuery.builder()
        .input("USER", ArgType.ROARING_BITSET)
        .walkEdge("userToGroup")
        .walkEdge("groupToRole")
        .collect(ReturnType.ROARING_BITSET);

// 2. Execute query against the loaded snapshot
Object result = rbacQuery.execute(loadedSnapshot, inputBitset);
```

---

## Step 6: Complete End-to-End Executable Example

Below is a self-contained, end-to-end example demonstrating file loading, query construction, execution, and off-heap memory management.

```java
package com.example.rbac;

import org.impulsegraph.api.ArgType;
import org.impulsegraph.api.ImpulseGraphQuery;
import org.impulsegraph.api.ReturnType;
import org.impulsegraph.core.csr.BinarySnapshotLoader;
import org.impulsegraph.core.csr.GraphSnapshot;
import org.impulsegraph.core.csr.RelationSnapshot;

import java.lang.foreign.Arena;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.BitSet;

public class RbacSnapshotQueryExample {

    public static void main(String[] args) throws Exception {
        Path snapshotPath = Paths.get("datasets/rbac_snapshot.imps");

        if (!Files.exists(snapshotPath)) {
            System.err.println("Error: Snapshot file not found at " + snapshotPath.toAbsolutePath());
            System.exit(1);
        }

        System.out.println("[+] Loading binary snapshot: " + snapshotPath);

        // 1. Allocate shared memory arena for off-heap C-ABI graph buffers
        try (Arena arena = Arena.ofShared()) {
            BinarySnapshotLoader.LoadedSnapshot loadedSnapshot = 
                    BinarySnapshotLoader.loadSnapshot(snapshotPath, arena);

            System.out.printf("[+] Snapshot Magic: 0x%X | Version: %d | SHA256: %s%n",
                    loadedSnapshot.magic(),
                    loadedSnapshot.version(),
                    loadedSnapshot.getSha256Checksum());

            // 2. Inspect underlying CSR topology
            GraphSnapshot graph = loadedSnapshot.graph();
            System.out.println("[+] Available relations: " + loadedSnapshot.getRelationNames());

            // 3. Define 3-tier User -> Group -> Role RBAC query via fluent AST builder
            ImpulseGraphQuery<Object> userToRolesQuery = ImpulseGraphQuery.builder()
                    .input("USER", ArgType.ROARING_BITSET)
                    .walkEdge("userToGroup")
                    .walkEdge("groupToRole")
                    .collect(ReturnType.ROARING_BITSET);

            System.out.println("[+] Built AST Query Operation: " + userToRolesQuery.getOperationName());

            // 4. Prepare input seed parameter (e.g. User Index 0)
            BitSet inputUsers = new BitSet();
            inputUsers.set(0);

            // 5. Execute query pipeline against snapshot
            Object result = userToRolesQuery.execute(loadedSnapshot, inputUsers);

            System.out.println("[+] Query execution finished successfully.");
            System.out.println("[+] Query Result: " + result);
        }
        // 6. Shared Arena closes automatically here, releasing off-heap memory
        System.out.println("[+] Off-heap graph snapshot memory closed successfully.");
    }
}
```

---

## Running the Example Application

When executing your Java project from the command line, pass the required JVM flags for native memory access and vector acceleration:

```bash
java --enable-preview \
     --add-modules jdk.incubator.vector \
     --enable-native-access=ALL-UNNAMED \
     -cp "target/my-app-1.0.0.jar:target/dependency/*" \
     com.example.rbac.RbacSnapshotQueryExample
```

---

## Summary Checklist

| Step | Action | Command / Code |
| :--- | :--- | :--- |
| **1. Clone** | Clone engine source | `git clone https://github.com/impulse-graph/impulse-graph-java.git` |
| **2. Build** | Install to local Maven cache | `mvn clean install -DskipTests` |
| **3. Depend** | Add dependency in `pom.xml` | `<artifactId>impulse-core</artifactId>` |
| **4. Configure**| Add compiler & surefire args | `--enable-preview --add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED` |
| **5. Load** | Open `.imps` file in shared Arena | `BinarySnapshotLoader.loadSnapshot(path, arena)` |
| **6. Query** | Construct fluent AST query | `ImpulseGraphQuery.builder().input(...).walkEdge(...).collect(...)` |

