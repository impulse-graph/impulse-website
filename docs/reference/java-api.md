# Java API Reference (`impulse-graph-java`)

Welcome to the **Java 25 Foreign Function & Memory (FFM) API Reference** for the Impulse Graph Engine.

The Java engine is distributed on Maven Central across 3 decoupled modules:
* **`io.impulse.graph:impulse-api`**: Public interfaces, query AST builders, and ID mappers.
* **`io.impulse.graph:impulse-core`**: Off-heap Java 25 FFM CSR engine (zero external runtime dependencies).
* **`io.impulse.graph:impulse-spec`**: Java binary protocol layouts for C-ABI Spec v2.4.

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
Immutable Query AST contract and fluent builder for constructing type-safe graph traversals.

```java
ImpulseGraphQuery<RoaringBitmap> userRolesQuery = ImpulseGraphQuery.builder()
    .input("USER", ArgType.ROARING_BITSET)
    .walkEdge("userToGroup")
    .walkEdge("groupToRole")
    .collect(ReturnType.ROARING_BITSET);

RoaringBitmap roleIds = userRolesQuery.execute(snapshot, userBitset);
```

### `SnapshotBuilder`
Streaming snapshot compactor interface. Compacts live graph states and writes page-aligned C-ABI Spec v2.4 binary files direct-to-disk in $O(\text{chunk})$ physical memory footprint.

```java
SnapshotBuilder builder = new DefaultSnapshotBuilder();
ImpulseGraphSnapshot newSnapshot = builder.buildSnapshot(liveGraph, Path.of("compacted_v2.imps"));
```

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
Multi-relation graph container mapping relation names (e.g., `"userToGroup"`, `"groupToRole"`) to their underlying `RelationSnapshot` instances and `DeltaLayer` overlays.

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

Conforms 100% to **C-ABI Binary Snapshot Specification v2.4**:
* Direct-to-memory-mapped binary loader.
* Validates SHA-256 payload checksums.
* Supports SIMDComp / PFOR-Delta (`0x04`), Delta-VByte (`0x01`), UINT16 (`0x02`), HYBRID (`0x03`), RAW_UINT64 (`0x07`), and RAW_UINT32 (`0x00`) encodings.
