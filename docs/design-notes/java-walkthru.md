# Impulse Graph Java Engine Integration Walkthrough

This walkthrough guides you through integrating the **Impulse Graph Java** (`impulse-graph-java`) library into an existing Java application. It covers adding the Maven Central dependencies, configuring your project and JVM runtime flags, and querying an immutable binary snapshot (`.imps`) file containing Role-Based Access Control (RBAC) data using the fluent DomainView traversal API.

---

## Prerequisites

Before beginning, ensure your environment meets the following requirements:

* **Java 21 LTS** or **Java 22+** (including **Java 25 LTS** and **Java 26+**) with support for Foreign Function & Memory (FFM) and the Vector API (`jdk.incubator.vector`).
* **Apache Maven 3.9+** (or **Gradle 8.5+**).
* An existing Java project.

---

## Step 1: Configure Project Dependencies

Impulse Graph is published to **Maven Central** under the `org.impulsegraph` namespace.

### Maven Configuration (`pom.xml`)

Add the core engine modules to your `pom.xml`:

```xml
<dependencies>
    <!-- Public API & Domain Abstractions -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-api</artifactId>
        </dependency>

    <!-- Off-Heap Storage Layer & Binary Snapshot Loader -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-storage</artifactId>
        </dependency>

    <!-- Compute Virtual Machine & SIMD Traversal Execution -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-vm</artifactId>
        </dependency>

    <!-- Optional: Query Compiler for openCypher parsing & multi-stage passes -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-compiler</artifactId>
        </dependency>
</dependencies>
```

### Alternative: Gradle Configuration (`build.gradle.kts`)

If your project uses Gradle with Kotlin DSL:

```kotlin
dependencies {
    implementation("org.impulsegraph:impulse-api")
    implementation("org.impulsegraph:impulse-storage")
    implementation("org.impulsegraph:impulse-vm")
    implementation("org.impulsegraph:impulse-compiler") // Optional
}
```

---

## Step 2: Configure JVM Runtime & Compiler Flags

Impulse Graph utilizes off-heap memory mapping via Foreign Function & Memory (FFM) and SIMD vector operations via `jdk.incubator.vector`. Configure your build tool and runtime flags based on your target JDK:

| Java Runtime | Required JVM Flags | Description |
| :--- | :--- | :--- |
| **Java 22+ / Java 25 LTS** | `--add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED` | **Standard FFM** in `java.base`. No preview flag required. |
| **Java 21 LTS** | `--enable-preview --add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED` | Enables JEP 442 FFM Preview 3 on Java 21 LTS. |

### Maven Build Plugins (`pom.xml`)

```xml
<build>
    <plugins>
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

## Step 3: Load an Immutable Binary Snapshot (`.imps`) File

Impulse Graph loads `.imps` snapshot files directly from disk into off-heap memory using zero-copy memory mapping (`mmap`). Off-heap memory is safely scoped to a Java `java.lang.foreign.Arena`:

```java
import org.impulsegraph.api.ImpulseGraphSnapshot;
import org.impulsegraph.storage.csr.BinarySnapshotLoader;

import java.lang.foreign.Arena;
import java.nio.file.Path;

Path snapshotPath = Path.of("datasets/rbac_snapshot.imps");

// Arena.ofShared() manages thread-safe off-heap memory lifecycle
try (Arena arena = Arena.ofShared()) {
    var loaded = BinarySnapshotLoader.loadSnapshot(snapshotPath, arena);
    ImpulseGraphSnapshot snap = loaded.getGraph();

    System.out.printf("Loaded snapshot with %d relations across %d MB memory.%n",
            snap.getRelationCount(),
            snap.getOffHeapMemorySizeBytes() / (1024 * 1024));
}
```

---

## Step 4: Querying Connections (Universal Traversal Model)

All graph queries follow the **Kleisli Frontier Propagation Model** anchored to an explicit domain context:

$$\text{Pipeline} = \text{Anchor}(D_0, F_0, S_0) \gg= T_1 \gg= T_2 \dots \gg= \text{Collect}()$$

### 3-Tier RBAC Graph Traversal Example

In a standard Role-Based Access Control model:

- `USER` nodes link to `GROUP` nodes via relation `userToGroup`.
- `GROUP` nodes link to `ROLE` nodes via relation `groupToRole`.

We anchor to the `USER` domain, seed with User ID `0` (or resolve an external key), traverse two hops, and collect reached roles into a zero-allocation off-heap bitset:

```java
import org.impulsegraph.api.traversal.DomainView;
import org.impulsegraph.api.bitset.ImpulseBitSet;

// 1. Anchor query to the USER domain
DomainView userDomain = snap.domain("USER");

// 2. Execute 2-hop traversal: User(0) -> Group -> Role
ImpulseBitSet rolesReached = userDomain.from(0)
        .out("userToGroup")
        .out("groupToRole")
        .toBitSet();

System.out.println("Roles reached: " + rolesReached.cardinality());
```

---

## Step 5: Complete End-to-End Executable Example

Below is a self-contained, end-to-end example demonstrating snapshot loading, relation inspection, and fluent vector-accelerated traversal.

```java
package com.example.rbac;

import org.impulsegraph.api.ImpulseGraphSnapshot;
import org.impulsegraph.api.bitset.ImpulseBitSet;
import org.impulsegraph.api.traversal.DomainView;
import org.impulsegraph.storage.csr.BinarySnapshotLoader;
import org.impulsegraph.storage.csr.GraphSnapshot;
import org.impulsegraph.storage.csr.RelationSnapshot;

import java.lang.foreign.Arena;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.Set;

public class RbacSnapshotQueryExample {

    public static void main(String[] args) throws Exception {
        Path snapshotPath = Paths.get(args.length > 0 ? args[0] : "datasets/rbac_snapshot.imps");

        if (!Files.exists(snapshotPath)) {
            System.err.println("Error: Snapshot file not found at " + snapshotPath.toAbsolutePath());
            System.exit(1);
        }

        System.out.println("[+] Loading binary snapshot: " + snapshotPath);

        // 1. Allocate shared memory arena for off-heap graph buffers
        try (Arena arena = Arena.ofShared()) {
            BinarySnapshotLoader.LoadedSnapshot loadedSnapshot = 
                    BinarySnapshotLoader.loadSnapshot(snapshotPath, arena);

            System.out.printf("[+] Snapshot Magic: 0x%X | Version: %d%n",
                    loadedSnapshot.magic(),
                    loadedSnapshot.version());

            // 2. Obtain high-level graph view
            ImpulseGraphSnapshot graph = loadedSnapshot.getGraph();
            System.out.println("[+] Available relations: " + loadedSnapshot.getRelationNames());

            // 3. Execute 3-tier User -> Group -> Role traversal via fluent DomainView
            System.out.println("\n[+] Executing fluent vector traversal: User(0) -[:userToGroup]-> Group -[:groupToRole]-> Role");
            DomainView userDomain = graph.domain("USER");
            ImpulseBitSet roles = userDomain.from(0)
                    .out("userToGroup")
                    .out("groupToRole")
                    .toBitSet();

            System.out.printf("[+] Traversal reached %d roles (bitset cardinality).%n", roles.cardinality());

            // 4. Low-level CSR inspection (optional)
            GraphSnapshot rawGraph = loadedSnapshot.graph();
            RelationSnapshot userToGroup = rawGraph.getRelationSnapshot("userToGroup");
            RelationSnapshot groupToRole = rawGraph.getRelationSnapshot("groupToRole");

            if (userToGroup != null && groupToRole != null) {
                int startUser = 0;
                int[] groups = userToGroup.getTargets(startUser);
                System.out.printf(" User %d -> Groups %s (count=%d)%n", startUser, java.util.Arrays.toString(groups), groups.length);

                Set<Integer> rolesReached = new HashSet<>();
                for (int group : groups) {
                    int[] rList = groupToRole.getTargets(group);
                    System.out.printf(" Group %d -> Roles %s%n", group, java.util.Arrays.toString(rList));
                    for (int r : rList) {
                        rolesReached.add(r);
                    }
                }
                System.out.println("[+] Reached Role IDs for User 0: " + rolesReached);
            }
        }
        // 5. Shared Arena closes automatically, cleanly releasing off-heap memory
        System.out.println("[+] Off-heap graph snapshot memory closed successfully.");
    }
}
```

---

## Running the Application

Execute your compiled Java application directly using `java` with the required native access flags:

```bash
java --add-modules jdk.incubator.vector \
     --enable-native-access=ALL-UNNAMED \
     -cp "target/my-app-1.0.0.jar:target/dependency/*" \
     com.example.rbac.RbacSnapshotQueryExample
```

Or execute via Maven:

```bash
mvn exec:exec
```

---

## Summary Checklist

| Step | Action | Description |
| :--- | :--- | :--- |
| **1. Depend** | Add Maven Central dependencies | `org.impulsegraph:impulse-api`, `impulse-storage`, `impulse-vm` (`0.9.0`) |
| **2. Configure** | JVM flags | `--add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED` |
| **3. Load** | Zero-copy `mmap` off-heap | `BinarySnapshotLoader.loadSnapshot(path, arena)` |
| **4. Anchor** | Domain context | `DomainView userDomain = graph.domain("USER");` |
| **5. Traverse** | Kleisli pipeline propagation | `userDomain.from(0).out("userToGroup").out("groupToRole").toBitSet()` |

