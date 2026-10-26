# Querying & DSLs Overview

Once an `.imps` snapshot is memory-mapped into your application, **Impulse Graph Engine** provides four ways to interact with the graph. All query interfaces compile through the same [ImpScheme $\to$ `impOps` bytecode pipeline](../concepts/compiler-architecture.md) and execute with **zero heap allocations on the hot path**:

| Query Mode | Best For | Primary Guide |
| :--- | :--- | :--- |
| **1. Fluent Traversal API** | Programmatic multi-hop walks, set algebra, state projections, and fixed-point loops in Java, Python, C++, Rust, TypeScript, and C#. | **[Fluent Traversal API](fluent-api.md)** & **[State Projections, Reducers & Loops](advanced-querying.md)** |
| **2. openCypher & Prepared Statements** | Declarative `MATCH ... WHERE ... RETURN` pattern matching and SQLite-style parameterized statements (`ImpulseStatement` / `impulse_stmt_t`). | **[openCypher Guide](../dsl/opencypher.md)** |
| **3. Domain-Specific Languages (`ImpLog` & `ImpK`)** | Recursive Datalog / Zanzibar ReBAC security policies (**`ImpLog`**) and GraphBLAS sparse matrix / PageRank math (**`ImpK`**). | **[ImpLog (`.implog`)](../dsl/implog.md)** & **[ImpK (`.impk`)](../dsl/impk.md)** |
| **4. Zero-Copy Tensor & Array Views** | Mounting CSR topology (`row_offsets`, `col_indices`) and `[N, D]` node embeddings directly as `torch.Tensor` or `scipy.sparse` views. | **[PyTorch & GNN Showcase](../showcase/gnn.md)** |

*Across all query modes, filter predicates and calculated projections use **[Google CEL (Filters & Math)](../dsl/cel.md)**.*

---

## 1. Fluent Domain-to-Domain Traversals

Every Fluent query anchors to a starting **Domain** (`snap.domain("User")`), seeds an initial frontier (`fromKey`, `from`, or `all`), walks zero or more directed relations (`.out(...)` / `.in(...)`), and collects the surviving nodes in the target domain:

=== "Java 25"
    ```java
    // 1. Multi-hop traversal with inline CEL filtering
    List<String> recipientAccounts = snap.domain("User")
        .fromKey("usr_101")
        .out("OWNS")
        .out("TRANSFERRED_TO", "edge.amount >= 1000.0")
        .toKeyList();

    // 2. Unbounded fixed-point reachability (transitive closure)
    ImpulseBitSet reachableGroups = snap.domain("User")
        .fromKey("usr_alice")
        .out("MEMBER_OF")
        .repeatUntilStable("PARENT_GROUP")
        .toBitSet();
    ```

=== "Python"
    ```python
    with Snapshot("banking.imps") as snap:
        recipient_accounts = (
            snap.traverse(start_node=101)
                .out("OWNS")
                .out("TRANSFERRED_TO")
                .to_list()
        )
    ```

=== "C++20 (`impulse::vm::QueryBuilder`)"
    ```cpp
    using namespace impulse::vm;
    CompiledQuery query = QueryBuilder()
        .inputNode(0)
        .walkEdge(/*MEMBER_OF=*/ 0)
        .repeatUntilStable([](QueryBuilder& b) {
            b.walkEdge(/*PARENT_GROUP=*/ 1);
        })
        .collectBitset()
        .compile();

    impulse_vm_context_t* ctx = nullptr;
    QueryResult res = query.execute(snap, /*input_param=*/ 101, &ctx);
    if (ctx) impulse_vm_context_destroy(ctx);
    ```

---

## 2. Parameterized Prepared Statements (`ImpulseStatement` / `impulse_stmt_t`)

For declarative `openCypher` queries, prepare a statement once and execute it with caller-bound parameters:

=== "Java 25 (`ImpulseStatement`)"
    ```java
    try (ImpulseStatement stmt = snap.prepare(
            "MATCH (u:User)-[:PURCHASED]->(p:Product) " +
            "WHERE u.id = $userId AND p.price <= 100.0 " +
            "RETURN p")) {

        stmt.bindNode("userId", 42L);

        try (RowReader rows = stmt.execute()) {
            while (rows.next()) {
                long productDenseId = rows.getNodeId(0);
            }
        }
    }
    ```

=== "C-ABI (`impulse_stmt_t`)"
    ```c
    impulse_stmt_t* stmt = NULL;
    impulse_stmt_prepare(
        snap,
        "MATCH (u:User)-[:PURCHASED]->(p:Product) WHERE u.id = $userId AND p.price <= 100.0 RETURN p",
        &stmt
    );

    size_t buf_len = impulse_stmt_buffer_size(stmt);
    void* buf = malloc(buf_len); // Reusable per-thread buffer

    impulse_stmt_bind_node(stmt, "$userId", 42);
    impulse_stmt_execute(stmt, buf, buf_len);

    size_t word_count = impulse_stmt_row_count(stmt);
    const uint64_t* bitset_words = (const uint64_t*)impulse_stmt_column_data(stmt, 0);

    impulse_stmt_finalize(stmt);
    free(buf);
    ```

!!! tip
    **When to Use Ad-Hoc Compilation vs. Pre-Prepared Statements**:
    Because the entire Impulse compiler pipeline (AST $\to$ Stage 1 & 2 Optimizer $\to$ `impOps` Bytecode $\to$ Java 25 `MethodHandle` JIT) completes in **under 10 microseconds**, compiling analytical queries directly with concrete constants unlocks aggressive **compile-time Zone Map branch pruning** (`age > 250` $\to$ `FALSE`) and **constant folding** that generic `$param` placeholders cannot exploit until bind time. Use pre-prepared statements for high-QPS request handlers (100K+ QPS), and feel free to compile ad-hoc fluent or CEL queries for analytical sweeps.
