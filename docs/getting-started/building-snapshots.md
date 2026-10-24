# Building Snapshots in Java

This guide walks through building an `.imps` snapshot from scratch using the Java **`SnapshotBuilder`** API (`org.impulsegraph:impulse-builder`).

We'll assume zero starting knowledge and build up a snapshot step-by-step for a **banking graph** scenario, including how to stream edge data from a relational database via JDBC.

If you haven't already, read the [Core Concepts](core-concepts.md) page first—it covers the binary format, CSR/CSC layouts, and domain model at a high level.

---

## What Are We Building?

Our relational database has standard tables:

| Table | Columns |
| :--- | :--- |
| `users` | `user_id BIGINT`, `name VARCHAR`, `age INT` |
| `accounts` | `account_id BIGINT`, `balance DOUBLE` |
| `user_accounts` | `user_id BIGINT`, `account_id BIGINT` |
| `account_transfers` | `from_account_id BIGINT`, `to_account_id BIGINT`, `amount DOUBLE` |

> [!NOTE]
> In a production banking database, `account_transfers` would also carry a `timestamp` (`TIMESTAMP_MS`), `currency`, `transfer_type` (ACH, wire), and reference IDs. Each of those columns can be attached to the `TRANSFERRED_TO` relation as its own 128-byte-aligned Structure-of-Arrays (SoA) edge attribute column. Here we attach `amount` (`DataType.F64`) to keep the walkthrough focused.

The graph we want:

```
 (User: 101) ──[:OWNS]──> (Account: 5001) ──[:TRANSFERRED_TO {amount: 2500.00}]──> (Account: 7008)
```

Once built, we can memory-map the snapshot and answer queries like *"Which accounts received transfers over \$1,000 from accounts owned by User 101?"*.

---

## Project Dependencies

Add these to your `pom.xml`:

```xml
<dependencies>
    <!-- The Snapshot Builder (writes binary .imps files) -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-builder</artifactId>
        </dependency>

    <!-- Public API (DomainView, IdMapper, traversals, bitsets) -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-api</artifactId>
        </dependency>

    <!-- Binary Snapshot Loader -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-storage</artifactId>
        </dependency>

    <!-- Compute Virtual Machine -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-vm</artifactId>
        </dependency>
</dependencies>
```

### JVM Flags

Impulse uses Java Foreign Function & Memory (FFM) and the Vector API. Configure the compiler plugin:

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
                    <arg>--add-modules</arg>
                    <arg>jdk.incubator.vector</arg>
                    <arg>--enable-native-access=ALL-UNNAMED</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
```

On **Java 21 LTS**, also add `--enable-preview` to both compiler args and JVM flags.

---

## Step 1: Define a Domain for Users

Entities in Impulse Graph are partitioned into **Domains** (e.g., `User`, `Account`). Each domain is an independent set of nodes with its own ID space.

### Bridging Database Keys to Dense IDs

In your source database, users have natural primary keys like `user_id BIGINT` (101, 502, 9891, ...). Impulse doesn't use those directly. Internally, each domain's nodes are mapped to a contiguous range of **dense IDs** $0 \dots N-1$. This is what makes CSR array indexing work—dense IDs are direct offsets into flat arrays, no hash lookups needed.

Dense IDs are strictly internal. You don't need to modify your database schema.

Impulse provides **`IdMapper<K>`** to bridge external keys to internal dense IDs. As you scan rows from the database, the mapper assigns each key a sequential dense ID:

> [!IMPORTANT]
> The `ORDER BY` in the domain scan query is critical. Dense IDs are assigned in scan order ($0, 1, 2, \dots$). Later, when loading edges (Step 5), the edge query must use the **same `ORDER BY`** on its source column so that source dense IDs arrive in ascending order. This is a CSR requirement—edges must be grouped by source node in ascending order.

```java
import org.impulsegraph.api.IdMapper;
import org.impulsegraph.api.LongIdMapper;
import org.impulsegraph.builder.api.DomainDefinition;
import org.impulsegraph.builder.api.PrimitiveWidth;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

// Scan user primary keys from the database and map them to dense IDs (0 .. N-1).
// The ORDER BY here determines the dense ID assignment order.
IdMapper<Long> userMapper = new LongIdMapper("User");
long denseId = 0;

try (Statement stmt = conn.createStatement();
     ResultSet rs = stmt.executeQuery("SELECT user_id FROM users ORDER BY user_id")) {
    while (rs.next()) {
        long dbUserId = rs.getLong("user_id");
        userMapper.registerMapping(dbUserId, denseId++);
    }
}

// Define the User domain with the exact cardinality
DomainDefinition userDomain = DomainDefinition.builder(userMapper.size())
        .idWidth(PrimitiveWidth.UINT32)       // 32-bit node IDs (up to ~4.29 billion nodes)
        .withPrimaryKeyIndex(true)            // Embed reverse index so you can query by database key later
        .build();
```

### What did we just configure?

- **`userMapper.size()`** — The exact node count. The builder uses this to pre-allocate correctly sized offset arrays.
- **`idWidth(PrimitiveWidth.UINT32)`** — The byte width used to store node IDs in edge target lists:
    - `UINT16` (2 bytes): domains under 65,536 nodes
    - `UINT32` (4 bytes): the standard default, up to ~4.29 billion nodes
    - `UINT64` (8 bytes): for multi-billion node domains
- **`withPrimaryKeyIndex(true)`** — Embeds a reverse index in the `.imps` file so you can resolve original database keys (user_id, UUIDs, emails) to dense IDs at query time.

---

## Step 2: Add an Accounts Domain

Same pattern for `Account`:

```java
IdMapper<Long> accountMapper = new LongIdMapper("Account");
long accDenseId = 0;

// ORDER BY account_id — this must match the edge query order in Step 5.
try (Statement stmt = conn.createStatement();
     ResultSet rs = stmt.executeQuery("SELECT account_id FROM accounts ORDER BY account_id")) {
    while (rs.next()) {
        long dbAccountId = rs.getLong("account_id");
        accountMapper.registerMapping(dbAccountId, accDenseId++);
    }
}

DomainDefinition accountDomain = DomainDefinition.builder(accountMapper.size())
        .idWidth(PrimitiveWidth.UINT32)
        .withPrimaryKeyIndex(true)
        .build();
```

> [!NOTE]
> **Disjoint ID Spaces**: Dense ID `0` in `User` is completely unrelated to dense ID `0` in `Account`. Each domain has its own independent coordinate space ($0 \dots N_d-1$).

---

## Step 3: Define the Relations

Nodes without edges are just disconnected rows. A **Relation** is a typed, directed connection from a **source domain** to a **target domain**.

### OWNS: User → Account

```java
import org.impulsegraph.builder.api.RelationDefinition;
import org.impulsegraph.builder.api.Topology;
import org.impulsegraph.builder.api.CompressionScheme;

RelationDefinition ownsRelation = RelationDefinition.builder("User", "Account")
        .addTopology(Topology.CSR, CompressionScheme.RAW) // Forward: User -> Account
        .addTopology(Topology.CSC, CompressionScheme.RAW) // Reverse: Account -> User
        .dataSource(ownsEdgeDataSource)                  // Defined in Step 5
        .build();
```

### Topologies: CSR vs CSC

- **`Topology.CSR` (Compressed Sparse Row)** — Stores forward edges. Enables queries like `snap.domain("User").from(userId).out("OWNS")`. CSR is required for all relations.
- **`Topology.CSC` (Compressed Sparse Column)** — Stores reverse (incoming) edges. Enables queries like `snap.domain("Account").from(accountId).in("OWNS")` (*"Who owns this account?"*). CSC is optional.

### TRANSFERRED_TO: Account → Account (with `amount` Edge Attribute)

Edges can also carry columnar attributes (stored as parallel 128-byte-aligned Structure-of-Arrays vectors indexed by edge position $0 \dots E-1$). Here we attach an `amount` property (`DataType.F64`) to `TRANSFERRED_TO`:

```java
RelationDefinition transferRelation = RelationDefinition.builder("Account", "Account")
        .addTopology(Topology.CSR, CompressionScheme.RAW)
        .addTopology(Topology.CSC, CompressionScheme.RAW)
        .dataSource(transferEdgeDataSource)
        .addAttribute("amount", transferAmountSource) // Edge property: transfer amount (F64)
        .build();
```

> [!TIP]
> **Real-World Transfer Metadata**: In a production financial graph, you would typically attach additional edge attributes alongside `amount`—such as `.addAttribute("timestamp", transferTimestampSource)` (`DataType.TIMESTAMP_MS`) for temporal window filtering, `channel`, or `status`. Because Impulse stores edge attributes in Structure-of-Arrays (SoA) layout, a query that only filters on `edge.amount > 1000.0` scans only the contiguous `amount[]` column and never touches `timestamp[]` or `channel[]` in memory.

---

## Step 4: Domains Without Attributes

In Steps 1 and 2 we scanned the database to build the `IdMapper` for each domain. But what if a domain has **no attributes** you care about—no `name`, `age`, `balance`, etc.?

In that case, you don't need to scan domain rows at all. **Only the cardinality (node count) is required.** If you already know the count from your edge data or from a `SELECT COUNT(*)`, you can skip the domain scan entirely and just build the `DomainDefinition` with that count:

```java
// If you only need the topology and don't need any domain attributes:
long accountCount = 50_000; // from SELECT COUNT(*) FROM accounts, or derived from edge data

DomainDefinition accountDomain = DomainDefinition.builder(accountCount)
        .idWidth(PrimitiveWidth.UINT32)
        .build();
```

The only thing the builder needs from a domain is its cardinality—everything else (the IdMapper, attributes, primary key index) is optional depending on your use case.

Of course, if you *do* want attributes or the ability to resolve original database keys at query time, you need the domain scan as shown in Steps 1–2.

---

## Step 5: Feeding Edge Data — Data Sources & Chunk Iterators

The builder needs to know the edges for each relation. For small datasets (unit tests, prototypes), you could construct edges in memory. For production data, you'll typically stream from a database.

### The Streaming Model

Rather than materializing all edges as Java objects on the heap, the builder uses **`RelationDataSource`** and **`EdgeChunkIterator`**. It allocates a fixed-size off-heap buffer and asks your iterator to fill it with the next batch of edges. Once the chunk is written to disk, the buffer is reused. This keeps heap usage constant regardless of edge count.

### SQL Requirements for CSR

To stream edges into a CSR matrix in a single pass:

1. **Source ordering must match domain scan order** — CSR requires edges grouped by source node in ascending dense ID order. Because dense IDs were assigned sequentially during the domain scan (Step 1), your edge query must sort by the same source column in the same order (e.g., `ORDER BY user_id`).

2. **Set a streaming fetch size** — By default, many JDBC drivers buffer all rows into heap memory. Set `statement.setFetchSize(10_000)` to force streaming.

### A Reusable `JdbcRelationDataSource`

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

/**
 * JDBC streaming edge source. Reads relational tables and maps
 * primary/foreign keys to Impulse dense IDs via IdMapper.
 */
public class JdbcRelationDataSource implements RelationDataSource {

    private final Connection connection;
    private final String countQuery;
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
        this.countQuery = countQuery;
        this.edgeQuery = edgeQuery;
        this.sourceMapper = sourceMapper;
        this.targetMapper = targetMapper;

        try (Statement stmt = connection.createStatement();
             ResultSet rs = stmt.executeQuery(countQuery)) {
            if (rs.next()) {
                this.edgeCount = rs.getLong(1);
            } else {
                throw new IllegalStateException("Count query returned 0 rows");
            }
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
                    edgeQuery,
                    ResultSet.TYPE_FORWARD_ONLY,
                    ResultSet.CONCUR_READ_ONLY
            );
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
                            long dbSourceKey = rs.getLong(1);
                            long dbTargetKey = rs.getLong(2);

                            // Translate database keys to dense IDs
                            long srcDenseId = sourceMapper.getId(dbSourceKey);
                            long tgtDenseId = targetMapper.getId(dbTargetKey);

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

### Wiring It Up

Connect the data sources to the relation definitions using standard SQL queries:

```java
Connection conn = DriverManager.getConnection("jdbc:postgresql://localhost:5432/bank_db", "user", "pass");

// OWNS: User -> Account
// ORDER BY user_id matches the domain scan order from Step 1.
RelationDataSource ownsDataSource = new JdbcRelationDataSource(
        conn,
        "SELECT COUNT(*) FROM user_accounts",
        "SELECT user_id, account_id FROM user_accounts ORDER BY user_id",
        userMapper,
        accountMapper
);

// TRANSFERRED_TO: Account -> Account
// ORDER BY from_account_id, to_account_id matches the domain scan order from Step 2.
RelationDataSource transferDataSource = new JdbcRelationDataSource(
        conn,
        "SELECT COUNT(*) FROM account_transfers",
        "SELECT from_account_id, to_account_id FROM account_transfers ORDER BY from_account_id, to_account_id",
        accountMapper,
        accountMapper
);
```

### Streaming the `amount` Edge Attribute (`AttributeDataSource`)

Edge attributes are streamed in the **exact same edge order** (`ORDER BY from_account_id, to_account_id`) so that element $k$ in the `amount[]` column corresponds to edge $k$ in the CSR `col_indices[]` array:

```java
import org.impulsegraph.builder.api.DataType;
import org.impulsegraph.builder.api.Nullability;
import org.impulsegraph.builder.spi.AttributeChunkIterator;
import org.impulsegraph.builder.spi.AttributeDataSource;

AttributeDataSource transferAmountSource = new AttributeDataSource() {
    @Override
    public DataType dataType() {
        return DataType.F64; // 64-bit IEEE-754 double
    }

    @Override
    public Nullability nullability() {
        return Nullability.NOT_NULL;
    }

    @Override
    public AttributeChunkIterator iterator() {
        try {
            PreparedStatement stmt = conn.prepareStatement(
                    "SELECT amount FROM account_transfers ORDER BY from_account_id, to_account_id",
                    ResultSet.TYPE_FORWARD_ONLY,
                    ResultSet.CONCUR_READ_ONLY
            );
            stmt.setFetchSize(10_000);
            ResultSet rs = stmt.executeQuery();

            return new AttributeChunkIterator() {
                private boolean hasNextRow = rs.next();

                @Override
                public boolean hasNext() {
                    return hasNextRow;
                }

                @Override
                public int nextChunk(MemorySegment destination, int limit) {
                    int count = 0;
                    try {
                        while (hasNextRow && count < limit) {
                            double amount = rs.getDouble(1);
                            destination.setAtIndex(ValueLayout.JAVA_DOUBLE_UNALIGNED, count, amount);
                            count++;
                            hasNextRow = rs.next();
                        }
                    } catch (SQLException e) {
                        throw new RuntimeException("Error reading transfer amount", e);
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
            throw new RuntimeException("Failed to stream transfer amounts", e);
        }
    }
};
```

---

## Step 6: Write the Snapshot

Assemble domains, relations, and metadata, then write the `.imps` file:

```java
import org.impulsegraph.builder.api.SnapshotBuilder;
import java.nio.file.Path;
import java.time.Instant;

Path snapshotPath = Path.of("datasets/bank_graph.imps");
Path stagingDir = Path.of("/tmp/impulse_staging");

SnapshotBuilder.create()
        // Staging directory for intermediate sort runs (e.g. inverting CSR to CSC)
        .withStagingDirectory(stagingDir)
        // RAM limit for staging buffers before spilling to disk
        .withStagingMemoryLimit(64 * 1024 * 1024L) // 64 MB

        // Register domains
        .addDomain("User", userDomain)
        .addDomain("Account", accountDomain)

        // Register relations
        .addRelation("OWNS", ownsRelation)
        .addRelation("TRANSFERRED_TO", transferRelation)

        // Optional footer metadata
        .addFooterMetadata("generator", "BankGraphPipeline-v1")
        .addFooterMetadata("source_database", "production_postgres_replica")
        .addFooterMetadata("built_at", Instant.now().toString())

        // Write to disk
        .writeTo(snapshotPath);

System.out.println("Snapshot written to: " + snapshotPath.toAbsolutePath());
```

When `writeTo()` runs, the builder streams bytes sequentially: the 4KB Page 0 header, the shared string pool, the domain catalog, CSR matrices, and a footer with a SHA-256 checksum. If you requested `Topology.CSC`, the builder automatically sorts and transposes the edge stream using the staging directory.

---

## Step 7: Load and Query

Load the `.imps` file, start the traversal using the external business key (`fromKey("101")` for `user_id = 101`), and materialize the surviving target accounts back into their external business keys via `.toKeyList()`:

```java
import org.impulsegraph.api.ImpulseGraphSnapshot;
import org.impulsegraph.api.traversal.DomainView;
import org.impulsegraph.storage.csr.BinarySnapshotLoader;
import java.lang.foreign.Arena;
import java.nio.file.Path;
import java.util.List;

Path snapshotFile = Path.of("datasets/bank_graph.imps");

try (Arena arena = Arena.ofShared()) {
    BinarySnapshotLoader.LoadedSnapshot loaded = 
            BinarySnapshotLoader.loadSnapshot(snapshotFile, arena);

    ImpulseGraphSnapshot graph = loaded.getGraph();

    // 2-hop traversal seeded by business key ("101") and returning destination account business keys:
    // User(101) -[:OWNS]-> Account -[:TRANSFERRED_TO (amount >= 1000.0)]-> Destination Account Keys
    DomainView users = graph.domain("User");

    List<String> destinationAccountKeys = users.fromKey("101")
            .out("OWNS")
            .out("TRANSFERRED_TO", "edge.amount >= 1000.0")
            .toKeyList();

    System.out.println("Destination account keys (transfers >= $1,000): " + destinationAccountKeys);
}
```

Because we configured `.withPrimaryKeyIndex(true)` on both `User` and `Account` domains in Steps 1 and 2, the engine resolves `"101"` to its internal dense ID at the start of the query, executes the multi-hop CSR walks and SIMD edge filter strictly over dense IDs, and translates only the final matching `Account` dense IDs back to their external business keys (`"7008"`, etc.) on `.toKeyList()`.

---

## Summary of Key Concepts

| Concept | What to Remember |
| :--- | :--- |
| **Dense IDs** | Internal to Impulse ($0 \dots N-1$). Not in your database. Assigned during domain scan. |
| **IdMapper** | Bridges external database keys to dense IDs. Variants: `LongIdMapper`, `UuidIdMapper`, `StringIdMapper`. |
| **ORDER BY** | Domain scan order determines dense ID assignment. Edge queries must use the same `ORDER BY` on the source column. |
| **Disjoint ID Spaces** | Dense ID `0` in `User` ≠ dense ID `0` in `Account`. Each domain is independent. |
| **Domains without attributes** | Only the cardinality is required. Skip the domain scan if you don't need attributes or a primary key index. |
| **CSR** | Forward edges, required. Edges must arrive sorted by source dense ID. |
| **CSC** | Reverse edges, optional. Built automatically from CSR via the staging directory. |
| **EdgeChunkIterator** | Fills fixed-size off-heap buffers in batches. Keeps heap usage constant. |

---

## FAQ

### My database uses UUIDs or strings—do I need to change my schema?

No. Dense IDs are internal to Impulse. Use `UuidIdMapper` or `StringIdMapper` instead of `LongIdMapper`, and your database schema stays as-is.

### Can I stream directly to S3 or GCS?

Yes. The builder writes bytes sequentially and never seeks backwards, so you can pass an `OutputStream` pointing at a cloud multipart upload:

```java
OutputStream s3Stream = s3Client.openStream("my-bucket", "snapshots/graph.imps");
builder.writeTo(s3Stream);
```

### Can I sign snapshots?

Yes:

```java
builder.withSignature(privateKey, certificateChain);
```

The signature is embedded in the footer and verified by `BinarySnapshotLoader`.

---

## Next Steps

* [Fluent API Guide](../query-api/fluent-api.md) — Filtering, set intersections, and multi-hop traversals.
* [ReBAC Authorization Showcase](../showcase/authz.md) — Fine-grained Zanzibar-style permissions with Impulse Graph.
