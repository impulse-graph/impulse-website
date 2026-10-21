# Typed Graph Model

Impulse Graph enforces a strongly-typed, [Data-Oriented](data-oriented-design.md) domain model designed to eliminate pointer chasing and hash-table lookups during traversal.

---

## 1. Node Domains & Relations

Every `.imps` snapshot schema is organized into **Node Domains** and directed **Relations**:

* **Node Domains**: Distinct entity namespaces (e.g., `User`, `Account`, `Product`, `Device`). Each domain declares its total node cardinality $N_d$, key type, and optional columnar attributes.
* **Directed Relations**: Typed edges connecting a specific source domain to a target domain (e.g., `(User)-[:OWNS]->(Account)`). Each relation is stored physically as its own contiguous CSR (forward) and optional CSC (reverse) matrix.

---

## 2. Per-Domain Dense IDs ($0 \dots N_d - 1$)

Unlike graph databases that assign a global 64-bit ID across all vertices, **every Node Domain in Impulse Graph has its own independent, 0-indexed dense integer space ($0 \dots N_d - 1$)**:

* Dense ID `0` in domain `User` and Dense ID `0` in domain `Account` are distinct entities in separate namespaces.
* Because IDs are contiguous from $0$ to $N_d - 1$, a Dense ID acts as a **direct array index** ($O(1)$ offset lookup) into CSR `row_offsets` and Structure-of-Arrays (SoA) attribute columns.
* Each domain configures its physical integer width (`uint16`, `uint32`, or `uint64`) based on its cardinality, minimizing CPU cache footprint.

---

## 3. External Business Keys & Primary Key Catalogs

Applications identify entities using external primary keys (`UUID`, `String`, or 64-bit database IDs). Impulse Graph bridges external keys and internal Dense IDs at the boundary of the query:

1. **Input Resolution (`toDenseId` / `fromKey`)**: Maps an external key (such as `"usr_alice"` or a UUID) to its internal Dense ID ($0 \dots N_d - 1$) via the snapshot's Key Catalog or `IdMapper<K>`.
2. **Traversal Execution**: All multi-hop walks, bitset operations, and SIMD filters execute strictly on primitive Dense IDs.
3. **Output Materialization (`toKey` / `toKeyList`)**: Resolves surviving target Dense IDs back into external keys when returning results.
