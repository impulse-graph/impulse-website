# Java 25 SDK Reference (`impulse-graph-java`)

The **Pure Java 25 Engine** (`impulse-graph-java`) is a standalone, zero-dependency implementation of the Impulse Graph Engine and `ImpulseVM`. It uses the Java 25 Foreign Function & Memory (FFM) API (`MemorySegment`, `Arena`) to mount `.imps` binary snapshots directly off-heap, combined with the Vector API (`jdk.incubator.vector`) and `MethodHandle` C2 JIT combinators.

Because graph traversals over 128-byte-aligned CSR/CSC arrays are primarily **memory-bandwidth and cache-line bound**, `impulse-graph-java` executes within **`1.5x–2.0x` of the Native C++20 kernel** (specifically **`1.65x`** on 1.47B-edge `twitter-2010` BFS: `240.29 ms` Java vs. `145.00 ms` C++) with a **JFR-verified zero-allocation hot path** (`0.00 ms` GC pauses). In enterprise microservices, JFR profiling shows that Jackson JSON serialization of the query response (`1.91 µs – 2.56 µs`) consumes **`3.5x to 73x` more CPU time** than the Impulse Graph query itself (`0.026 µs – 0.552 µs`)—making Pure Java 25 wholly suitable for demanding enterprise workloads without JNI wrappers or inherited CVEs. See **[Benchmarks](../benchmarks.md)** for full details.

!!! info "Interactive Aggregated Javadocs"
    Browse the full multi-module HTML Javadoc site at [**`/javadoc/index.html`**](/javadoc/index.html).

| Javadoc Package | Module | Description |
| :--- | :--- | :--- |
| [**`org.impulsegraph.api`**](/javadoc/org/impulsegraph/api/package-summary.html) | `impulse-api` | `ImpulseGraphSnapshot`, `RelationSnapshot`, `ImpulseGraphQuery`, `IdMapper<K>` |
| [**`org.impulsegraph.api.traversal`**](/javadoc/org/impulsegraph/api/traversal/package-summary.html) | `impulse-api` | Kleisli frontier pipeline (`DomainView`, `Traversal<T>`, `Reducer`) |
| [**`org.impulsegraph.api.statement`**](/javadoc/org/impulsegraph/api/statement/package-summary.html) | `impulse-api` | SQLite-style prepared statements (`ImpulseStatement`, `RowReader`) |
| [**`org.impulsegraph.api.bitset`**](/javadoc/org/impulsegraph/api/bitset/package-summary.html) | `impulse-api` | Zero-copy off-heap bitsets (`ImpulseBitSet`, `OffHeapBitSet`) |
| [**`org.impulsegraph.storage.csr`**](/javadoc/org/impulsegraph/storage/csr/package-summary.html) | `impulse-storage` | `BinarySnapshotLoader`, `GraphSnapshot`, `SnapshotSwapManager` |
| [**`org.impulsegraph.vm`**](/javadoc/org/impulsegraph/vm/package-summary.html) | `impulse-vm` | `ImpulseVmInterpreter`, `ImpulseVmValidator`, `ImpulseMethodHandleCompiler`, `CompiledQuery` |
| [**`org.impulsegraph.compiler`**](/javadoc/org/impulsegraph/compiler/package-summary.html) | `impulse-compiler` | Multi-pass `ImpScheme` / `openCypher` / `CEL` compiler, Stage 1 & Stage 2 passes |
| [**`org.impulsegraph.builder.api`**](/javadoc/org/impulsegraph/builder/api/package-summary.html) | `impulse-builder` | Streaming `SnapshotBuilder`, `DomainDefinition`, `RelationDefinition` |
| [**`org.impulsegraph.spec.v0_9`**](/javadoc/org/impulsegraph/spec/v0_9/package-summary.html) | `impulse-spec` | Binary Snapshot Format FFM memory layouts and protocol constants |

---

## 1. Maven & Gradle Coordinates (`org.impulsegraph`)

=== "Maven (`pom.xml`)"
    ```xml
    <dependencies>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-api</artifactId>
            <version>${impulse.version}</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-storage</artifactId>
            <version>${impulse.version}</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-vm</artifactId>
            <version>${impulse.version}</version>
        </dependency>
        <dependency>
            <groupId>org.impulsegraph</groupId>
            <artifactId>impulse-compiler</artifactId>
            <version>${impulse.version}</version>
        </dependency>
    </dependencies>
    ```

=== "Gradle (`build.gradle.kts`)"
    ```kotlin
    dependencies {
        implementation("org.impulsegraph:impulse-api:$impulseVersion")
        implementation("org.impulsegraph:impulse-storage:$impulseVersion")
        implementation("org.impulsegraph:impulse-vm:$impulseVersion")
        implementation("org.impulsegraph:impulse-compiler:$impulseVersion")
    }
    ```

---

## 2. Snapshot Loading & Domain-Bound Traversals

### 2.1 `BinarySnapshotLoader` & `ImpulseGraphSnapshot`
Mounts an immutable `.imps` file directly off-heap inside a `java.lang.foreign.Arena`:

```java
import java.lang.foreign.Arena;
import java.nio.file.Path;
import org.impulsegraph.api.ImpulseGraphSnapshot;
import org.impulsegraph.storage.csr.BinarySnapshotLoader;

try (Arena arena = Arena.ofShared()) {
    ImpulseGraphSnapshot snap =
        BinarySnapshotLoader.loadSnapshot(Path.of("social.imps"), arena).getGraph();

    System.out.printf("Domains: %s, Relations: %d, Off-Heap Bytes: %d%n",
        snap.getDomainNames(), snap.getRelationCount(), snap.getOffHeapMemorySizeBytes());
}
```

### 2.2 `DomainView` & `Traversal<T>`
Every traversal anchors to an explicit domain (`snap.domain("User")`), establishing the 0-indexed dense ID space $0 \dots N_d-1$:

```java
DomainView users = snap.domain("User");

// 1. Seed from business key, walk edge, and filter with CEL
List<String> friendKeys = users.fromKey("usr_alice")
    .out("FOLLOWS")
    .filter("node.age >= 21 && node.active == true")
    .toKeyList();

// 2. Unbounded fixed-point reachability (transitive closure)
Set<Long> reachableGroups = users.from(42L)
    .out("MEMBER_OF")
    .repeatUntilStable("PARENT_GROUP")
    .toSet();

// 3. Monoidic state projection and reduction
ImpulseBitSet targetBitSet = users.from(1L, 2L, 3L)
    .out("PURCHASED", Reducer.OR)
    .toBitSet();
```

| Interface | Core Methods |
| :--- | :--- |
| **`DomainView`** | `all()`, `from(long...)`, `from(ImpulseBitSet)`, `fromKey(String)`, `fromKeys(String...)`, `first(int)`, `fromRandom(int)`, `toDenseId(String)`, `toKey(long)` |
| **`Traversal<T>`** | `.filter(cel)`, `.project(cel)`, `.withParam(k, v)`, `.out(rel)`, `.out(rel, cel)`, `.out(rel, Reducer)`, `.outWithState(rel, stateExpr)`, `.in(rel)`, `.repeatUntilStable(rel)`, `.repeatUntilStable(rel, cel)`, `.repeat(n, rel)`, `.toBitSet()`, `.toList()`, `.toSet()`, `.toKeyList()`, `.toKeySet()`, `.count()`, `.toImpAsm()` |

---

## 3. Prepared Statements (`ImpulseStatement` & `RowReader`)

`snap.prepare(String query)` compiles an `openCypher`, `ImpScheme`, or `CEL` query once into a reusable `ImpulseStatement`:

```java
try (ImpulseStatement stmt = snap.prepare(
        "MATCH (u:User)-[:PURCHASED]->(p:Product) " +
        "WHERE u._key = $userKey AND p.price <= $maxPrice " +
        "RETURN p._id, p.price")) {

    stmt.bindString("userKey", "usr_alice")
        .bindDouble("maxPrice", 99.95);

    try (RowReader rows = stmt.execute()) {
        while (rows.next()) {
            long productId = rows.getNodeId(0);
            double price   = rows.getDouble(1);
        }
    }
}
```

---

## 4. Streaming Snapshot Builder & Blue/Green Swaps

### 4.1 `SnapshotBuilder` (`org.impulsegraph:impulse-builder`)
Streams page-aligned, 128-byte-aligned `.imps` snapshots direct-to-disk in $O(\text{chunk})$ memory (see [Building Snapshots (Java)](../getting-started/building-snapshots.md)):

```java
SnapshotBuilder.create()
    .withStagingDirectory(Path.of("/tmp/staging"))
    .addDomain("User", DomainDefinition.builder(100_000L).idWidth(PrimitiveWidth.UINT32).build())
    .addRelation("KNOWS", RelationDefinition.builder("User", "User")
        .addTopology(Topology.CSR, CompressionScheme.RAW)
        .dataSource(edgeDataSource).build())
    .writeTo(Path.of("graph.imps"));
```

### 4.2 `SnapshotSwapManager<T>` (`org.impulsegraph:impulse-storage`)
Epoch-tracked atomic A/B pointer swap manager for rotating live `.imps` snapshots without blocking active reader threads:

```java
SnapshotSwapManager<GraphSnapshot> swapManager = new SnapshotSwapManager<>(initialGraph);

// Reader thread: zero-lock epoch acquisition
try (var holder = swapManager.acquireCurrent()) {
    GraphSnapshot current = holder.getResource();
    // Execute lock-free traversal...
}

// Background updater thread: atomic pointer swap
swapManager.swap(newGraphSnapshot);
```

---

## 5. JVM Languages (Kotlin & Scala 3) & Build Plugins

Because `impulse-api` uses standard Java 25 interfaces without checked exceptions or runtime lambdas, it is directly usable from **Kotlin** (`org.impulsegraph:impulse-kotlin`) and **Scala 3** (`org.impulsegraph:impulse-scala_3`).

### Maven & Gradle Schema Code Generation (`impulse-codegen`)
To generate strongly-typed domain views and POJOs from a declarative [`.imps.schema.yaml`](spec/schema-specification.md) file during your build:

=== "Maven (`impulse-maven-plugin`)"
    ```xml
    <plugin>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-maven-plugin</artifactId>
        <version>${impulse.version}</version>
        <executions>
            <execution>
                <goals><goal>generate</goal></goals>
            </execution>
        </executions>
        <configuration>
            <schemaFile>src/main/resources/schema.yaml</schemaFile>
            <packageName>com.example.graph.generated</packageName>
        </configuration>
    </plugin>
    ```

=== "Gradle (`impulse-gradle-plugin`)"
    ```kotlin
    plugins {
        id("org.impulsegraph.impulse") version "$impulseVersion"
    }

    impulse {
        schemaFile = file("src/main/resources/schema.yaml")
        packageName = "com.example.graph.generated"
    }
    ```
