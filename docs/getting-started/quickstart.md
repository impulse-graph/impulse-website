# Quickstart

This guide walks you through **building** an immutable `.imps` binary snapshot and **querying** it across **Pure Java 25**, **C / C++20 (C-ABI)**, and **Python**.

---

## 1. Build Your First `.imps` Snapshot

You can compile an `.imps` file in two ways:

* **Rust CLI Builder (`impulse build`)**: Compiles CSV, TSV, or Parquet files + a JSON manifest directly into an `.imps` file—a fast, standalone option with **no JVM required** (ideal for Python, C/C++, Go, C#, and Node.js users).
* **Java `SnapshotBuilder`**: Streams data directly from Java collections, JDBC databases, or custom `RelationDataSource` iterators.

=== "Rust CLI Builder (CSV / Parquet -> `.imps`)"
    Create two CSV files (`users.csv` and `follows.csv`) and a `manifest.json`:

    **`users.csv`** (Node keys and attributes):
    ```csv
    id,age,active
    usr_alice,30,true
    usr_bob,24,true
    usr_charlie,19,false
    ```

    **`follows.csv`** (Directed edges):
    ```csv
    src,tgt
    usr_alice,usr_bob
    usr_alice,usr_charlie
    usr_bob,usr_charlie
    ```

    **`manifest.json`**:
    ```json
    {
      "domains": [
        {
          "id": 0,
          "name": "User",
          "key_type": "string",
          "file": "users.csv",
          "id_column": "id",
          "attributes": [
            { "name": "age", "column": "age", "type": "int32" },
            { "name": "active", "column": "active", "type": "uint8" }
          ]
        }
      ],
      "relations": [
        {
          "name": "FOLLOWS",
          "src_domain": 0,
          "tgt_domain": 0,
          "file": "follows.csv",
          "src_column": "src",
          "tgt_column": "tgt",
          "include_csc": true
        }
      ]
    }
    ```

    Compile the `.imps` snapshot and inspect its 128-byte-aligned sections:
    ```bash
    impulse build --manifest manifest.json -o social.imps
    impulse snapshot inspect social.imps
    ```

=== "Java 25 (`SnapshotBuilder`)"
    For JVM applications or streaming JDBC pipelines, use `org.impulsegraph.builder.api.SnapshotBuilder` (see the full [Building Snapshots Walkthrough](building-snapshots.md)):

    ```java
    import org.impulsegraph.builder.api.*;
    import java.nio.file.Path;

    // 1. Define the User domain (3 nodes: dense IDs 0, 1, 2)
    DomainDefinition userDomain = DomainDefinition.builder(3)
        .idWidth(PrimitiveWidth.UINT32)
        .build();

    // 2. Define the FOLLOWS relation (User -> User, CSR + CSC)
    RelationDefinition followsRel = RelationDefinition.builder("User", "User")
        .addTopology(Topology.CSR, CompressionScheme.RAW)
        .addTopology(Topology.CSC, CompressionScheme.RAW)
        .dataSource(followsDataSource) // Streams (0->1), (0->2), (1->2)
        .build();

    // 3. Stream-write the 128-byte-aligned .imps file
    SnapshotBuilder.create()
        .addDomain("User", userDomain)
        .addRelation("FOLLOWS", followsRel)
        .writeTo(Path.of("social.imps"));
    ```

---

## 2. Mount `social.imps` & Traverse Edges

Impulse Graph maps `.imps` files directly from disk into virtual memory via `mmap`. Every traversal follows two core mechanics:

1. **Domain-to-Domain Pipeline**: You start in a single domain (e.g., `User`), walk zero or more directed relations (e.g., `.out("FOLLOWS")`), and finish in a single target domain, returning the surviving nodes, target attributes, or projected state from that final domain.
2. **Set Semantics & Collapsed Frontiers**: Intermediate results are stored as a **Set** (an off-heap BitSet), not a multi-set of duplicate paths. Converging paths are immediately collapsed into a single entry per node at each step (via Bitwise `OR` for reachability, or a monoid like `SUM`/`MIN`/`MAX` when projecting numeric state)—so the next hop never repeats work.

=== "Java 25 (Pure Java Engine)"
    ```java
    import org.impulsegraph.api.ImpulseGraphSnapshot;
    import org.impulsegraph.storage.csr.BinarySnapshotLoader;
    import java.lang.foreign.Arena;
    import java.nio.file.Path;
    import java.util.List;

    public class Quickstart {
        public static void main(String[] args) throws Exception {
            // 1. Manage off-heap memory lifecycle deterministically with a shared Arena
            try (Arena arena = Arena.ofShared()) {
                // 2. Memory-map the .imps binary snapshot off-heap (zero heap allocation)
                var loaded = BinarySnapshotLoader.loadSnapshot(Path.of("social.imps"), arena);
                ImpulseGraphSnapshot snap = loaded.getGraph();

                // 3. Execute a domain-anchored traversal (Dense ID 0 -> out("FOLLOWS"))
                List<Long> friends = snap.domain("User")
                    .from(0L)
                    .out("FOLLOWS")
                    .toList();

                System.out.println("User 0 follows Dense IDs: " + friends);
            }
        }
    }
    ```

=== "C / C++20 (C-ABI & Fluent VM)"
    ```cpp
    #include "impulse_graph.h"
    #include "impulse_vm_fluent.hpp"
    #include <iostream>

    int main() {
        // 1. Memory-map the .imps binary snapshot via C-ABI
        impulse_status_t status = IMPULSE_OK;
        impulse_snapshot_t* snap = impulse_snapshot_open("social.imps", &status);
        if (status != IMPULSE_OK || !snap) return 1;

        // 2. Compile a bytecode traversal query using the C++20 Fluent Builder
        using namespace impulse::vm;
        CompiledQuery query = QueryBuilder()
            .inputNode(0)       // Seed node ID in R0
            .walkEdge(0)        // CSR forward walk on relation 0 (FOLLOWS)
            .collectBitset()    // Materialize off-heap bitset handle
            .compile();

        // 3. Execute on ImpulseVM
        impulse_vm_context_t* ctx = nullptr;
        QueryResult res = query.execute(snap, 0 /* seed node */, &ctx);

        if (res.isOk()) {
            std::cout << "Node 1 reachable: " << res.testBitset(ctx, 1) << "\n";
        }

        if (ctx) impulse_vm_context_destroy(ctx);
        impulse_snapshot_close(snap);
        return 0;
    }
    ```

=== "Python"
    ```python
    from impulse_graph import Snapshot

    # 1. Memory-map the .imps binary snapshot off-heap
    with Snapshot("social.imps") as snap:
        # 2. Execute a fluent traversal on relation 0 (FOLLOWS)
        friends = (
            snap.traverse(start_node=0, catalog={"FOLLOWS": 0})
            .out("FOLLOWS")
            .to_list()
        )
        print("User 0 follows:", friends)
    ```

---

## 3. Filtered Traversals & Prepared Statements

Both the Pure Java 25 engine and the C++20 / C-ABI kernel include an in-kernel compiler for **Google CEL** predicates and **openCypher** pattern matching:

=== "Java 25"
    ```java
    // 1. Fluent traversal with vectorized CEL attribute filtering
    List<Long> activeFriends = snap.domain("User")
        .fromKey("usr_alice")
        .out("FOLLOWS")
        .filter("node.age >= 21 && node.active == true")
        .toList();

    // 2. Parameterized SQLite-style prepared statement
    try (var stmt = snap.prepare(
            "MATCH (u:User)-[:FOLLOWS]->(f:User) WHERE u.id = $uid AND f.age >= $minAge RETURN f.id")) {
        stmt.bindNode("uid", 0L).bindLong("minAge", 21L);
        try (var rows = stmt.execute()) {
            while (rows.next()) {
                System.out.println("Matched friend ID: " + rows.getNodeId(0));
            }
        }
    }
    ```

=== "C-ABI (`impulse_stmt_t`)"
    ```c
    #include "impulse_vm.h"
    #include <stdlib.h>

    impulse_stmt_t* stmt = NULL;
    impulse_stmt_prepare(
        snap,
        "MATCH (u:User)-[:FOLLOWS]->(f:User) WHERE u.id = $uid AND f.age >= $minAge RETURN f.id",
        &stmt
    );

    impulse_stmt_bind_node(stmt, "uid", 0);
    impulse_stmt_bind_int(stmt, "minAge", 21);

    // Exact scratch + result footprint is known at prepare time; caller supplies pre-allocated buffer
    size_t buf_size = impulse_stmt_buffer_size(stmt);
    void* buf = malloc(buf_size);
    impulse_stmt_execute(stmt, buf, buf_size);

    size_t rows = impulse_stmt_row_count(stmt);
    const uint64_t* col0 = (const uint64_t*)impulse_stmt_column_data(stmt, 0);

    free(buf);
    impulse_stmt_finalize(stmt);
    ```

=== "Python"
    ```python
    from impulse_graph import Snapshot

    with Snapshot("social.imps") as snap:
        # 1. Fluent traversal with node attribute filter
        active_friends = (
            snap.traverse(start_node=0, catalog={"FOLLOWS": 0})
            .out("FOLLOWS")
            .filter(prefix="active")
            .to_list()
        )

        # 2. Parameterized openCypher query execution
        matched_ids = snap.cypher(
            "MATCH (u:User)-[:FOLLOWS]->(f:User) WHERE u.id = $uid RETURN f",
            params={"uid": 0},
            catalog={"FOLLOWS": 0},
        )
        print("Matched friend IDs:", matched_ids)
    ```
