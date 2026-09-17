# Building Snapshots in Java: A Soup-to-Nuts Walkthrough

Welcome to the hands-on snapshot building guide! If you have read through the [Core Concepts](core-concepts.md) and understand that Impulse Graph stores graphs as memory-mapped, zero-copy `.imps` binary snapshots, your very first question is probably:

> **"Okay, but where does the `.imps` file come from? How do I take my existing data and turn it into one of these ultra-fast snapshots?"**

This guide will walk you through building your very first snapshot from scratch using the Java **`SnapshotBuilder`** API (`org.impulsegraph:impulse-builder`). 

We will assume **zero starting knowledge** of snapshot internals. We'll start simple, explain every concept as we encounter it, and build up an `.imps` snapshot step-by-step for a real-world **FinTech & Banking Graph**.

Along the way, you'll also learn how to stream millions of edges and attributes directly out of a **relational database (PostgreSQL, MySQL, SQLite) using standard JDBC** with bounded $O(\text{chunk})$ heap memory, so your JVM never runs out of RAM.

---

## 1. What Are We Building?

In our banking scenario, our relational database has standard tables:

1. **`users` Table**: Contains customers (`user_id BIGINT`, `name VARCHAR`, `age INT`).
2. **`accounts` Table**: Contains accounts (`account_id BIGINT`, `balance DOUBLE`).
3. **`user_accounts` Table**: Join table connecting users to accounts (`user_id BIGINT`, `account_id BIGINT`).
4. **`account_transfers` Table**: Ledger of money transfers (`from_account_id BIGINT`, `to_account_id BIGINT`).

Here is the graph topology we want to construct:

```
 (User: 101) ──[:OWNS]──> (Account: 5001) ──[:TRANSFERRED_TO]──> (Account: 7008)
                            (balance: $1500)                        (balance: $850)
```

Once built, we will be able to map this snapshot into memory in **sub-milliseconds** and answer questions like: *"Which accounts received money from accounts owned by User 101?"* in **sub-microseconds**.

---

## 2. Setting Up Your Project Dependencies

First, add the Impulse Graph Java dependencies to your `pom.xml`. The snapshot builder lives in the **`impulse-builder`** module:

```xml
<dependencies>
    <!-- The Snapshot Builder (streams binary .imps files) -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-builder</artifactId>
        <version>0.9.0</version>
    </dependency>

    <!-- Public API (DomainView, IdMapper, traversals, bitsets) -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-api</artifactId>
        <version>0.9.0</version>
    </dependency>

    <!-- Storage Layer & Binary Snapshot Loader -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-storage</artifactId>
        <version>0.9.0</version>
    </dependency>

    <!-- Impulse Compute Virtual Machine -->
    <dependency>
        <groupId>org.impulsegraph</groupId>
        <artifactId>impulse-vm</artifactId>
        <version>0.9.0</version>
    </dependency>
</dependencies>
```

### Required JVM Runtime & Compiler Flags

Impulse Graph uses Java Foreign Function & Memory (FFM) and vector acceleration. Configure the Maven compiler plugin:

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

*(If you are running on **Java 21 LTS**, also add `--enable-preview` to your compiler args and JVM flags).*

---

## Step 1: Let's start with adding a Domain for Users.....

In Impulse Graph, entities do not live in one giant, unstructured heap. Instead, they are partitioned into **Domains** (e.g., `User`, `Account`, `Transaction`).

### Bridging Database Keys to Internal Dense IDs

In your source database (e.g. PostgreSQL), users have natural primary keys like `user_id BIGINT` (e.g., `101, 502, 9891`), UUIDs, or emails.

**Dense IDs ($0 \dots N-1$) are strictly an internal Impulse Graph concept.** In order to achieve sub-microsecond traversals, Impulse maps each domain's nodes to contiguous indices $0 \dots N-1$ so the CPU can index CSR row offsets directly as a flat hardware array without hash lookups.

**Your source database does NOT have dense IDs, and you do not need to modify your database tables.**

Instead, Impulse provides **`IdMapper<K>`** (`org.impulsegraph.api.IdMapper`) to bridge external database keys to internal dense coordinates. As you read your users from the database, the mapper assigns them internal dense IDs:

> [!IMPORTANT]
> **The `ORDER BY` is Crucial!**
> Notice the `ORDER BY user_id` clause in the query below. This deterministic ordering is **crucial because edges will later be loaded in that exact same order**:
> 
> Dense IDs ($0, 1, 2, \dots, N-1$) are assigned sequentially as domain rows are scanned. When building the CSR graph topology in Step 5, the relation edge stream (e.g., from `user_accounts`) **must be ordered by the exact same source key (`ORDER BY user_id`)** so that source dense IDs arrive monotonically without requiring random disk seeks or in-memory shuffling!

```java
import org.impulsegraph.api.IdMapper;
import org.impulsegraph.api.LongIdMapper;
import org.impulsegraph.builder.api.DomainDefinition;
import org.impulsegraph.builder.api.PrimitiveWidth;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

// 1. Scan user primary keys from PostgreSQL and map them to dense coordinates (0 .. N-1)
// CRITICAL: The "ORDER BY user_id" is essential! Edges must later be loaded in this exact same order.
IdMapper<Long> userMapper = new LongIdMapper("User");
long denseId = 0;

try (Statement stmt = conn.createStatement();
     ResultSet rs = stmt.executeQuery("SELECT user_id FROM users ORDER BY user_id")) {
    while (rs.next()) {
        long dbUserId = rs.getLong("user_id");
        userMapper.registerMapping(dbUserId, denseId++);
    }
}

// 2. Define the User domain with the exact cardinality from userMapper
DomainDefinition userDomain = DomainDefinition.builder(userMapper.size())
        .idWidth(PrimitiveWidth.UINT32)       // 32-bit integers (up to 4.29 billion nodes)
        .withPrimaryKeyIndex(true)            // Embeds reverse index for querying by database key
        .build();
```

### What did we just configure?

1. **`userMapper.size()`**:
   The exact count of nodes in this domain. Why exact? Because Impulse pre-allocates vector-aligned offset memory so it never has to resize, re-hash, or fragment buffers.
2. **`idWidth(PrimitiveWidth.UINT32)`**:
   How many bytes are used to store node IDs for this domain in edge target lists.
   * `UINT16` (2 bytes): If your domain has fewer than 65,536 nodes (saves 50% storage!).
   * `UINT32` (4 bytes): The standard default; handles up to 4,294,967,296 nodes.
   * `UINT64` (8 bytes): For multi-billion/trillion node hyperscale domains.
3. **`withPrimaryKeyIndex(true)`**:
   Tells the builder to embed a compact reverse index in the `.imps` file so you can resolve your original database primary keys (`user_id`, UUIDs, emails) to dense IDs at query time!

---

## Step 2: Let's add Accounts next.....

Now let's add our second domain: `Account`. In our database, accounts also have their own primary keys (`account_id BIGINT`):

```java
IdMapper<Long> accountMapper = new LongIdMapper("Account");
long accDenseId = 0;

// CRITICAL: "ORDER BY account_id" ensures Account dense IDs match the transfer edge order in Step 5!
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

> [!IMPORTANT]
> **Remember the Golden Rule of Impulse Graph Domains**:
> Internal Dense ID `0` in `User` is **completely distinct and unrelated** to Internal Dense ID `0` in `Account`. Each domain has its own independent coordinate space ($0 \dots N_d-1$). This allows direct array lookups ($O(1)$) without a massive sparse hash table.

---

## Step 3: Ok, time to link them with a Relation.....

Nodes without edges are just disconnected rows. Let's connect them!

A **Relation** is a typed, directed connection from a **Source Domain** to a **Target Domain**.

### Linking `User` to `Account` (`OWNS`)

Let's declare that a `User` owns an `Account`:

```java
import org.impulsegraph.builder.api.RelationDefinition;
import org.impulsegraph.builder.api.Topology;
import org.impulsegraph.builder.api.CompressionScheme;

RelationDefinition ownsRelation = RelationDefinition.builder("User", "Account")
        .addTopology(Topology.CSR, CompressionScheme.RAW) // Forward: User -> Account
        .addTopology(Topology.CSC, CompressionScheme.RAW) // Reverse: Account -> User
        .dataSource(ownsEdgeDataSource)                  // We'll define this next!
        .build();
```

### What are these Topologies?

* **`Topology.CSR` (Compressed Sparse Row)**:
  This stores forward edges. It allows your queries to say:
  `snap.domain("User").from(userId).out("OWNS")` in sub-microseconds.
  *CSR is mandatory for all relations.*
* **`Topology.CSC` (Compressed Sparse Column)**:
  This stores reverse (incoming) edges. It allows you to ask:
  `snap.domain("Account").from(accountId).in("OWNS")` (*"Who owns this account?"*).
  *CSC is optional, but adding it takes just one line!*

### Linking `Account` to `Account` (`TRANSFERRED_TO`)

Next, let's declare the money transfer relation between accounts:

```java
RelationDefinition transferRelation = RelationDefinition.builder("Account", "Account")
        .addTopology(Topology.CSR, CompressionScheme.RAW) // Forward: Outgoing transfers
        .addTopology(Topology.CSC, CompressionScheme.RAW) // Reverse: Incoming transfers
        .dataSource(transferEdgeDataSource)
        .build();
```

---

## Step 4: Where do the edges come from? The Data Source & Chunk Iterators

Now comes the big question: **How do we feed millions of edge connections into the builder?**

### Why not just pass a `List<Edge>`?
If you have 10 edges in a unit test, a `List<Edge>` is fine. But what if you have **500 million edges**?
* In standard Java, 500 million `Edge` objects on the heap would consume **~16 to 24 GB of RAM** just for JVM object headers and reference pointers!
* The garbage collector would freeze your application during allocation and cleanup.

### The Impulse Solution: Zero-Allocation Off-Heap Chunk Streaming
Impulse's builder uses **`RelationDataSource`** and **`EdgeChunkIterator`**.

Instead of creating Java objects, the builder allocates a small, fixed-size off-heap buffer (`MemorySegment`) and asks your iterator:
*"Please write the next chunk of edges (e.g. up to 65,536 edges) directly into these native memory buffers."*

Once written to disk, the builder reuses the same buffer for the next chunk. **Heap memory usage remains bounded to a few kilobytes, even when processing billions of edges.**

---

## Step 5: The Real World: Reading from a JDBC Data Source

In real enterprise systems, your graph data lives in a relational database.

Notice our SQL tables use **natural, standard database column names**:
* Table `user_accounts`: Foreign keys `(user_id, account_id)`
* Table `account_transfers`: Foreign keys `(from_account_id, to_account_id)`

There are **no dense ID columns in the database**. The JDBC streaming adapter uses our `IdMapper` instances to translate database keys into Impulse dense IDs on the fly!

### 1. The SQL Requirements for CSR

To stream edges into a CSR matrix in a single pass without buffering everything in memory:

1. **Source Ordering Must Match Domain Ingestion Order**:
   CSR (Compressed Sparse Row) requires edges to arrive grouped and strictly ordered by the source entity's **internal dense ID** ($0, 0, 1, 1, 2, \dots$).

   Because internal dense IDs were assigned sequentially in the order the source domain was scanned (e.g. `ORDER BY user_id` when populating `userMapper` in Step 1), **your edge query's source column MUST be sorted in that exact same order** (`ORDER BY user_id`). If the source ordering differs from the domain ingestion ordering, the generated dense IDs will arrive out of order, violating CSR sequential stream invariants.

2. **Fetch Size for Bounded Memory**:
   Always configure `statement.setFetchSize(10_000)`. By default, many JDBC drivers (like PostgreSQL) attempt to buffer all rows into JVM heap memory at once. Setting a streaming fetch size forces the driver to fetch rows from the database cursor in bounded batches.

### 2. The Reusable `JdbcRelationDataSource` Implementation

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
 * High-performance JDBC streaming edge source.
 * Reads standard relational database tables and maps primary/foreign keys
 * to Impulse dense IDs on the fly into off-heap MemorySegments with O(chunk) heap footprint.
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

        // 1. Fast exact edge count for header pre-allocation
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
            // Forward-only cursor with streaming fetch size
            PreparedStatement stmt = connection.prepareStatement(
                    edgeQuery,
                    ResultSet.TYPE_FORWARD_ONLY,
                    ResultSet.CONCUR_READ_ONLY
            );
            stmt.setFetchSize(10_000); // Stream 10,000 rows per database roundtrip

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
                            // Read natural database primary/foreign keys from SQL result set
                            long dbSourceKey = rs.getLong(1);
                            long dbTargetKey = rs.getLong(2);

                            // Translate database keys to internal Impulse dense IDs (0 .. N-1)
                            long srcDenseId = sourceMapper.getId(dbSourceKey);
                            long tgtDenseId = targetMapper.getId(dbTargetKey);

                            // Write source dense ID formatted to domain integer width
                            if (sWidth == 2) {
                                srcIds.setAtIndex(ValueLayout.JAVA_SHORT_UNALIGNED, count, (short) srcDenseId);
                            } else if (sWidth == 8) {
                                srcIds.setAtIndex(ValueLayout.JAVA_LONG_UNALIGNED, count, srcDenseId);
                            } else {
                                srcIds.setAtIndex(ValueLayout.JAVA_INT_UNALIGNED, count, (int) srcDenseId);
                            }

                            // Write target dense ID formatted to domain integer width
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

### 3. Using it in Your Application

Connecting your database to `SnapshotBuilder` is now as simple as querying your standard database tables:

```java
Connection conn = DriverManager.getConnection("jdbc:postgresql://localhost:5432/bank_db", "user", "pass");

// OWNS Relation: User -> Account
// Uses natural database foreign keys: user_id and account_id.
// CRITICAL: "ORDER BY user_id" matches the exact order we scanned the User domain in Step 1!
RelationDataSource ownsDataSource = new JdbcRelationDataSource(
        conn,
        "SELECT COUNT(*) FROM user_accounts",
        "SELECT user_id, account_id FROM user_accounts ORDER BY user_id",
        userMapper,
        accountMapper
);

// TRANSFERRED_TO Relation: Account -> Account
// Uses natural database foreign keys: from_account_id and to_account_id.
// CRITICAL: "ORDER BY from_account_id" matches the exact order we scanned the Account domain in Step 2!
RelationDataSource transferDataSource = new JdbcRelationDataSource(
        conn,
        "SELECT COUNT(*) FROM account_transfers",
        "SELECT from_account_id, to_account_id FROM account_transfers ORDER BY from_account_id",
        accountMapper,
        accountMapper
);
```

---

## Step 6: Putting It All Together & Streaming the Snapshot

Now we assemble our domains, relations, and metadata, and write the `.imps` file!

```java
import org.impulsegraph.builder.api.SnapshotBuilder;
import java.nio.file.Path;
import java.time.Instant;

Path snapshotPath = Path.of("datasets/bank_graph.imps");
Path stagingDir = Path.of("/tmp/impulse_staging");

SnapshotBuilder.create()
        // Staging directory used for external sort runs (e.g. Inverting CSR to CSC)
        .withStagingDirectory(stagingDir)
        // Bounded RAM limit for staging buffers before spilling to NVMe
        .withStagingMemoryLimit(64 * 1024 * 1024L) // 64 MB
        
        // 1. Register Node Domains
        .addDomain("User", userDomain)
        .addDomain("Account", accountDomain)
        
        // 2. Register Edge Relations
        .addRelation("OWNS", ownsRelation)
        .addRelation("TRANSFERRED_TO", transferRelation)
        
        // 3. Attach Custom Footer Metadata
        .addFooterMetadata("generator", "BankGraphPipeline-v1")
        .addFooterMetadata("source_database", "production_postgres_replica")
        .addFooterMetadata("built_at", Instant.now().toString())
        
        // 4. Stream directly to disk!
        .writeTo(snapshotPath);

System.out.println("Snapshot successfully written to: " + snapshotPath.toAbsolutePath());
```

### What Happens Under the Hood?
1. **Single-Pass Streaming**: The writer outputs bytes sequentially. It writes the 4KB Page 0 header, the shared string pool, the domain catalog, the CSR matrices, and the footer with an automated cryptographic SHA-256 checksum.
2. **Automated CSC Inversion**: Because we requested `Topology.CSC` on our relations, Impulse automatically sorts and transposes the edge stream in the staging directory without loading the entire graph into heap memory.
3. **128-Byte Alignment**: Every section and array is aligned to 128 bytes, ready for AVX-512 CPU execution and GPU warp access.

---

## Step 7: The Payoff: Sub-Millisecond Cold Start & Query Traversal

Now for the best part. Let's load the `.imps` file we just created and execute a traversal!

```java
import org.impulsegraph.api.ImpulseGraphSnapshot;
import org.impulsegraph.api.traversal.DomainView;
import org.impulsegraph.storage.csr.BinarySnapshotLoader;
import java.lang.foreign.Arena;
import java.nio.file.Path;
import java.util.List;

Path snapshotFile = Path.of("datasets/bank_graph.imps");

// Arena manages the off-heap memory lifecycle cleanly
try (Arena arena = Arena.ofShared()) {
    long t0 = System.nanoTime();
    
    // 1. Zero-copy memory-map the snapshot
    BinarySnapshotLoader.LoadedSnapshot loaded = 
            BinarySnapshotLoader.loadSnapshot(snapshotFile, arena);
    
    long t1 = System.nanoTime();
    System.out.printf("Snapshot loaded via zero-copy mmap in %.2f ms!%n", (t1 - t0) / 1_000_000.0);
    System.out.printf("Snapshot SHA-256: %s%n", loaded.getSha256Checksum());
    System.out.printf("Built at: %s%n", loaded.getMetadata("built_at"));

    ImpulseGraphSnapshot graph = loaded.getGraph();

    // 2. Execute a 2-hop vector traversal:
    // User(0) -[:OWNS]-> Account -[:TRANSFERRED_TO]-> Destination Accounts
    DomainView userDomain = graph.domain("User");

    long q0 = System.nanoTime();
    List<Long> destinationAccounts = userDomain.from(0)
            .out("OWNS")
            .out("TRANSFERRED_TO")
            .toList();
    long q1 = System.nanoTime();

    System.out.printf("Found %d destination accounts in %.2f µs!%n", 
            destinationAccounts.size(), (q1 - q0) / 1_000.0);
    System.out.println("Accounts reached: " + destinationAccounts);
}
```

---

## 8. Frequently Asked Questions & Best Practices

### Q: My database uses UUIDs, strings, or sparse auto-increment IDs—do I need to modify my database schema?
**No!** Dense IDs are strictly an **Impulse Graph internal storage mechanism** designed for off-heap direct array indexing ($0 \dots N-1$). Your source database schema remains 100% standard and untouched. You never need to add artificial `dense_id` columns to your database tables.

During ingestion, Impulse's `IdMapper` (`LongIdMapper`, `UuidIdMapper`, `StringIdMapper`) maps your database keys to dense IDs on the fly in memory. At query time, enabling `withPrimaryKeyIndex(true)` allows you to query directly using your database keys.

### Q: Can I stream directly to Amazon S3 or Google Cloud Storage?
**Yes!** `SnapshotBuilder` features single-pass S3 streaming semantics:
```java
// S3 / GCS Multipart Upload OutputStream
OutputStream s3Stream = s3Client.openStream("my-bucket", "snapshots/graph.imps");
builder.writeTo(s3Stream);
```
Because the builder never performs backwards file seeks, bytes flow directly across the network to cloud object storage.

### Q: Can I cryptographically sign my snapshots?
**Yes!** If you want tamper-evident snapshots for enterprise security:
```java
builder.withSignature(privateKey, certificateChain);
```
The signature is embedded into the file footer and verified automatically by `BinarySnapshotLoader`.

---

## Next Steps

* Explore the [Fluent API Guide](../query-api/fluent-api.md) for advanced filtering, set intersections, and multi-hop paths.
* Check out the [ReBAC Authorization Showcase](../showcase/authz.md) to see how Impulse Graph powers Google Zanzibar style fine-grained permission systems.
