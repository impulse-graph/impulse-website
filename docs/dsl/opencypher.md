# openCypher Dialect Guide

Impulse Graph includes an embedded, zero-dependency **openCypher** compiler frontend that lowers read-only `MATCH ... WHERE ... RETURN` queries into [`ImpScheme` S-Expressions](impscm.md) and executes them as 64-bit `impOps` bytecode on `ImpulseVM`.

---

## 1. Supported openCypher Clause Grammar

Because `.imps` snapshots are strictly read-only, the openCypher frontend focuses on high-speed analytical pattern matching and projection:

```cypher
MATCH <PathPattern>
[WHERE <PredicateExpression>]
RETURN <ProjectionExpression>
```

### 1.1 Supported `MATCH` Patterns

```cypher
// 1. Single-Hop Forward Traversal (CSR Walk)
MATCH (u:User)-[:FOLLOWS]->(f:User)

// 2. Single-Hop Reverse Traversal (CSC Walk)
MATCH (p:Product)<-[:PURCHASED]-(u:User)

// 3. Multi-Hop Metapath Across Domains
MATCH (d:Disease)-[:DdG]->(g:Gene)<-[:CuG]-(c:Compound)

// 4. Escaped / Namespaced Relationship Types (Backticks)
MATCH (d:Disease)-[:`DISGENET::da`]->(g:Gene)

// 5. Bounded Variable-Length Path (*min..max)
MATCH (u1:User)-[:FOLLOWS*1..3]->(u2:User)

// 6. Edge Variable Binding (for edge attribute filtering & projection)
MATCH (u:User)-[t:TRANSFERRED_TO]->(a:Account)
```

### 1.2 Compile-Time Guardrails & Intentional Exclusions
To guarantee sub-millisecond latency and deterministic memory bounds, the compiler enforces four strict rules at parse time:

1. **Explicit Relationship Types Required**: Every edge in a `MATCH` pattern must declare its relationship type (`-[:OWNS]->`). Untyped edges (`-->` or `-[e]->`) are rejected because each relation in `.imps` is stored as an isolated CSR/CSC matrix.
2. **No Disconnected Cartesian Products**: Disconnected patterns like `MATCH (a:User), (b:Account)` are rejected at compile time to prevent $O(M \times N)$ cross-joins.
3. **Bounded Variable-Length Paths**: Variable-length paths must specify an explicit upper bound (`*2`, `*1..4`, or `*..3`). Unbounded `*` wildcards are rejected in openCypher (use the Fluent API's `.repeatUntilStable(...)` or [ImpLog Datalog](implog.md) for unbounded fixed-point closures).
4. **Read-Only Execution**: Mutation and DDL clauses (`CREATE`, `MERGE`, `SET`, `DELETE`, `CREATE INDEX`) are rejected—updates are handled via [out-of-band `.imps` snapshot rebuilds](../getting-started/handling-mutations.md).

---

## 2. `WHERE` Predicates & `RETURN` Projections

* **Seed Anchoring (`WHERE u._key = $key` or `WHERE u.id = $id`)**: Constraining the starting node variable anchors the initial traversal frontier to that key or dense node ID.
* **Inline Node & Edge Attribute Filtering**: Predicates on edge variables (`t.amount >= $minAmt`) or node variables (`a.balance > 0`) compile directly into vectorized [Google CEL](cel.md) shaders (`OP_CSR_WALK_FILTERED` / `OP_NODE_FILTER`) evaluated inline during the CSR/CSC walk step.
* **`RETURN` Target Frontier Projections**:
  * `RETURN c` (or `RETURN c.id`): Projects the surviving **target domain node frontier** into a zero-copy result set (`BitSetRowReader` yielding surviving dense node IDs in Java, `List[int]` in Python `snap.cypher(...)`, or bitset words in C-ABI `impulse_stmt_column_data(stmt, 0)`).
  * `RETURN count(c)`: Computes the scalar cardinality or aggregate of the surviving target frontier (`OP_SET_CARDINALITY` / `OP_VECTOR_REDUCE_SUM` / `OP_COLLECT_VALUE_MAP`) without materializing full arrays.

!!! important
    **Set Semantics vs. Traditional Cypher Multi-Sets (Why Edge & Intermediate Hop Tuples Collapse)**:
    Traditional Cypher engines (like Neo4j) use multi-set (bag) path semantics, emitting one row per path tuple `(u, t, dst)`. Impulse Graph evaluates every hop using **Set Semantics (Monoidic Reduction)**:

    - When `WHERE t.amount >= 1000.0` filters an edge variable `t`, only edges satisfying that predicate are traversed, and all qualifying edges landing on the same destination node `dst` immediately collapse into `dst`'s target bitset via bitwise `OR`.
    - Consequently, `RETURN` outputs the **surviving target domain frontier** (or `count(target)`), rather than unreduced per-edge or intermediate-hop tuple rows. To inspect target node attributes or external keys for the surviving target IDs, use the target domain's O(1) key/attribute accessors.
    - **Shortest-Path Witness Tracking**: For single-hop minimum-cost witness selection, use `:ARGMIN` (`OP_REDUCE` with `ARGMIN` / `OP_STREAM_REDUCE_ARGMIN` / `reduceArgMin`). Full multi-hop path sequence reconstruction requires recording per-hop predecessor vectors across BFS levels.

---

## 3. Running openCypher Across Languages

=== "Java 25 (`ImpulseStatement`)"
    ```java
    String cypher = """
        MATCH (d:Disease)-[:DdG]->(g:Gene)<-[:CuG]-(c:Compound)
        WHERE d.id = $diseaseId
        RETURN c
        """;

    try (ImpulseStatement stmt = snap.prepare(cypher)) {
        stmt.bindNode("diseaseId", 42L);

        try (RowReader rows = stmt.execute()) {
            while (rows.next()) {
                long compoundDenseId = rows.getNodeId(0);
                System.out.println("Compound ID: " + compoundDenseId);
            }
        }
    }
    ```

=== "Python (`snap.cypher`)"
    ```python
    from impulse_graph import Snapshot

    with Snapshot("banking.imps") as snap:
        # Returns the list of surviving destination Account dense node IDs
        dst_account_ids = snap.cypher(
            """
            MATCH (u:User)-[:OWNS]->(src:Account)-[:TRANSFERRED_TO]->(dst:Account)
            WHERE u.id = $user_id
            RETURN dst
            """,
            params={"user_id": 101},
            catalog={"OWNS": 0, "TRANSFERRED_TO": 1},
        )
        for account_id in dst_account_ids:
            print("Reached Account dense ID:", account_id)
    ```

=== "C / C++20 (`impulse_stmt_*`)"
    ```c
    impulse_stmt_t* stmt = NULL;
    impulse_stmt_prepare(
        snap,
        "MATCH (u:User)-[e:KNOWS]->(f:User) WHERE u.id = $uid AND e.weight >= 0.8 RETURN f",
        &stmt
    );

    size_t buf_len = impulse_stmt_buffer_size(stmt);
    void* buf = malloc(buf_len);

    impulse_stmt_bind_node(stmt, "$uid", 101);
    impulse_stmt_execute(stmt, buf, buf_len);

    size_t word_count = impulse_stmt_row_count(stmt);
    const uint64_t* bitset_words = (const uint64_t*)impulse_stmt_column_data(stmt, 0);

    impulse_stmt_finalize(stmt);
    free(buf);
    ```

---

## 4. How openCypher Lowers to `ImpScheme` IR

Under the hood, `CypherCompiler` lowers `MATCH ... WHERE ... RETURN` patterns directly into [`ImpScheme` S-Expressions](impscm.md):

| openCypher Query | Lowered `ImpScheme` IR (`.impscm`) |
| :--- | :--- |
| `MATCH (d:Disease)-[:DdG]->(g:Gene)<-[:CuG]-(c:Compound)`<br>`WHERE d.id = $diseaseId RETURN c` | `(program (csr-walk "DdG") (csc-walk "CuG") (collect-bitset))` |
| `MATCH (d:Disease)-[:DdG]->(g:Gene)<-[:CuG]-(c:Compound)`<br>`WHERE d.id = $diseaseId RETURN count(c)` | `(program (csr-walk "DdG") (csc-walk "CuG") (collect-count))` |
| `MATCH (u:User)-[e:knows]->(f:User)`<br>`WHERE u.id = $uid AND e.weight >= 0.8 RETURN f` | `(program (csr-walk "knows" (shader (cel-expr (vec-cmp-gte (get-attr edge "weight") 0.8)))) (collect-bitset))` |
