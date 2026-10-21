# Pure Java 25 Engine API Reference (`impulse-graph-java`)

This reference documents the **Pure Java 25 Engine** located in `impulse-graph-java`.

The Java 25 engine is a **first-class, 100% pure Java implementation** of the Impulse Graph Engine and `ImpulseVM`—not a JNI or FFI wrapper around C++. It uses the Java 25 Foreign Function & Memory (FFM) API (`MemorySegment`, `Arena`) to mount `.imps` binary snapshots directly off-heap, combined with the Vector API (`jdk.incubator.vector`) and a **Lua-inspired register VM compiled via `MethodHandle` JIT combinators**:

* **Zero External Runtime Dependencies**: Core runtime modules have zero third-party dependencies.
* **Zero GC Pauses**: All CSR/CSC matrices, SoA attributes, bitsets, and the 640-byte `ImpulseVM` register frame live off-heap.
* **`MethodHandle` Combinator C2 JIT Fusion (`ImpulseMethodHandleCompiler` & `ShaderCompiler`)**: Binds decoded `impOps` instruction operands and stream-walk shaders into `java.lang.invoke.MethodHandle` trees (`insertArguments` / `foldArguments`), allowing HotSpot's C2 JIT compiler to constant-fold register indices and inline query pipelines without interpreter loop overhead.
* **100% Equivalence with the C++ C-ABI Engine**: Reads the exact same `.imps` binary snapshot format and executes the exact same `impOps` bytecode ISA with bitwise-identical output.

!!! info "Interactive Aggregated Javadocs"
    Browse the full multi-module HTML Javadoc site at [**`/javadoc/index.html`**](/javadoc/index.html).

| Javadoc Package | Module | Description |
| :--- | :--- | :--- |
| [**`org.impulsegraph.api`**](/javadoc/org/impulsegraph/api/package-summary.html) | `impulse-api` | `ImpulseGraphSnapshot`, `RelationSnapshot`, `ImpulseGraphQuery`, `IdMapper<K>` |
| [**`org.impulsegraph.api.traversal`**](/javadoc/org/impulsegraph/api/traversal/package-summary.html) | `impulse-api` | Kleisli frontier pipeline (`DomainView`, `Traversal<T>`, `Reducer`) |
| [**`org.impulsegraph.api.statement`**](/javadoc/org/impulsegraph/api/statement/package-summary.html) | `impulse-api` | SQLite-style prepared statements (`ImpulseStatement`, `RowReader`) |
| [**`org.impulsegraph.api.bitset`**](/javadoc/org/impulsegraph/api/bitset/package-summary.html) | `impulse-api` | Zero-copy off-heap bitsets (`ImpulseBitSet`, `OffHeapBitSet`) |
| [**`org.impulsegraph.api.stats`**](/javadoc/org/impulsegraph/api/stats/package-summary.html) | `impulse-api` | Catalog statistics (`GraphStatistics`, `RelationStatistics`, `AttributeStatistics`) |
| [**`org.impulsegraph.api.metrics`**](/javadoc/org/impulsegraph/api/metrics/package-summary.html) | `impulse-api` | JMX `ImpulseEngineMXBean` and `PrometheusMetricsExporter` |
| [**`org.impulsegraph.storage.csr`**](/javadoc/org/impulsegraph/storage/csr/package-summary.html) | `impulse-storage` | `BinarySnapshotLoader`, `GraphSnapshot`, `DeltaLayer`, `SnapshotSwapManager` |
| [**`org.impulsegraph.vm`**](/javadoc/org/impulsegraph/vm/package-summary.html) | `impulse-vm` | `ImpulseVmInterpreter`, `ImpulseVmValidator`, `ImpulseMethodHandleCompiler`, `CompiledQuery` |
| [**`org.impulsegraph.compiler`**](/javadoc/org/impulsegraph/compiler/package-summary.html) | `impulse-compiler` | Multi-pass `ImpScheme` / `openCypher` / `CEL` compiler, Stage 1 & Stage 2 passes |
| [**`org.impulsegraph.builder.api`**](/javadoc/org/impulsegraph/builder/api/package-summary.html) | `impulse-builder` | Streaming `SnapshotBuilder`, `DomainDefinition`, `RelationDefinition` |
| [**`org.impulsegraph.spec.v0_9`**](/javadoc/org/impulsegraph/spec/v0_9/package-summary.html) | `impulse-spec` | Binary Snapshot Format FFM memory layouts and protocol constants |

---

## 1. Maven Module Architecture (`org.impulsegraph`)

The Pure Java 25 engine is partitioned into 6 core modules under groupId `org.impulsegraph`:

* **`org.impulsegraph:impulse-spec`**: Binary Snapshot Format FFM memory layouts and opcode constants.
* **`org.impulsegraph:impulse-api`**: Public interfaces (`ImpulseGraphSnapshot`, `DomainView`, `Traversal`, `ImpulseStatement`, `RowReader`), AST nodes (`ImpScmNode`), and ID mappers.
* **`org.impulsegraph:impulse-storage`**: Zero-dependency off-heap Java 25 FFM CSR/CSC snapshot loader (`BinarySnapshotLoader`), `DeltaLayer`, secondary indices, and catalog statistics.
* **`org.impulsegraph:impulse-vm`**: Register-based `ImpulseVM` interpreter, `MethodHandle` JIT combinators, off-heap `VmStateLayout` (640-byte frame), and bytecode emitter.
* **`org.impulsegraph:impulse-compiler`**: Multi-pass query frontends (`openCypher`, `CEL`, `ImpScheme`), Stage 1/Stage 2 optimization passes, and `.impas` disassembler.
* **`org.impulsegraph:impulse-builder`**: Direct-to-disk streaming `.imps` snapshot builder.

---

## 2. Snapshot Loading & Domain-Bound Traversals (`impulse-api`)

### 2.1 `ImpulseGraphSnapshot` & `BinarySnapshotLoader`
Provides read-only access to memory-mapped `.imps` snapshot files backed by a `java.lang.foreign.Arena`:

```java
import java.lang.foreign.Arena;
import java.nio.file.Path;
import org.impulsegraph.api.ImpulseGraphSnapshot;
import org.impulsegraph.storage.csr.BinarySnapshotLoader;

try (Arena arena = Arena.ofShared()) {
    BinarySnapshotLoader.LoadedSnapshot loaded =
        BinarySnapshotLoader.loadSnapshot(Path.of("social.imps"), arena);
    ImpulseGraphSnapshot snap = loaded.getGraph();

    System.out.printf("Domains: %s, Relations: %d, Off-Heap Bytes: %d%n",
        snap.getDomainNames(),
        snap.getRelationCount(),
        snap.getOffHeapMemorySizeBytes());
}
```

### 2.2 `DomainView` & Kleisli `Traversal<T>`
All traversals bind an explicit domain anchor (`snap.domain("User")`), establishing the 0-indexed dense ID space $0 \dots N_d-1$ for that domain:

```java
import java.util.List;
import java.util.Set;
import org.impulsegraph.api.bitset.ImpulseBitSet;
import org.impulsegraph.api.traversal.DomainView;
import org.impulsegraph.api.traversal.Reducer;

DomainView users = snap.domain("User");

// 1. Seed from external business key or dense IDs, filter with CEL, and walk edges
List<String> friendKeys = users
    .fromKey("usr_alice")
    .out("FOLLOWS")
    .filter("node.age >= 21 && node.active == true")
    .toKeyList();

// 2. Unbounded fixed-point reachability (transitive closure)
Set<Long> reachableGroups = users
    .from(42L)
    .out("MEMBER_OF")
    .repeatUntilStable(step -> step.out("PARENT_GROUP"))
    .toSet();

// 3. Monoidic reduction and off-heap BitSet materialization
ImpulseBitSet targetBitSet = users
    .from(1L, 2L, 3L)
    .out("PURCHASED", Reducer.OR)
    .toBitSet();
```

#### `DomainView` Entrypoints
* `all()`: Anchor frontier to all nodes $0 \dots N_d-1$ in the domain.
* `from(long nodeId)` / `from(long... nodeIds)` / `from(ImpulseBitSet bitset)`: Seed frontier from dense node IDs.
* `fromKey(String key)` / `fromKeys(String... keys)`: Resolve external primary keys via the domain's key catalog and seed the frontier.
* `first(int n)` / `fromRandom(int n)`: Seed with the first $n$ nodes or a uniform random sample of $n$ nodes.
* `toDenseId(String key)` / `toKey(long denseId)`: Direct bidirectional key resolution.

#### `Traversal<T>` Operations & Terminals
* **In-Domain Endomorphisms**: `.filter(String celPredicate)`, `.project(String projectionExpr)`, `.withParam(String key, Object value)`
* **Cross-Domain Steps**: `.out(String relation)`, `.out(String relation, String edgePredicate)`, `.out(String relation, Reducer reducer)`, `.outWithState(String relation, String stateProjections)`, `.in(String relation)` (reverse CSC walk)
* **Fixed-Point & Bounded Loops**: `.repeatUntilStable(stepFn)`, `.repeat(int iterations, stepFn)`
* **Terminals**: `.toBitSet()`, `.toList()`, `.toSet()`, `.toKeyList()`, `.toKeySet()`, `.count()`, `.collect()`, `.toImpAsm()`

---

## 3. Parameterized Prepared Statements (`ImpulseStatement` & `RowReader`)

`snap.prepare(String query)` compiles an `openCypher`, `ImpScheme`, or `CEL` query once into an `ImpulseStatement` that can be repeatedly bound and executed with zero recompilation:

```java
import org.impulsegraph.api.statement.ImpulseStatement;
import org.impulsegraph.api.statement.RowReader;

try (ImpulseStatement stmt = snap.prepare(
        "MATCH (u:User)-[:PURCHASED]->(p:Product) " +
        "WHERE u.id = $userId AND p.price <= $maxPrice " +
        "RETURN p.id, p.price")) {

    stmt.bindNode("userId", 42L)
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

## 4. Streaming Snapshot Builder (`impulse-builder`)

`SnapshotBuilder` (`org.impulsegraph.builder.api`) streams page-aligned C-ABI Spec  `.imps` snapshots direct-to-disk in $O(\text{chunk})$ physical memory:

```java
import java.nio.file.Path;
import org.impulsegraph.builder.api.*;

DomainDefinition userDomain = DomainDefinition.builder(100_000L)
    .idWidth(PrimitiveWidth.UINT32)
    .withPrimaryKeyIndex(true)
    .build();

RelationDefinition knowsRel = RelationDefinition.builder("User", "User")
    .addTopology(Topology.CSR, CompressionScheme.RAW)
    .addTopology(Topology.CSC, CompressionScheme.RAW)
    .dataSource(edgeDataSource)
    .build();

SnapshotBuilder.create()
    .withStagingDirectory(Path.of("/tmp/staging"))
    .addDomain("User", userDomain)
    .addRelation("KNOWS", knowsRel)
    .addFooterMetadata("environment", "production")
    .writeTo(Path.of("graph.imps"));
```

> [!TIP]
> See the [Building Snapshots Guide](../getting-started/building-snapshots.md) and [Snapshot Builder Reference](../getting-started/snapshot-builder-reference.md) for full JDBC and streaming ingestion examples.

---

## 5. Multi-Type ID Mappers (`IdMapper<K>`)

Bi-directional mapping interface between external domain identifiers and internal 0-indexed dense node IDs:

| Class | Key Type (`K`) | Use Case |
| :--- | :--- | :--- |
| **`UuidIdMapper`** | `UUID` | 128-bit RFC 4122 UUIDs |
| **`StringIdMapper`** | `String` | String business keys (`"USER#10492"`, `"DB00001"`) |
| **`LongIdMapper`** | `Long` | 64-bit database primary keys / Snowflake IDs |
| **`BytesIdMapper`** | `byte[]` | Raw binary keys or hashes |

---

## 6. Off-Heap Storage & Zero-Downtime Rotation (`impulse-storage`)

### `SnapshotSwapManager<T>`
Epoch-tracked atomic A/B pointer swap manager for rotating live `.imps` snapshots without blocking active reader threads:

```java
SnapshotSwapManager<GraphSnapshot> swapManager = new SnapshotSwapManager<>(initialGraph);

// Reader thread
try (var holder = swapManager.acquireCurrent()) {
    GraphSnapshot current = holder.getResource();
    // Execute lock-free traversal...
}

// Writer thread: Atomic A/B pointer swap
swapManager.swap(newGraphSnapshot);
```

---

## 7. Building Aggregated Javadocs Locally

To generate the multi-module HTML Javadoc site locally:

```bash
cd impulse-graph-java
mvn javadoc:aggregate -DskipTests
```

The output Javadoc site is written to `impulse-graph-java/target/site/apidocs/index.html`.
