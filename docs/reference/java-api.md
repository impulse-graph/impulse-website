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
| [**`org.impulsegraph.vm`**](/javadoc/org/impulsegraph/vm/package-summary.html) | `impulse-vm` | `ImpulseVmInterpreter`, `ImpulseVmValidator`, `ImpulseMethodHandleCompiler`, `CompiledQuery`, `VmQueryContext`, `VmLaneFrontier`, `VmMultiLaneHandlers` |
| [**`org.impulsegraph.compiler.ast`**](/javadoc/org/impulsegraph/compiler/ast/package-summary.html) · [**`cypher`**](/javadoc/org/impulsegraph/compiler/cypher/package-summary.html) · [**`cel`**](/javadoc/org/impulsegraph/compiler/cel/package-summary.html) · [**`passes`**](/javadoc/org/impulsegraph/compiler/passes/package-summary.html) · [**`emitter`**](/javadoc/org/impulsegraph/compiler/emitter/package-summary.html) | `impulse-compiler` | Multi-pass `ImpScheme` / `openCypher` / `CEL` compiler, Stage 1 & Stage 2 passes, and bytecode emitter |
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
ImpulseBitSet highSpendProducts = users.from(1L, 2L, 3L)
    .outWithState("PURCHASED", "state.total_spend:SUM = edge.amount")
    .project("state.spend_with_tax = state.total_spend * 1.08")
    .filter("state.spend_with_tax >= 100.0")
    .toBitSet();
```

See [State Projections, Reducers & Loops](../query-api/advanced-querying.md) for the full list of monoidic `:MIN`, `:MAX`, `:SUM`, `:AVG`, `:ARGMIN`, and `:ARGMAX` reducers.

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
        "RETURN p")) {

    stmt.bindString("userKey", "usr_alice")
        .bindDouble("maxPrice", 99.95);

    try (RowReader rows = stmt.execute()) {
        while (rows.next()) {
            long productDenseId = rows.getNodeId(0);
        }
    }
}
```

---

## 4. Multi-Lane Bit-Sliced Execution & Pool Management (`org.impulsegraph.vm`) [Planned v0.9.1]

In `v0.9.1`, `org.impulsegraph.vm` implements the **Multi-Lane Bit-Sliced Execution (`0xC0..0xC9`)** and **Hybrid Vector ANN (`0xCA..0xCB`)** ISA extensions with zero hot-path heap allocations via thread-local `VmQueryContext` buffer pools.

### 4.1 `VmLaneFrontier` & `LaneWidth` (`TYPE_LANE_FRONTIER = 0x10`)
`VmLaneFrontier` represents a pooled vertical bit-sliced frontier where each node $u \in [0, N_d)$ holds up to 64 parallel lane bits alongside optional per-relation counterfactual edge trip masks:

* **`VmLaneFrontier.LaneWidth`**: Hardware width tiers **`WIDTH_8(8)`**, **`WIDTH_16(16)`**, **`WIDTH_32(32)`**, and **`WIDTH_64(64)`**.
* **`VmLaneFrontier.selectLaneWidth(int k)`**: Selects the narrowest tier capable of holding `k` active lanes (`WIDTH_8` for $k \le 8$, `WIDTH_16` for $k \le 16$, `WIDTH_32` for $k \le 32$, `WIDTH_64` for $k > 32$).
* **`VmLaneFrontier.NORMATIVE_BOUNDARY_SEED_COUNTS`**: The 17 normative boundary lane counts `{0, 1, 7, 8, 9, 15, 16, 17, 31, 32, 33, 63, 64, 65, 127, 128, 129}` used across polyglot verification suites to guard width transitions and 32/64-bit shift boundaries.
* **Counterfactual Edge Trip Masks**: `ensureEdgeTripMask(VmQueryContext ctx, int relId, int minEdges)` (or `setEdgeTripMask`), `getEdgeTripMask(int relId)`, `getEdgeTripMaskLength(int relId)`, and `copyEdgeTripMasksFrom(VmQueryContext ctx, VmLaneFrontier src)` manage per-edge bitmasks (`tripArr[e] |= (1L << laneB)`) for simultaneous $N-1$/$N-2$ outage screening (`OP_LANE_SET_EDGE_MASK` `0xC2`).

### 4.2 `VmQueryContext` Pooling & `VmMultiLaneHandlers`
`VmQueryContext` pools `VmLaneFrontier` instances via thread-local arenas (`TL_BUFFER_POOL`) so multi-lane steps execute with zero GC pressure:

```java
try (VmQueryContext ctx = VmQueryContext.acquire(snap, arena)) {
    int k = 16;
    VmLaneFrontier.LaneWidth width = VmLaneFrontier.selectLaneWidth(k); // WIDTH_16
    long activeMask = VmRegisterType.VmRegType.makeActiveMaskU64(k);    // 0xFFFFL
    int handle = ctx.acquireLaneFrontier(width, k, activeMask, nodeCount);

    VmLaneFrontier frontier = ctx.getLaneFrontier(handle);
    // Execute 0xC0..0xCB instructions via VmMultiLaneHandlers.handleMultiLaneOpcode(state, ctx, instr, pc)
}
```

| Class / Method | Purpose |
| :--- | :--- |
| **`VmQueryContext.acquireLaneFrontier(width, numLanes, activeMask, nodeCount)`** | Acquires and resets a pooled `VmLaneFrontier` from the thread-local buffer pool and returns its integer handle. |
| **`VmQueryContext.getLaneFrontier(int handle)`** | Resolves a `TYPE_LANE_FRONTIER` (`0x10`) register handle to its `VmLaneFrontier` instance. |
| **`VmMultiLaneHandlers.requireLaneFrontier(state, ctx, regIndex)`** | Exhaustive switch-checked extractor that validates `T_LANE_FRONTIER` (`0x10`) in `R[regIndex]` or traps with `IMPULSE_VM_ERR_INVALID_REGISTER`. |
| **`VmMultiLaneHandlers.handleMultiLaneOpcode(state, ctx, instr, pc)`** | Executes opcodes `0xC0` (`OP_LANE_INIT_SEEDS`) through `0xCB` (`OP_VECTOR_RERANK_DOT`) with 100% bitwise parity against C++20 and the OCaml oracle. |

---

## 5. Streaming Snapshot Builder & Blue/Green Swaps

### 5.1 `SnapshotBuilder` (`org.impulsegraph:impulse-builder`)
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

### 5.2 `SnapshotSwapManager<T>` (`org.impulsegraph:impulse-storage`)
Epoch-tracked atomic A/B pointer swap manager for rotating live `.imps` snapshots without blocking active reader threads:

```java
SnapshotSwapManager<GraphSnapshot> swapManager = new SnapshotSwapManager<>(initialGraph);

// Reader thread: zero-lock epoch acquisition
var holder = swapManager.acquireCurrent();
if (holder != null) {
    try {
        GraphSnapshot current = holder.getResource();
        // Execute lock-free traversal...
    } finally {
        holder.release();
    }
}

// Background updater thread: atomic pointer swap
swapManager.swap(newGraphSnapshot);
```

---

## 6. JVM Languages (Kotlin & Scala 3) & Build Plugins

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
                <goals>
                    <goal>generate</goal>
                </goals>
            </execution>
        </executions>
        <configuration>
            <schemaFile>${project.basedir}/src/main/resources/schema.yaml</schemaFile>
            <outputDirectory>${project.build.directory}/generated-sources/impulse</outputDirectory>
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
        outputDirectory = layout.buildDirectory.dir("generated/sources/impulse").get().asFile
        packageName = "com.example.graph.generated"
    }
    ```
