# Quickstart

This guide demonstrates how to mount an immutable `.imps` binary snapshot and execute graph traversals across both primary engines (**Pure Java 25** and **Native C++20 / C-ABI**) as well as the **Python SDK**.

---

## 1. Mount an `.imps` Binary Snapshot & Traverse Edges

Impulse Graph maps `.imps` files directly from disk into virtual memory via `mmap`. Traversals anchor to an explicit Node Domain (`User`) and propagate frontiers lock-free off-heap.

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

                // 3. Execute a domain-anchored Kleisli traversal
                List<Long> friends = snap.domain("User")
                    .from(42L)
                    .out("FOLLOWS")
                    .toList();

                System.out.println("User 42 follows: " + friends);
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
        QueryResult res = query.execute(snap, 42 /* seed node */, &ctx);

        if (res.isOk()) {
            std::cout << "Node 100 reachable: " << res.testBitset(ctx, 100) << "\n";
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
            snap.traverse(start_node=42, catalog={"FOLLOWS": 0})
            .out("FOLLOWS")
            .to_list()
        )
        print("User 42 follows:", friends)
    ```

---

## 2. Filtered Traversals & Prepared Statements

Both the Pure Java 25 engine and the C++20 / C-ABI kernel include an in-kernel compiler for **Google CEL** predicates and **openCypher** pattern matching:

=== "Java 25"
    ```java
    // 1. Fluent traversal with vectorized CEL attribute filtering
    List<Long> activeFriends = snap.domain("User")
        .from(10L, 20L, 30L)
        .filter("node.age >= 21 && node.active == true")
        .out("FOLLOWS")
        .toList();

    // 2. Parameterized SQLite-style prepared statement
    try (var stmt = snap.prepare(
            "MATCH (u:User)-[:FOLLOWS]->(f:User) WHERE u.id = $uid AND f.age >= $minAge RETURN f.id")) {
        stmt.bindNode("uid", 42L).bindLong("minAge", 21L);
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

    impulse_stmt_bind_node(stmt, "uid", 42);
    impulse_stmt_bind_int(stmt, "minAge", 21);

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
            snap.traverse(start_node=42, catalog={"FOLLOWS": 0})
            .out("FOLLOWS")
            .filter(prefix="active")
            .to_list()
        )

        # 2. Parameterized openCypher query execution
        matched_ids = snap.cypher(
            "MATCH (u:User)-[:FOLLOWS]->(f:User) WHERE u.id = $uid RETURN f",
            params={"uid": 42},
            catalog={"FOLLOWS": 0},
        )
        print("Matched friend IDs:", matched_ids)
    ```
