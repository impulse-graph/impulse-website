# Building Snapshots in Java: A Soup-to-Nuts Walkthrough

Welcome to the hands-on snapshot building guide! If you have read through the [Core Concepts](core-concepts.md) and understand that Impulse Graph stores graphs as memory-mapped, zero-copy `.imps` binary snapshots, your very first question is probably:

> **"Okay, but where does the `.imps` file come from? How do I take my existing data and turn it into one of these ultra-fast snapshots?"**

This guide will walk you through building your very first snapshot from scratch using the Java **`SnapshotBuilder`** API (`org.impulsegraph:impulse-builder`). 

We will assume **zero starting knowledge** of snapshot internals. We'll start simple, explain every concept as we encounter it, and build up an `.imps` snapshot step-by-step for a real-world **FinTech & Banking Graph**.

Along the way, you'll also learn how to stream millions of edges and attributes directly out of a **relational database (PostgreSQL, MySQL, SQLite) using JDBC** with bounded $O(\text{chunk})$ heap memory, so your JVM never runs out of RAM.

---

## 1. What Are We Building?

In our banking scenario, we have:

1. **`User` Domain**: The customers of our bank. Each user has an `age` attribute and an external string business key (like an email or customer ID).
2. **`Account` Domain**: Checking, savings, or investment accounts. Each account has a `balance` attribute.
3. **`OWNS` Relation**: Connects a `User` to the `Account`(s) they own.
4. **`TRANSFERRED_TO` Relation**: Connects an `Account` to other `Account`s where money was sent.

Here is the graph topology we want to build:

```
 (User: 42) ──[:OWNS]──> (Account: 101) ──[:TRANSFERRED_TO]──> (Account: 205)
                           (balance: $1500)                       (balance: $850)
```

Once built, we will be able to map this file into memory in **sub-milliseconds** and answer questions like: *"Which accounts received money from accounts owned by User 42?"* in **sub-microseconds**.

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

    <!-- Public API (DomainView, traversals, bitsets) -->
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

Impulse Graph uses Java Foreign Function & Memory (FFM) and vector acceleration. Configure the Maven compiler and surefire plugins:

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

In Impulse Graph, entities do not live in one giant, messy heap. Instead, they are partitioned into **Domains** (e.g., `User`, `Account`, `Transaction`).

Each domain owns its own **independent, zero-indexed dense integer space** from $0$ to $\text{cardinality} - 1$.

```java
import org.impulsegraph.builder.api.DomainDefinition;
import org.impulsegraph.builder.api.PrimitiveWidth;

// 1. Define our User domain with 10,000 users (dense IDs: 0 .. 9,999)
DomainDefinition userDomain = DomainDefinition.builder(10_000L)
        .idWidth(PrimitiveWidth.UINT32)       // 32-bit integers (up to 4.29 billion nodes)
        .withPrimaryKeyIndex(true)            // Enable external String/UUID -> Dense ID lookup
        .build();
```

### What did we just configure?

1. **`cardinality(10_000L)`**:
   The exact count of nodes in this domain. Why exact? Because Impulse pre-allocates vector-aligned offset memory so it never has to resize, re-hash, or fragment buffers.
2. **`idWidth(PrimitiveWidth.UINT32)`**:
   How many bytes are used to store node IDs for this domain in edge target lists.
   * `UINT16` (2 bytes): If your domain has fewer than 65,536 nodes (saves 50% storage!).
   * `UINT32` (4 bytes): The standard default; handles up to 4,294,967,296 nodes.
   * `UINT64` (8 bytes): For multi-billion/trillion node hyperscale domains.
3. **`withPrimaryKeyIndex(true)`**:
   In production, your users have UUIDs or emails like `"alice@acme.com"`. Enabling the primary key index tells the builder to embed a compact reverse index in the file so you can query by your external business keys!

---

## Step 2: Let's add Accounts next.....

Now let's add our second domain: `Account`. In our bank, we have 50,000 accounts.

```java
DomainDefinition accountDomain = DomainDefinition.builder(50_000L)
        .idWidth(PrimitiveWidth.UINT32)
        .withPrimaryKeyIndex(true)
        .build();
```

> [!IMPORTANT]
> **Remember the Golden Rule of Impulse Graph Domains**:
> Dense ID `0` in `User` is **completely distinct and unrelated** to Dense ID `0` in `Account`. They have independent coordinate spaces. This design allows direct array lookups ($O(1)$) without a massive sparse hash table.

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

### In-Memory Example for Quick Unit Tests

For tests or small datasets, you can wrap an in-memory list with a simple adapter:

```java
import org.impulsegraph.builder.spi.EdgeChunkIterator;
import org.impulsegraph.builder.spi.RelationDataSource;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.List;

public record SimpleEdge(long src, long tgt) {}

public class SimpleEdgeSource implements RelationDataSource {
    private final List<SimpleEdge> edges;

    public SimpleEdgeSource(List<SimpleEdge> edges) {
        this.edges = List.copyOf(edges);
    }

    @Override
    public long getEdgeCount() {
        return edges.size();
    }

    @Override
    public EdgeChunkIterator getEdges() {
        return new EdgeChunkIterator() {
            private int index = 0;

            @Override
            public boolean hasNext() {
                return index < edges.size();
            }

            @Override
            public int nextChunk(MemorySegment srcIds, MemorySegment tgtIds, int limit) {
                int count = 0;
                while (index < edges.size() && count < limit) {
                    SimpleEdge e = edges.get(index++);
                    srcIds.setAtIndex(ValueLayout.JAVA_INT_UNALIGNED, count, (int) e.src());
                    tgtIds.setAtIndex(ValueLayout.JAVA_INT_UNALIGNED, count, (int) e.tgt());
                    count++;
                }
                return count;
            }
        };
    }
}
```

---

## Step 5: The Real World: Reading from a JDBC Data Source

In real enterprise systems, your graph data lives in a relational database—like **PostgreSQL, MySQL, Oracle, Snowflake, or SQLite**.

Let's write a production-ready, reusable **`JdbcRelationDataSource`** that streams edges directly from an SQL query via standard `java.sql`.

### 1. The SQL Requirements for CSR
To stream edges into a CSR matrix:
1. **Source ID Ordering**: The SQL query **MUST be sorted by source ID** (`ORDER BY user_id`). This allows the builder to lay down CSR row offsets in a single sequential pass.
2. **Fetch Size**: Set `statement.setFetchSize(10_000)`. This tells the JDBC driver to stream rows from the database in batches rather than loading millions of rows into JVM memory at once.

### 2. The Reusable `JdbcRelationDataSource` Implementation

```java
package com.example.builder;

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
 * Streams edges directly from a relational database into off-heap MemorySegments
 * with bounded O(chunk) heap footprint.
 */
public class JdbcRelationDataSource implements RelationDataSource {

    private final Connection connection;
    private final String countQuery;
    private final String edgeQuery;
    private final long edgeCount;

    public JdbcRelationDataSource(Connection connection, String countQuery, String edgeQuery) throws SQLException {
        this.connection = connection;
        this.countQuery = countQuery;
        this.edgeQuery = edgeQuery;

        // 1. Fast exact edge count for header pre-allocation
        try (Statement stmt = connection.createStatement();
             ResultSet rs = stmt.executeQuery(countQuery)) {
            if (rs.next()) {
                this.edgeCount = rs.getLong(1);
            } else {
                throw harvestEmptyException();
            }
        }
    }

    private static IllegalStateException harvestEmptyException() {
        return new IllegalStateException("Count query returned 0 rows");
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
                            long src = rs.getLong(1);
                            long tgt = rs.getLong(2);

                            // Write source node ID formatted to domain integer width
                            if (sWidth == 2) {
                                srcIds.setAtIndex(ValueLayout.JAVA_SHORT_UNALIGNED, count, (short) src);
                            } else if (sWidth == 8) {
                                srcIds.setAtIndex(ValueLayout.JAVA_LONG_UNALIGNED, count, src);
                            } else {
                                srcIds.setAtIndex(ValueLayout.JAVA_INT_UNALIGNED, count, (int) src);
                            }

                            // Write target node ID formatted to domain integer width
                            if (tWidth == 2) {
                                tgtIds.setAtIndex(ValueLayout.JAVA_SHORT_UNALIGNED, count, (short) tgt);
                            } else if (tWidth == 8) {
                                tgtIds.setAtIndex(ValueLayout.JAVA_LONG_UNALIGNED, count, tgt);
                            } else {
                                tgtIds.setAtIndex(ValueLayout.JAVA_INT_UNALIGNED, count, (int) tgt);
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

Connecting your database to `SnapshotBuilder` is now as simple as providing the SQL query:

```java
Connection conn = DriverManager.getConnection("jdbc:postgresql://localhost:5432/bank_db", "user", "pass");

// OWNS Relation: User -> Account
RelationDataSource ownsDataSource = new JdbcRelationDataSource(
        conn,
        "SELECT COUNT(*) FROM user_accounts",
        "SELECT user_dense_id, account_dense_id FROM user_accounts ORDER BY user_dense_id"
);

// TRANSFERRED_TO Relation: Account -> Account
RelationDataSource transferDataSource = new JdbcRelationDataSource(
        conn,
        "SELECT COUNT(*) FROM account_transfers",
        "SELECT from_account_id, to_account_id FROM account_transfers ORDER BY from_account_id"
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
    // User(42) -[:OWNS]-> Account -[:TRANSFERRED_TO]-> Destination Accounts
    DomainView userDomain = graph.domain("User");

    long q0 = System.nanoTime();
    List<Long> destinationAccounts = userDomain.from(42)
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

### Q: What if my database IDs are not 0-indexed?
Impulse Graph domains require dense integer IDs $0 \dots N-1$. If your SQL table has sparse IDs (e.g. `102, 584, 99938`), you can either:
1. Generate dense IDs in SQL using the standard window function:
   ```sql
   SELECT id, DENSE_RANK() OVER (ORDER BY id) - 1 AS dense_id FROM users;
   ```
2. Or use Impulse's built-in `StringIdMapper` / `UuidIdMapper` in `impulse-api` during ingestion.

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
