# Cypher Query Language Support in Impulse Graph Engine: Opcode Specification & Technical Proposal

## Executive Summary

This specification outlines the architecture for supporting a high-performance, read-only subset of the **Cypher query language** within the Impulse Graph Engine.

Drawing key architectural insights from TuringDB's MLIR query dialect (`query/ir/dialect/db/DBOps.td`) and NornicDB's Cypher fast-path matcher (`pkg/cypher/compound_query_shape_matcher.go`), this document specifies how read-only Cypher queries compile down to `ImpScheme` S-Expressions (`.impscm`), `ImpAsm` register assembly (`.impas`), and execute directly on `ImpulseVM` over zero-copy `.imps` binary snapshot files.

### Critical Structural & Physical Layout Rules
1. **Domains, Multi-Label Nodes & Relations Mapping**: In Impulse Graph Engine's `.imps` Binary Snapshot Specification:
   * Cypher **Primary Node Labels** (e.g. `:User`, `:Group`) map to Impulse **Domain Catalog Entries** (`DomainID`, `NameOffset`).
   * Cypher **Multi-Label Node Specifications** (e.g. `(u:Admin:User:Manager)`) are **unordered/commutative** in user queries. The compiler automatically matches `"User"` to the primary `DomainID`, compiling secondary labels (`:Admin`, `:Manager`) into bitwise label mask filters.
   * **Conflicting Primary Domains (e.g. `(u:User:Group:Manager)`) Are Invalid**: Because primary domains (`User`, `Group`) define mutually exclusive physical node ID spaces and SoA memory regions, a node cannot belong to two primary domains simultaneously. Specifying multiple primary domains is rejected at compile time as an empty domain intersection ($\emptyset$).
   * Cypher **Relationship Types** (e.g. `:USER_TO_GROUP`, `:KNOWS`) map directly to Impulse **Relation Directory Entries** (`RelationID`, `SrcDomainID`, `TgtDomainID`, `NameOffset`).
2. **Mandatory Explicit Relationship Specification**: Cypher patterns **MUST explicitly specify relationship types** (e.g. `(u:User)-[:USER_TO_GROUP]->(g:Group)`). Untyped relationship traversals (e.g. `(u:User)--(g:Group)`) are disallowed because each relation in `.imps` is physically stored as an isolated CSR/CSC matrix. Mandating explicit relationship types enables compile-time resolution of `RelationID`, executing via a single $O(1)$ `OP_CSR_WALK` without multi-matrix dynamic union overhead.
3. **Cartesian Products Prohibited**: Disconnected pattern matches without join keys or connecting relationships (e.g. `MATCH (a:User), (b:Group)`) are **strictly prohibited** and rejected at compile time. Disconnected cross-joins ($O(M \times N)$) destroy sub-microsecond latency and cache locality. All patterns MUST be connected via relationships or shared join keys.
4. **Native APOC Mapping to Impulse Macro Opcodes**: Cypher `CALL apoc.algo...` procedure calls map directly to Impulse's pre-existing native macro opcodes (`OP_CC_AFFOREST`, `OP_BRANDES_FORWARD`, `OP_LOUVAIN_MODULARITY`, `OP_KCORE_DECOMPOSITION`), executing graph algorithms directly on off-heap snapshot vectors.
5. **100% Zero-Allocation Compliance**: All proposed opcodes strictly preserve `ImpulseVM`'s Allocation-Free Hot Path Mandate. Intermediate bitsets, hash join maps, path frontiers, and sorting heaps are pooled and allocated strictly out-of-band via VM Scratch Arenas (`acquire_bitset`, `acquire_scratch_slice`). Zero heap `malloc`/`new` calls occur during query execution.
6. **Domain-Agnostic VM ISA**: `impOps` is the generic Virtual Machine ISA for `ImpulseVM` serving multiple frontends (`ImpK`, `ImpLog`, `ImpScheme`, Cypher). Opcodes **MUST NOT** include frontend-specific prefixes (e.g. `CYPHER`).

---

## 1. Domain/Relation Mapping & Supported Cypher Subset

### 1.1 Physical Schema Mapping (.imps  $\leftrightarrow$ Cypher)

```
Cypher Pattern & APOC Mapping
   MATCH (u:User)-[:USER_TO_GROUP]->(g:Group)  ---> VALID: Connected pattern graph
   MATCH (u:User), (g:Group)                   ---> INVALID: Disconnected Cartesian Product
   CALL apoc.algo.betweenness()                ---> NATIVE: Maps to OP_BRANDES_FORWARD (0x48)
```

#### Primary Domain & Connection Rules
1. **Disjoint Node ID Spaces**: Primary Domains (`DomainCatalogArray`: `User`, `Group`, `Device`) partition physical nodes into distinct $0..N-1$ ID spaces and separate memory-mapped SoA attribute pools.
2. **Mandatory Pattern Connection**: Every node variable in a query must be connected to the pattern graph via a typed relationship or explicit join predicate. Disconnected Cartesian products (e.g. `MATCH (a:User), (b:Group)`) are rejected at compile time.

### 1.2 Supported Clauses, Syntax & APOC Procedures

| Cypher Construct / Procedure | Syntax Example | Description & Semantics |
| :--- | :--- | :--- |
| **Typed Multi-Label `MATCH`** | `MATCH (u:Admin:User)-[:USER_TO_GROUP]->(g:Group)` | Order-invariant multi-label node matching over typed relationships. |
| **`OPTIONAL MATCH`** | `OPTIONAL MATCH (u:User)-[:HAS_PERM]->(p:Permission)` | Left outer-join pattern matching; emits `NULL` (`0xFFFF_FFFF`) for missing relationships. |
| **`WHERE`** | `WHERE u.age >= 21 AND g.name STARTS WITH "Admin"` | Filtering over node/edge scalar attributes, domain constraints, and string prefixes. |
| **`WITH`** | `WITH u, COUNT(g) AS groupCount` | Pipeline projection barrier passing intermediate binding frames downstream. |
| **`RETURN`** | `RETURN u.name, g.id, COUNT(g)` | Final result set projection, aggregation, and variable renaming. |
| **`ORDER BY`** | `ORDER BY u.age DESC, g.name ASC` | Result set ordering over projected expressions or aggregates. |
| **`SKIP` / `LIMIT`** | `SKIP 20 LIMIT 10` | Paging and result set windowing. |
| **`UNWIND`** | `UNWIND $ids AS targetId` | Expanding list attributes or parameters into individual row execution frames. |
| **Variable Paths** | `(u:User)-[:REPORTS_TO*1..5]->(m:User)` | Multi-hop variable-length path traversal bounded by minimum and maximum hops. |
| **`shortestPath()`** | `shortestPath((u:User)-[:LINK*]->(g:Group))` | Bi-directional BFS shortest path computation between node sets. |
| **`CALL apoc.algo.components`** | `CALL apoc.algo.connectedComponents()` | Maps directly to native opcode `OP_CC_AFFOREST` (`0x40`). |
| **`CALL apoc.algo.betweenness`**| `CALL apoc.algo.betweenness()` | Maps directly to native opcode `OP_BRANDES_FORWARD` (`0x48`). |
| **`CALL apoc.algo.louvain`**    | `CALL apoc.algo.louvain()` | Maps directly to native opcode `OP_LOUVAIN_MODULARITY` (`0x67`). |
| **`CALL apoc.algo.kcore`**      | `CALL apoc.algo.kCore()` | Maps directly to native opcode `OP_KCORE_DECOMPOSITION` (`0x68`). |

### 1.3 Explicitly Excluded Features (Out of Scope)
* **Cartesian Products**: `MATCH (a), (b)` (Disconnected cross-joins are rejected at compile time).
* **Conflicting Primary Domain Patterns**: `(u:User:Group)` (Rejected at compile time as a domain intersection violation).
* **Untyped Relationship Patterns**: `(a)--(b)` (Omitted relationship types are rejected at compile time to guarantee $O(1)$ relation matrix resolution).
* **Mutation Operators**: `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE` (Impulse snapshot format `.imps` is strictly read-only; mutation is handled out-of-band by offline snapshot compilers).
* **DDL & Indexing**: `CREATE INDEX`, `DROP INDEX`, `CREATE CONSTRAINT` (Indexes are statically compiled directly into `.imps` binary headers).
* **Transaction Control**: `COMMIT`, `ROLLBACK` (Snapshots are atomic and immutable).

---

## 2. TuringDB / NornicDB Processor Analysis & `impOps` Reuse Matrix

The table below maps query operators from TuringDB (`query/pipeline/processors/`) and NornicDB (`pkg/cypher/`) to ImpulseVM's opcode infrastructure, explicitly distinguishing **existing `impOps`** from **truly new proposed ISA opcodes**.

| Reference Database Processor | Operator / Query Shape | Impulse Engine Execution Strategy | Opcode Status & Name |
| :--- | :--- | :--- | :--- |
| TuringDB / NornicDB Label Scan | `MATCH (n:Label)` | Map Domain name string to DomainID and scan primary domain vectors. | **NEW**: `OP_LABEL_SCAN` (`0x80`) |
| TuringDB / NornicDB CSR Walk | `MATCH (a)-[:TYPE]->(b)` | Zero-copy CSR offset walk for source nodes, filtered by `RelationID`. | **REUSED**: `OP_CSR_WALK` (`0x10`) |
| TuringDB / NornicDB CSC Walk | `MATCH (a)<-[:TYPE]-(b)` | Zero-copy CSC offset walk for target nodes, filtered by `RelationID`. | **REUSED**: `OP_CSC_WALK` (`0x18`) |
| TuringDB / NornicDB Filter | `WHERE a.attr > X` | SIMD vector predicate evaluation over SoA attribute & label bitmask matrices. | **REUSED**: `OP_NODE_FILTER` (`0x14`), `OP_NODE_FILTER_STR_PREFIX` (`0x15`) |
| TuringDB / NornicDB Hash Join | Multi-branch Join | Hash join over intermediate VM register binding frames in scratch memory. | **NEW**: `OP_HASH_JOIN` (`0x82`) |
| TuringDB / NornicDB Unwind | `UNWIND $list AS x` | Step through list element vectors in scratch space, creating iterative sub-frames. | **NEW**: `OP_UNWIND` (`0x83`) |
| TuringDB / NornicDB Top-K | `ORDER BY ... LIMIT K` | Maintain bounded Top-K min/max binary heap in VM scratch memory without global sorting. | **NEW**: `OP_SORT_TOPK` (`0x84`) |
| TuringDB Path Explorer | `(a)-[*1..N]->(b)` | Multi-hop frontier CSR expansion using Roaring Bitsets for visited tracking. | **NEW**: `OP_PATH_EXPLORE` (`0x85`) |
| TuringDB Shortest Path | `shortestPath(...)` | Bi-directional BFS search between source and target node sets over CSR/CSC. | **NEW**: `OP_SHORTEST_PATH_BFS` (`0x86`) |
| TuringDB / NornicDB Aggregation | `COUNT(...)`, `AVG(...)` | Hash grouping & SIMD vector reduction across register columns. | **NEW**: `OP_GROUP_AGG` (`0x87`) |
| NornicDB APOC Connected Components | `CALL apoc.algo.components` | Afforest parallel connected components over CSR snapshot topology. | **REUSED**: `OP_CC_AFFOREST` (`0x40`) |
| NornicDB APOC Betweenness | `CALL apoc.algo.betweenness` | Brandes forward/backward betweenness centrality over CSR snapshot topology. | **REUSED**: `OP_BRANDES_FORWARD` (`0x48`) |
| NornicDB APOC Louvain | `CALL apoc.algo.louvain` | Parallel Louvain modularity community detection over CSR snapshot. | **REUSED**: `OP_LOUVAIN_MODULARITY` (`0x67`) |
| NornicDB APOC K-Core | `CALL apoc.algo.kCore` | K-Core decomposition pruning over CSR snapshot. | **REUSED**: `OP_KCORE_DECOMPOSITION` (`0x68`) |

---

## 3. Proposed Generic `impOps` Opcode Extensions (`0x80` .. `0x88`)

To support complete Cypher execution while maintaining a clean, domain-agnostic VM ISA, we define **8 new generic opcodes** in the `0x80`..`0x88` opcode block.

```
+-----------------------------------------------------------------------------------+
| New Generic impOps Opcode Additions (0x80 .. 0x88)               |
+------+--------------------------+--------------------------------------------------+
| Hex  | Opcode Name              | Operational Summary                              |
+------+--------------------------+--------------------------------------------------+
| 0x80 | OP_LABEL_SCAN            | Scans nodes carrying a specified DomainID mask.  |
| 0x82 | OP_HASH_JOIN             | Joins two register node-binding matrices.        |
| 0x83 | OP_UNWIND                | Unwinds array/vector register into row frames.   |
| 0x84 | OP_SORT_TOPK             | Performs Top-K heap sort over register columns.  |
| 0x85 | OP_PATH_EXPLORE          | Multi-hop BFS traversal for (a)-[*min..max]->(b) |
| 0x86 | OP_SHORTEST_PATH_BFS     | Bi-directional BFS shortest path calculation.    |
| 0x87 | OP_GROUP_AGG             | Hash group-by and aggregate reduction.           |
| 0x88 | OP_OPTIONAL_OUTER_WALK   | Left-outer CSR/CSC walk emitting NULL on miss.   |
+------+--------------------------+--------------------------------------------------+
```

---

## 4. Operational Breakdown of the Remaining Opcodes

### 1. `OP_LABEL_SCAN` (`0x80`)
* **Purpose**: Serves as the query entry point for node domain scans (e.g. `MATCH (u:User)`).
* **Operation**: Reads the static `NodeCount` $N$ from the `.imps` `DomainCatalogEntry` for `DomainID`. Returns a zero-copy pointer slice to contiguous domain array $[0..N-1]$ or writes sequential NodeIDs into destination register `R_out`.

### 2. `OP_HASH_JOIN` (`0x82`)
* **Purpose**: Joins multi-variable pattern branches (e.g. joining `(a)-[:KNOWS]->(b)` and `(b)-[:WORKS_AT]->(c)` on key variable `b`).
* **Operation**: Builds a flat open-addressing hash table in VM Scratch Arena using `LeftColIdx` of `R_left_table` and probes with `RightColIdx` of `R_right_table`. Emits matching joined rows into `R_out_table`.

### 3. `OP_SORT_TOPK` (`0x84`)
* **Purpose**: Evaluates `ORDER BY ... LIMIT K` without full-array sorting.
* **Operation**: Allocates a fixed $K$-element binary min/max heap in VM Scratch Arena. Performs a single $O(N \log K)$ SIMD scan over key column `R_key_col`, immediately discarding elements worse than the root. Emits sorted Top-K row indices.

### 4. `OP_PATH_EXPLORE` (`0x85`)
* **Purpose**: Evaluates variable-length path patterns `(u:User)-[:REPORTS_TO*1..5]->(m:User)`.
* **Operation**: Executes multi-hop Breadth-First Search (BFS) over `RelationID` CSR matrix up to `MaxHops`. Swaps two pooled BitSet handles (`frontier_curr`, `frontier_next`) per hop iteration. Reconstructs and outputs valid path arrays meeting `MinHops` threshold.

### 5. `OP_SHORTEST_PATH_BFS` (`0x86`)
* **Purpose**: Calculates shortest path between source and target node sets (`shortestPath((a)-[*]-(b))`).
* **Operation**: Performs bi-directional BFS using two pooled BitSet handles (`src_frontier`, `dst_frontier`) stepping forward via CSR (`OP_CSR_WALK`) and backward via CSC (`OP_CSC_WALK`) until bitwise AND intersection `src_frontier & dst_frontier != 0`.

### 6. `OP_GROUP_AGG` (`0x87`)
* **Purpose**: Evaluates `GROUP BY` and computes aggregates (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`).
* **Operation**: Employs a flat open-addressing hash map in VM Scratch Arena over key columns `R_key_cols`. Accumulates primitive 64-bit scalar aggregators directly in fixed hash slots.

---

## 5. Zero-Allocation Hot Path Strategy & Allocation Audit

Every single proposed opcode maintains **100% compliance** with ImpulseVM's Allocation-Free Hot Path Mandate (`VM_SPECIFICATION.md` §6.5 & §6.6). Zero dynamic heap allocations (`malloc`, `new`, `std::vector::push_back`, or JVM heap objects) occur inside the instruction interpreter loop.

| Opcode | Memory Mechanism | Allocation Status |
| :--- | :--- | :--- |
| **`OP_LABEL_SCAN`** (`0x80`) | Direct zero-copy `.imps` mmap pointer slice | **0 Bytes Allocated** |
| **`OP_HASH_JOIN`** (`0x82`) | Pre-allocated Scratch Arena flat open-addressing hash map | **0 Bytes Allocated** |
| **`OP_UNWIND`** (`0x83`) | Register array slice offset sliding | **0 Bytes Allocated** |
| **`OP_SORT_TOPK`** (`0x84`) | Pre-allocated $K$-element Scratch Arena binary heap | **0 Bytes Allocated** |
| **`OP_PATH_EXPLORE`** (`0x85`) | Pooled BitSet handles (`acquire_bitset`) | **0 Bytes Allocated** |
| **`OP_SHORTEST_PATH_BFS`** (`0x86`) | Pooled BitSet handles + Scratch parent vector | **0 Bytes Allocated** |
| **`OP_GROUP_AGG`** (`0x87`) | Pre-allocated Scratch Arena flat hash map | **0 Bytes Allocated** |
| **`OP_OPTIONAL_OUTER_WALK`** (`0x88`) | Direct mmap CSR walk writing `0xFFFF_FFFF` sentinels | **0 Bytes Allocated** |

---

## 6. End-to-End Compiler Stack & Lowering Pipeline

```
Cypher APOC & Pattern Query
  │  "MATCH (u:User)-[:USER_TO_GROUP]->(g:Group) CALL apoc.algo.betweenness() YIELD node, score RETURN node.name, score"
  ▼
ImpScheme IR (.impscm S-Expression AST)
  │ (cypher-query
  │ (match (node u :User) (rel :USER_TO_GROUP) (node g :Group))
  │ (call apoc.algo.betweenness :out score-table)
  │ (project :out result-set :in score-table :cols (node.name score)))
  ▼
ImpAsm Register Assembly (.impas) -- Direct Mapping to Native Macro Opcodes
  │ OP_LABEL_SCAN R0, 0x0000               ; Scan Domain "User" -> R0
  │ OP_CSR_WALK R1, R0, 0x0004             ; Walk Relation "USER_TO_GROUP" -> R1
  │ OP_BRANDES_FORWARD R2, R1              ; Native Opcode 0x48: Brandes Betweenness Centrality
  │ OP_COLLECT_ARRAY R3, R2                ; Materialize results
  ▼
ImpulseVM Bytecode (.impb)
     [0x80, 0x00, 0x00, 0x10, 0x01, 0x00, 0x04, 0x48, 0x02, 0x91, 0x03, 0x00]
```

---

## 7. Summary & Mandatory Rule Enforcement

1. **Native APOC Procedure Mapping**: Cypher `CALL apoc.algo...` procedure calls map directly down to Impulse's pre-existing native macro opcodes (`OP_CC_AFFOREST`, `OP_BRANDES_FORWARD`, `OP_LOUVAIN_MODULARITY`, `OP_KCORE_DECOMPOSITION`).
2. **Cartesian Products Strictly Prohibited**: Disconnected pattern matches (e.g. `MATCH (a:User), (b:Group)`) are rejected at compile time to preserve sub-microsecond latency.
3. **100% Zero-Allocation Compliance**: Every opcode strictly observes Section 6.5 of `VM_SPECIFICATION.md`. Intermediate structures operate strictly on pre-allocated Scratch Arenas and BitSet handle pools.
4. **Order-Invariant Multi-Label Support**: Cypher label ordering is commutative (`(u:Admin:User:Manager)` $\equiv$ `(u:User:Admin:Manager)`).
5. **Conflicting Primary Domains Are Invalid**: If a query specifies multiple labels that resolve to two or more distinct primary Domains (e.g. `(u:User:Group:Manager)`), the compiler rejects the pattern at compile time.
6. **Mandatory Relation Types**: Cypher relationship patterns must explicitly name the relationship (e.g., `(u:User)-[:USER_TO_GROUP]->(g:Group)`).
7. **Domain & Relation Mapping**: Cypher primary node labels correspond directly to `.imps` **Domains** (`DomainCatalogArray`), and relationship types correspond directly to `.imps` **Relations** (`RelationDirectoryTable`).
8. **Zero-Copy ISA Execution**: Query execution uses direct $O(1)$ CSR walks (`OP_CSR_WALK` `0x10`) over memory-mapped `.imps` snapshot matrices without heap allocation.
