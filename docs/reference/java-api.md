# Java API Reference (`impulse-graph-java`)

Welcome to the **Java 25 Foreign Function & Memory (FFM) API Reference** for the Impulse Graph Engine.

The Java engine is distributed on Maven Central across 3 decoupled modules:
* **`io.impulse.graph:impulse-api`**: Public interfaces, query AST builders, and ID mappers.
* **`io.impulse.graph:impulse-core`**: Off-heap Java 25 FFM CSR engine (zero external runtime dependencies).
* **`io.impulse.graph:impulse-spec`**: Java binary protocol layouts for C-ABI Spec v0.9.0.

---

## 1. Core API Contracts (`impulse-api`)

### `ImpulseGraphSnapshot`
The primary read-only binary snapshot interface. Provides lock-free, zero-copy access to immutable memory-mapped graph snapshots (`.imps`).

```java
try (Arena arena = Arena.ofShared()) {
    BinarySnapshotLoader.LoadedSnapshot loaded = BinarySnapshotLoader.loadSnapshot(Path.of("grid.imps"), arena);
    GraphSnapshot graph = loaded.graph();
    
    System.out.printf("Loaded %d relations, %d bytes off-heap%n", 
        graph.getAllRelationSnapshots().size(), 
        graph.getOffHeapMemorySizeBytes());
}
```

### `ImpulseGraph`
Active read-write graph interface combining an immutable `ImpulseGraphSnapshot` with dynamic `DeltaLayer` overlays for live mutations and hypothetical scenarios.

```java
liveGraph.addEdge("userToGroup", uAliceId, gEngineeringId);
liveGraph.removeEdge("userToGroup", uBobId, gEngineeringId); // Tombstone
```

### `ImpulseGraphQuery<R>` & `ImpulseQueryBuilder<R>`
Immutable Query AST contract and fluent builder for constructing type-safe graph traversals. Supports AST tree exports (`exportAst()`) and VM disassembly (`disassemble(snapshot)`).

```java
ImpulseGraphQuery<RoaringBitmap> userRolesQuery = ImpulseGraphQuery.builder()
    .input("USER", ArgType.ROARING_BITSET)
    .walkEdge("userToGroup")
    .walkEdge("groupToRole")
    .collect(ReturnType.ROARING_BITSET);

// Execute query (automatically compiled and cached via ImpulseQueryCompiler)
RoaringBitmap roleIds = userRolesQuery.execute(snapshot, userBitset);

// Debug AST tree and disassembler text
System.out.println(userRolesQuery.exportAst());
System.out.println(userRolesQuery.disassemble(snapshot));
```

### `TypedQueryBuilder<E, R>` & `SchemaCodeGenerator`
Strongly-typed base class and CodeGen tool (`org.impulsegraph.api.schema`). Generates compile-time type-checked Java query builders from a `GraphSchema` definition for full IDE auto-complete.

```java
// Define schema
GraphSchema schema = new GraphSchema(List.of(userEntity, groupEntity), List.of(userToGroupRel));

// Generate typed Java builder source code
SchemaCodeGenerator generator = new SchemaCodeGenerator("com.example.generated");
Map<String, String> classes = generator.generateClasses(schema);

// Use generated strongly-typed query builder in production code
ImpulseGraphQuery<BitSet> query = UserQueryBuilder.from(userKey)
    .walkUserToGroup()        // Auto-completed by IDE
    .walkGroupToRole()        // Auto-completed by IDE
    .collectRoaringBitset();
```

### `ImpulseQueryCompiler` & `CompiledQuery`
AST-to-Bytecode compiler located in `org.impulsegraph.vm`. Compiles AST steps into off-heap VM bytecode instructions (`impulse_instruction_t`) and JIT `MethodHandle` pipelines.

* **Zero-Delay Atomic Swaps**: Uses `AtomicReference<QueryBindingState>` for non-blocking lock-free reads during blue/green snapshot swaps.
* **Relation Verification & Re-binding**: `compiledQuery.rebind(newSnapshot)` verifies required logical relations exist on `newSnapshot`, updates physical instruction payloads, and atomically swaps binding state.

```java
ImpulseQueryCompiler.CompiledQuery compiled = ImpulseQueryCompiler.compile(query.getSteps(), snapshot, arena);

// Zero-delay blue/green swap
compiled.rebind(newSnapshot);

// Safely await active queries to drain and unload old snapshot memory
oldSnapshot.drainAndClose(5, TimeUnit.SECONDS);
```

### `SnapshotBuilder`
Streaming snapshot builder interface (`org.impulsegraph:impulse-builder`). Writes page-aligned C-ABI Spec v0.9.0 binary snapshots direct-to-disk or S3 in $O(\text{chunk})$ physical memory footprint.

```java
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
> For a complete soup-to-nuts walkthrough including JDBC data source integration and sparse matrix definitions, see the [Building Snapshots Guide](../getting-started/building-snapshots.md).

---

## 2. Multi-Type ID Mappers (`IdMapper<K>`)

Bi-directional mapping interface between external domain identifiers and internal 64-bit/32-bit dense node IDs:

| Class | Key Type (`K`) | Use Case |
| :--- | :--- | :--- |
| **`UuidIdMapper`** | `UUID` | 128-bit RFC 4122 UUIDs (e.g., SaaS entity IDs) |
| **`StringIdMapper`** | `String` | String business keys (e.g., `"USER#10492"`, `"group_admin"`) |
| **`LongIdMapper`** | `Long` | 64-bit database primary keys / Twitter Snowflake IDs |
| **`BytesIdMapper`** | `byte[]` | Raw 16-byte binary keys or SHA-256 hashes |

```java
IdMapper<UUID> userMapper = new UuidIdMapper("USER");
long denseId = userMapper.getOrAssignId(UUID.fromString("550e8400-e29b-41d4-a716-446655440000"));
UUID originalUuid = userMapper.getExternalKey(denseId);
```

---

## 3. Off-Heap Kernel Primitives (`impulse-core`)

### `RelationSnapshot`
High-performance off-heap CSR container for a single edge relation (e.g., `userToGroup`), backed by Java 25 `Arena` and off-heap `MemorySegment` row-offsets and column-targets.

### `DeltaLayer`
Thread-safe live mutation overlay tracking added edges (`Map<Integer, int[]>`) and tombstones (`RoaringBitmap`) layered over an immutable `RelationSnapshot`.

### `GraphSnapshot`
Multi-relation graph container mapping relation names (e.g., `"userToGroup"`, `"groupToRole"`) to their underlying `RelationSnapshot` instances and `DeltaLayer` overlays. Tracks active in-flight queries via `LongAdder activeQueryCount` for safe epoch draining (`drainAndClose()`).

### `SnapshotSwapManager<T>`
Generic epoch-tracked A/B pointer swap manager. Enables zero-downtime atomic snapshot rotation with active reader tracking so old off-heap `Arena` memory segments can be safely closed without race conditions.

```java
SnapshotSwapManager<GraphSnapshot> swapManager = new SnapshotSwapManager<>(initialGraph);

// Reader thread
try (var holder = swapManager.acquireCurrent()) {
    GraphSnapshot current = holder.getResource();
    // Perform lock-free query...
} // Reader automatically decrements epoch reference counter

// Writer thread: Atomic A/B pointer swap
swapManager.swap(newGraphSnapshot);
```

---

## 4. Binary Snapshot Loader (`BinarySnapshotLoader`)

Conforms 100% to **C-ABI Binary Snapshot Specification v0.9.0**:
* Direct-to-memory-mapped binary loader.
* Validates SHA-256 payload checksums.
* Supports SIMDComp / PFOR-Delta (`0x04`), Delta-VByte (`0x01`), UINT16 (`0x02`), HYBRID (`0x03`), RAW_UINT64 (`0x07`), and RAW_UINT32 (`0x00`) encodings.

---

## 5. Auto-Generating Multi-Module Javadocs

All public classes across `impulse-api`, `impulse-core`, `impulse-spec`, and `impulse-codegen` contain structured Javadoc comments.

To build the aggregated HTML Javadoc site across all Java modules:

```bash
cd impulse-graph-java
mvn javadoc:aggregate
```

The output Javadoc site will be generated at `impulse-graph-java/target/site/apidocs/index.html`.

