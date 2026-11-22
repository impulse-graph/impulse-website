# Building Snapshots in Java

This guide covers building immutable `.imps` binary snapshots in pure Java using **`org.impulsegraph:impulse-builder`**. Depending on where your source data lives, Java provides two zero-dependency build paths:

1. **Programmatic Streaming (`SnapshotBuilder`)**: Stream rows directly from PostgreSQL/MySQL/Oracle via JDBC, Kafka state stores, or custom Java pipelines in bounded $O(\text{chunk})$ off-heap memory.
2. **Declarative Manifest Building (`CsvManifestSnapshotBuilder`)**: Compile CSV, TSV, and JSONL node/edge files from a declarative YAML or JSON manifest in pure Java without installing native binaries.

If you haven't already, read [Core Concepts](../../getting-started/core-concepts.md) first for an overview of CSR/CSC adjacency layouts and per-domain dense ID spaces.

!!! tip "Building from Apache Parquet or Attaching Vamana Vector Indices?"
    If your upstream tables are stored in **Apache Parquet**, `.npy` / `.safetensors` embeddings, or require offline RCM / Vamana ANN index construction, use the standalone native CLI (`impulse build`) documented in **[Snapshots from Parquet & CSV (CLI & Python)](../python/snapshots-from-parquet-csv.md)**. Because `.imps` is language-neutral, snapshots built by the native CLI mount directly in pure Java with zero conversion.

---

## What Are We Building?

Our relational database has four tables for a banking transfer graph:

| Table | Columns |
| :--- | :--- |
| `users` | `user_id BIGINT`, `name VARCHAR`, `age INT` |
| `accounts` | `account_id BIGINT`, `balance DOUBLE` |
| `user_accounts` | `user_id BIGINT`, `account_id BIGINT` |
| `account_transfers` | `from_account_id BIGINT`, `to_account_id BIGINT`, `amount DOUBLE` |

!!! note
    In a production banking schema, `account_transfers` also carries `timestamp` (`TIMESTAMP_MS`), `currency`, and `transfer_type`. Each column attaches to `TRANSFERRED_TO` as its own 128-byte-aligned Structure-of-Arrays (SoA) edge attribute column. Here we attach `amount` (`DataType.F64`) to keep the walkthrough concise.

Target graph topology:

```text
 (User: 101) ──[:OWNS]──> (Account: 5001) ──[:TRANSFERRED_TO {amount: 2500.00}]──> (Account: 7008)
```

Once built, we memory-map the `.imps` file and execute engine-native queries such as *"Which accounts received transfers over \$1,000 from accounts owned by User 101?"*.

---

## Project Dependencies & JVM Flags

Import `impulse-bom` (see the [Java & JVM Enterprise Hub](index.md#copy-paste-build-ide-container-setup) for full Maven/Gradle setup) and add `impulse-builder` alongside the core runtime modules:

```xml
<dependencies>
    <!-- Streaming SnapshotBuilder & CsvManifestSnapshotBuilder -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-builder</artifactId>
    </dependency>
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
</dependencies>
```

At runtime, pass `--add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED` to `java` (plus `--enable-preview` if running on **JDK 21 LTS**).

---

## Part 1: Programmatic JDBC Streaming (`SnapshotBuilder`)

### Step 1: Define Domains & Understand Natural Keys vs. Dense IDs

Entities in Impulse Graph are partitioned into **Domains** (here `User` and `Account`). Every domain has its own independent, contiguous 0-indexed dense ID space $0 \dots N_d - 1$, allowing CSR `row_offsets[]` and SoA attribute arrays to use direct array indexing with zero hash lookups.

!!! warning "Natural Keys vs. Ephemeral Dense IDs (0 .. N_d - 1)"
    Dense node IDs ($0 \dots N_d - 1$) are **ephemeral physical array indices** valid only for a single `.imps` snapshot revision. Whenever a snapshot is rebuilt—or reordered offline via Reverse Cuthill-McKee (`--rcm`) or degree sorting—a user's dense ID changes as rows are inserted or deleted.

    **Architectural Rule**: Never persist raw Impulse dense IDs into PostgreSQL, Kafka events, caches, or external API responses. Always persist your domain's immutable **natural business keys** (`UUID`, `Long`, or `String`) and translate at the query boundary via `.fromKey(...)` / `.toKeyList()` (or typed AOT `<Domain>DomainView` methods—see [Schema-First AOT Codegen](aot-codegen.md)).

During programmatic JDBC ingestion, **`IdMapper<K>`** (`LongIdMapper`, `UuidIdMapper`, `StringIdMapper`, `BytesIdMapper`) maps database primary keys to sequential dense IDs as you scan the domain table:

!!! important
    The `ORDER BY` in the domain scan query determines dense ID assignment order ($0, 1, 2, \dots$). When streaming CSR edges in a single pass (Step 4), the edge SQL query **must** `ORDER BY` its source foreign key in the exact same order so source dense IDs arrive monotonically non-decreasing.

```java
import org.impulsegraph.api.IdMapper;
import org.impulsegraph.api.LongIdMapper;
import org.impulsegraph.builder.api.DomainDefinition;
import org.impulsegraph.builder.api.PrimitiveWidth;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

IdMapper<Long> userMapper = new LongIdMapper("User");
long denseId = 0;

try (Statement stmt = conn.createStatement();
     ResultSet rs = stmt.executeQuery("SELECT user_id FROM users ORDER BY user_id")) {
    while (rs.next()) {
        userMapper.registerMapping(rs.getLong("user_id"), denseId++);
    }
}

DomainDefinition userDomain = DomainDefinition.builder(userMapper.size())
        .idWidth(PrimitiveWidth.UINT32) // UINT16 (<=65,535), UINT32 (<=4.29B), or UINT64
        .build();
```

### Step 2: Add the `Account` Domain

Apply the same pattern to `Account`:

```java
IdMapper<Long> accountMapper = new LongIdMapper("Account");
long accDenseId = 0;

try (Statement stmt = conn.createStatement();
     ResultSet rs = stmt.executeQuery("SELECT account_id FROM accounts ORDER BY account_id")) {
    while (rs.next()) {
        accountMapper.registerMapping(rs.getLong("account_id"), accDenseId++);
    }
}

DomainDefinition accountDomain = DomainDefinition.builder(accountMapper.size())
        .idWidth(PrimitiveWidth.UINT32)
        .withPrimaryKeyIndex(true)
        .primaryKeyAttribute("account_id")
        .addAttribute("account_id", accountKeySource)   // Optional AttributeDataSource for embedded key lookup
        .addAttribute("balance", accountBalanceSource)  // Optional SoA node attribute column
        .build();
```

!!! note "Disjoint Per-Domain ID Spaces"
    Dense ID `0` in `User` is distinct from and unrelated to dense ID `0` in `Account`. Every relation explicitly binds a `sourceDomain` and `targetDomain`.

#### Domains Without Attributes & High-Cardinality Memory Sizing

If a domain requires neither node attributes nor embedded key dictionaries, only its node count is required (`DomainDefinition.builder(accountCount).idWidth(PrimitiveWidth.UINT32).build()`).

When sizing builder memory for large graphs:

* **Off-Heap Topology & Column Streaming (`StreamingSnapshotWriter` & `ExternalSortStaging`)**: Streams pre-mapped dense IDs in fixed-size off-heap `MemorySegment` chunks (`65,536` edges per chunk) and spills intermediate CSC sort runs to disk whenever the staging buffer reaches `.withStagingMemoryLimit(...)` (default **64 MB**).
* **In-Memory `IdMapper<K>` Reference Classes**: `LongIdMapper`, `UuidIdMapper`, and `StringIdMapper` hold two `ConcurrentHashMap` instances on the Java heap (~120–200+ bytes per node), suitable up to ~10M–50M nodes depending on `-Xmx`.
* **Scaling Beyond 100M Nodes**: Pre-compute dense IDs in SQL/warehouse views (`ROW_NUMBER() OVER (ORDER BY id) - 1 AS dense_id`), implement `IdMapper<K>` over an off-heap sorted `MemorySegment` binary-search table, or run `impulse build` over Parquet exports (see [Snapshots from Parquet & CSV](../python/snapshots-from-parquet-csv.md)).

---

### Step 3: Stream Edges & Columnar Attributes via `RelationDataSource`

Rather than allocating Java edge objects on the heap, `SnapshotBuilder` pulls batches of primitive IDs into reusable off-heap `MemorySegment` buffers via **`RelationDataSource`** and **`EdgeChunkIterator`**. Remember to call `stmt.setFetchSize(10_000)` so the JDBC driver streams rows instead of buffering the entire table in heap memory:

```java
package com.example.builder;

import org.impulsegraph.api.IdMapper;
import org.impulsegraph.builder.spi.EdgeChunkIterator;
import org.impulsegraph.builder.spi.RelationDataSource;

import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class JdbcRelationDataSource implements RelationDataSource {

    private final Connection connection;
    private final String edgeQuery;
    private final long edgeCount;
    private final IdMapper<Long> sourceMapper;
    private final IdMapper<Long> targetMapper;

    public JdbcRelationDataSource(Connection connection,
                                  String countQuery,
                                  String edgeQuery,
                                  IdMapper<Long> sourceMapper,
                                  IdMapper<Long> targetMapper) throws SQLException {
        this.connection = connection;
        this.edgeQuery = edgeQuery;
        this.sourceMapper = sourceMapper;
        this.targetMapper = targetMapper;

        try (Statement stmt = connection.createStatement();
             ResultSet rs = stmt.executeQuery(countQuery)) {
            if (!rs.next()) {
                throw new IllegalStateException("Count query returned 0 rows");
            }
            this.edgeCount = rs.getLong(1);
        }
    }

    @Override
    public long getEdgeCount() {
        return edgeCount;
    }

    @Override
    public EdgeChunkIterator getEdges() {
        try {
            PreparedStatement stmt = connection.prepareStatement(
                    edgeQuery, ResultSet.TYPE_FORWARD_ONLY, ResultSet.CONCUR_READ_ONLY);
            stmt.setFetchSize(10_000);
            ResultSet rs = stmt.executeQuery();

            return new EdgeChunkIterator() {
                private boolean hasNextRow = rs.next();

                @Override
                public boolean hasNext() {
                    return hasNextRow;
                }

                @Override
                public int nextChunk(MemorySegment srcIds, MemorySegment tgtIds, int limit) {
                    int count = 0;
                    try {
                        int sWidth = limit > 0 ? (int) (srcIds.byteSize() / limit) : 4;
                        int tWidth = limit > 0 ? (int) (tgtIds.byteSize() / limit) : 4;

                        while (hasNextRow && count < limit) {
                            long srcDenseId = sourceMapper.getId(rs.getLong(1));
                            long tgtDenseId = targetMapper.getId(rs.getLong(2));

                            if (sWidth == 2) {
                                srcIds.setAtIndex(ValueLayout.JAVA_SHORT_UNALIGNED, count, (short) srcDenseId);
                            } else if (sWidth == 8) {
                                srcIds.setAtIndex(ValueLayout.JAVA_LONG_UNALIGNED, count, srcDenseId);
                            } else {
                                srcIds.setAtIndex(ValueLayout.JAVA_INT_UNALIGNED, count, (int) srcDenseId);
                            }

                            if (tWidth == 2) {
                                tgtIds.setAtIndex(ValueLayout.JAVA_SHORT_UNALIGNED, count, (short) tgtDenseId);
                            } else if (tWidth == 8) {
                                tgtIds.setAtIndex(ValueLayout.JAVA_LONG_UNALIGNED, count, tgtDenseId);
                            } else {
                                tgtIds.setAtIndex(ValueLayout.JAVA_INT_UNALIGNED, count, (int) tgtDenseId);
                            }

                            count++;
                            hasNextRow = rs.next();
                        }
                    } catch (SQLException e) {
                        throw new RuntimeException("Error reading JDBC edge row", e);
                    }
                    return count;
                }

                @Override
                public void close() throws Exception {
                    rs.close();
                    stmt.close();
                }
            };
        } catch (SQLException e) {
            throw new RuntimeException("Failed to initiate JDBC edge stream", e);
        }
    }
}
```

Stream the `amount` edge attribute in the **exact same SQL `ORDER BY` sequence** (`ORDER BY from_account_id, to_account_id`) via **`AttributeDataSource`** so element $k$ in `amount[]` aligns with edge $k$ in CSR `col_indices[]`:

```java
import org.impulsegraph.builder.api.DataType;
import org.impulsegraph.builder.api.Nullability;
import org.impulsegraph.builder.spi.AttributeChunkIterator;
import org.impulsegraph.builder.spi.AttributeDataSource;

AttributeDataSource transferAmountSource = new AttributeDataSource() {
    @Override
    public DataType dataType() {
        return DataType.F64;
    }

    @Override
    public Nullability nullability() {
        return Nullability.NON_NULL;
    }

    @Override
    public AttributeChunkIterator iterator() {
        try {
            PreparedStatement stmt = conn.prepareStatement(
                    "SELECT amount FROM account_transfers ORDER BY from_account_id, to_account_id",
                    ResultSet.TYPE_FORWARD_ONLY,
                    ResultSet.CONCUR_READ_ONLY);
            stmt.setFetchSize(10_000);
            ResultSet rs = stmt.executeQuery();

            return new AttributeChunkIterator() {
                private boolean hasNextRow = advanceOrClose();

                private boolean advanceOrClose() {
                    try {
                        boolean more = rs.next();
                        if (!more) {
                            rs.close();
                            stmt.close();
                        }
                        return more;
                    } catch (SQLException e) {
                        throw new RuntimeException("Error advancing transfer amount cursor", e);
                    }
                }

                @Override
                public boolean hasNext() {
                    return hasNextRow;
                }

                @Override
                public int nextChunk(MemorySegment destination, int limit) {
                    int count = 0;
                    try {
                        while (hasNextRow && count < limit) {
                            destination.setAtIndex(ValueLayout.JAVA_DOUBLE_UNALIGNED, count, rs.getDouble(1));
                            count++;
                            hasNextRow = advanceOrClose();
                        }
                    } catch (SQLException e) {
                        throw new RuntimeException("Error reading transfer amount", e);
                    }
                    return count;
                }
            };
        } catch (SQLException e) {
            throw new RuntimeException("Failed to stream transfer amounts", e);
        }
    }
};
```

---

### Step 4: Configure Relations & Write the Snapshot

Bind CSR (forward `.out(...)`) and optional CSC (reverse `.in(...)`) topologies to each `RelationDefinition`, attach `transferAmountSource`, stamp schema provenance metadata, and stream the `.imps` file to disk or directly to an S3/GCS `OutputStream`:

```java
import org.impulsegraph.builder.api.CompressionScheme;
import org.impulsegraph.builder.api.RelationDefinition;
import org.impulsegraph.builder.api.SnapshotBuilder;
import org.impulsegraph.builder.api.Topology;

import java.nio.file.Path;
import java.time.Instant;

RelationDataSource ownsDataSource = new JdbcRelationDataSource(
        conn,
        "SELECT COUNT(*) FROM user_accounts",
        "SELECT user_id, account_id FROM user_accounts ORDER BY user_id",
        userMapper,
        accountMapper
);

RelationDataSource transferDataSource = new JdbcRelationDataSource(
        conn,
        "SELECT COUNT(*) FROM account_transfers",
        "SELECT from_account_id, to_account_id FROM account_transfers ORDER BY from_account_id, to_account_id",
        accountMapper,
        accountMapper
);

RelationDefinition ownsRelation = RelationDefinition.builder("User", "Account")
        .addTopology(Topology.CSR, CompressionScheme.RAW)
        .addTopology(Topology.CSC, CompressionScheme.RAW)
        .dataSource(ownsDataSource)
        .build();

RelationDefinition transferRelation = RelationDefinition.builder("Account", "Account")
        .addTopology(Topology.CSR, CompressionScheme.RAW)
        .addTopology(Topology.CSC, CompressionScheme.RAW)
        .addAttribute("amount", transferAmountSource)
        .dataSource(transferDataSource)
        .build();

SnapshotBuilder.create()
        .withVersion((short) 10)
        .withStagingDirectory(Path.of("/tmp/impulse_staging"))
        .withStagingMemoryLimit(64 * 1024 * 1024L) // 64 MB external-sort spill threshold
        .addDomain("User", userDomain)
        .addDomain("Account", accountDomain)
        .addRelation("OWNS", ownsRelation)
        .addRelation("TRANSFERRED_TO", transferRelation)
        .withSchemaProvenance("BankGraph", "1.0.0", null)
        .addFooterMetadata("sys.build.generator", "BankGraphJdbcPipeline")
        .addFooterMetadata("sys.build.timestamp", Instant.now().toString())
        .writeTo(Path.of("datasets/bank_graph.imps"));
```

!!! tip "Type-Safe Generated Writer (`<Graph>SnapshotWriter`)"
    If you define a `.imps.schema.yaml` contract, `impulse-codegen` generates a typed `<Graph>SnapshotWriter` wrapper that pre-populates `impulse.schema.*` footer provenance, domain `PrimitiveWidth`, and relation `CSC` flags automatically. See [Schema-First Development & AOT Codegen](aot-codegen.md).

---

## Part 2: Declarative CSV / TSV / JSONL Builds (`CsvManifestSnapshotBuilder`)

!!! info "Version Note: v0.11 Tooling Suite"
    `CsvManifestSnapshotBuilder.buildV10Snapshot(...)` (streaming YAML/JSON manifest compilation over CSV, TSV, and JSONL inputs with domain/edge SoA attributes, vector columns, nullable bitmaps, and schema provenance metadata) is part of the **`v0.11`** pure-Java tooling suite (and powers `impulse-j build` and `impulse-maven-plugin:build-snapshot`).

When your upstream data is exported as **CSV, TSV, or JSONL** files—or when generating deterministic `.imps` test fixtures in CI—you do not need to write custom `RelationDataSource` iterators or install a native binary. `CsvManifestSnapshotBuilder` compiles a declarative `manifest.yaml` (or `manifest.json`) directly to a 128-byte-aligned `.imps` snapshot in pure Java:

### Example `manifest.yaml`

```yaml
schema_name: BankGraph
schema_version: "1.0.0"

domains:
  - id: 0
    name: User
    id_width: uint32
    key_type: int64
    id_column: user_id
    file: domains/users.csv
    attributes:
      - name: name
        type: string
      - name: age
        type: int32?

  - id: 1
    name: Account
    id_width: uint32
    key_type: int64
    id_column: account_id
    file: domains/accounts.jsonl
    attributes:
      - name: balance
        type: float64

relations:
  - id: 0
    name: OWNS
    from: User
    to: Account
    direction: bidirectional
    file: relations/user_accounts.csv

  - id: 1
    name: TRANSFERRED_TO
    from: Account
    to: Account
    direction: bidirectional
    file: relations/transfers.tsv
    attributes:
      - name: amount
        type: float64
```

### Invoking `CsvManifestSnapshotBuilder` from Java

```java
import org.impulsegraph.builder.csv.CsvManifestSnapshotBuilder;
import java.nio.file.Path;

// Default 64 MB external-sort staging limit in a temporary staging directory:
CsvManifestSnapshotBuilder.buildV10Snapshot(
        Path.of("datasets/manifest.yaml"),
        Path.of("datasets/bank_graph.imps")
);

// Or with explicit staging directory and memory budget:
CsvManifestSnapshotBuilder.buildV10Snapshot(
        Path.of("datasets/manifest.yaml"),
        Path.of("datasets/bank_graph.imps"),
        Path.of("/var/tmp/impulse-staging"),
        256L * 1024 * 1024 // 256 MB
);
```

What `CsvManifestSnapshotBuilder.buildV10Snapshot` handles automatically:

* **Multi-Format Node & Edge Parsing**: Streams `.csv`, `.tsv`, and `.jsonl` files in $O(\text{chunk})$ heap memory via `StreamingColumnStager`.
* **Automatic Primary Key Columns & Resolution**: Ensures each domain's `id_column` (`string`, `int32`, `int64`, `uuid`) is registered with `withPrimaryKeyIndex(true)` and resolves natural source/target keys in edge files to dense IDs.
* **Unsorted Edge Streams**: Externally sorts arbitrary-order edge rows and their attached edge attributes by `(srcDenseId, tgtDenseId)` via `ExternalSortStaging`, and builds optional reverse `CSC` indices when `direction: bidirectional` or `include_csc: true` is set.
* **Nullable Bitmaps & Vector Columns**: Supports trailing `?` nullable shorthand (`int32?`, `string?`) with 128-byte-padded validity bitmaps and fixed-length vector columns (`float32[4]`).
* **Provenance Footer**: Embeds `impulse.schema.name`, `impulse.schema.version`, and `impulse.schema.sha256` (SHA-256 of the manifest bytes) into the `.imps` footer trailer.

---

## Step 5: Mount and Query the Snapshot

Mount the compiled `.imps` file inside a shared FFM `Arena` and execute an engine-native Kleisli traversal seeded by the external business key (`"101"`), filtering on the `amount` edge attribute and resolving surviving target nodes back to external account keys:

```java
import org.impulsegraph.api.ImpulseGraphSnapshot;
import org.impulsegraph.storage.csr.BinarySnapshotLoader;

import java.lang.foreign.Arena;
import java.nio.file.Path;
import java.util.List;

Path snapshotFile = Path.of("datasets/bank_graph.imps");

try (Arena arena = Arena.ofShared();
     BinarySnapshotLoader.LoadedSnapshot loaded =
             BinarySnapshotLoader.loadSnapshot(snapshotFile, arena)) {

    ImpulseGraphSnapshot graph = loaded.graph();

    // Engine-native 2-hop CSR traversal with fused CEL edge filter:
    // User("101") -[:OWNS]-> Account -[:TRANSFERRED_TO {amount > 1000.0}]-> Account
    List<String> recipientAccountKeys = graph.domain("User")
            .fromKey("101")
            .out("OWNS")
            .out("TRANSFERRED_TO", "edge.amount > 1000.0")
            .toKeyList();

    System.out.println("Recipient account keys: " + recipientAccountKeys);
}
```

!!! note "External `IdMapper<K>` Resolution for Topology-Only Snapshots"
    If you built a topology-only snapshot via `SnapshotBuilder` without embedding primary key attribute columns, seed the traversal via `graph.domain("User").from(userMapper.getId(101L))` and translate the resulting `.toList()` dense IDs at the boundary with `accountMapper::getKey`.

---

## FAQ

### Can I stream `.imps` bytes directly to S3 or Google Cloud Storage?

Yes. `SnapshotBuilder` writes sequentially in a single pass without seeking backward, so you can pass any `OutputStream` or `WritableByteChannel` backed by an S3/GCS multipart upload stream:

```java
try (OutputStream s3Out = openS3MultipartUploadStream("my-bucket", "snapshots/bank_graph.imps")) {
    builder.writeTo(s3Out);
}
```

### Can I cryptographically sign snapshots in Java?

Yes. Pass a `java.security.PrivateKey` and certificate chain before calling `writeTo(...)`:

```java
builder.withSignature(privateKey, certificateChain);
```

---

## Next Steps

* **[Schema-First Development & AOT Codegen](aot-codegen.md)** — Replace string domain/relation/attribute names with compile-time verified Java classes.
* **[Maven Plugin & Build-Time AOT Pipeline](maven-and-build-tooling.md)** — Automate test snapshot builds (`build-snapshot`) and schema validation in Maven.
* **[Changing Data & Live Updates](../../getting-started/handling-mutations.md)** — Architectural patterns for CDC refresh and Blue/Green hot-swapping.
* **[Fluent API Guide](../../query-api/fluent-api.md)** & **[ReBAC Authorization Showcase](../../showcase/authz.md)**.
