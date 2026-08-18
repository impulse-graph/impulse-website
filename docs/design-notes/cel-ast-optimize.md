# CEL Expression & AST Optimization via Snapshot Metadata and Algebraic Property Labeling

This document formalizes the compilation, analysis, and optimization pipeline for evaluating **Common Expression Language (CEL)** and general query expressions over **Impulse Graph Engine** immutable binary snapshots (`.imps`).

It details how an un-optimized Abstract Syntax Tree (AST) is bound to an immutable snapshot instance, annotated with **exact physical metadata** and **formal algebraic properties**, and transformed into ultra-low-latency, zero-allocation **ImpScheme IR (`.impscm`)**, **ImpAsm (`.impas`)**, and **`impOps` bytecode**.

---

## 1. Executive Summary & The Immutable Snapshot Thesis

In traditional relational and graph databases (e.g., PostgreSQL, Neo4j, CockroachDB), query optimizers operate under **probabilistic uncertainty**:
1. **Dynamic Mutation**: The underlying dataset mutates concurrently, forcing optimizers to rely on stale, sampled histograms.
2. **Conservative Transformations**: Compilers cannot safely apply aggressive algebraic rewrites (e.g., eliminating deduplication or skipping multi-hop scans) because data invariants might be violated at runtime.
3. **Bag Semantics Explosion**: Intermediate multi-set path expansions require heap allocations and expensive runtime hash deduplication (`DISTINCT`).

### 1.1 The Impulse Immutable Optimization Thesis

```
   ┌───────────────────────┐         ┌───────────────────────────────┐
   │   Un-optimized AST    │         │  Immutable Snapshot (.imps)   │
   │  (CEL / Cypher / ImpK)│         │ • Exact Domain Cardinalities  │
   └───────────┬───────────┘         │ • Exact Degree Distributions  │
               │                     │ • Injective/Bijective Flags   │
               │                     │ • Min/Max Zone Maps per Attr  │
               │                     │ • Monotonicity & Null Counts  │
               └───────────┬─────────┴───────────────┬───────────────┘
                           │                         │
                           ▼                         ▼
               ┌─────────────────────────────────────────────┐
               │    AST Binding & Property Labeling Phase    │
               │  • Interval Bounds ([L, U])                 │
               │  • Morphism Type (Inj, Surj, Bij, Fn)       │
               │  • Algebraic Structures (Monoid, Lattice)   │
               │  • Nullability & Monotonicity Flags         │
               └─────────────────────┬───────────────────────┘
                                     │
                                     ▼
               ┌─────────────────────────────────────────────┐
               │    Algebraic Transformation & DCE Passes    │
               │  • Constant Folding & Zone Map Pruning      │
               │  • Semilattice Idempotency Rewrites         │
               │  • Deduplication (DISTINCT) Elimination     │
               │  • Join Inversion & Monoidal Pushdown       │
               │  • Monotonic Binary Search Range Slicing    │
               └─────────────────────┬───────────────────────┘
                                     │
                                     ▼
               ┌─────────────────────────────────────────────┐
               │      Optimized ImpScheme IR / ImpAsm        │
               │  (Allocation-Free SIMD / impOps Bytecode)   │
               └─────────────────────────────────────────────┘
```

> **The Immutable Optimization Thesis**: Because an Impulse Snapshot (`.imps` v0.9.0+) is **100% immutable and memory-mapped**, all structural topology, degree distributions, attribute value ranges, nullability flags, and algebraic morphism classifications are **exact, deterministic, and closed**. 
> 
> Binding an expression AST to a specific snapshot instance converts probabilistic heuristic optimization into **sound, deterministic algebraic reduction**.

---

## 2. Low-Hanging Fruit: Immediate Pruning & Early-Exit Optimizations

When an expression is bound to a snapshot, the compiler immediately evaluates boundary metadata to prune unreachable subtrees before generating intermediate representation code.

```
       [AST Filter Node: (u.age > 250 && u.status == "ACTIVE")]
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
   Predicate: u.age > 250                      Predicate: u.status == "ACTIVE"
   Snapshot Zone Map:                          Snapshot Dictionary:
   age.min = 18, age.max = 114                 status ∈ {"ACTIVE", "INACTIVE", "PENDING"}
          │                                           │
          ▼                                           ▼
   [EVALUATES: CONSTANT FALSE]                 [EVALUATES: VALID PREDICATE]
          │
          └─────────────────────┬─────────────────────┘
                                │
                                ▼
             Boolean Absorptive Law: FALSE && P ≡ FALSE
                                │
                                ▼
             [PRUNE ENTIRE NODE / RELATION TRAVERSAL]
```

### 2.1 Zone Map & Value Range Pruning
Every numerical, temporal, and lexicographical attribute in `.imps` contains precomputed `[MinVal, MaxVal]` bounds:
* **Rule**: For predicate `attr < C` or `attr > C`:
  $$\text{If } C < \text{attr}.\min \land \text{op} \in \{<, \le, =\} \implies \text{Node} \to \mathbf{False}$$
  $$\text{If } C > \text{attr}.\max \land \text{op} \in \{>, \ge, =\} \implies \text{Node} \to \mathbf{False}$$
* **Impact**: Predicates like `u.age > 250` (where `age.max == 114`) immediately fold to `false`. Boolean absorptive laws ($x \land \mathbf{False} \equiv \mathbf{False}$) prune parent conjunctions, eliminating entire graph traversal branches and foreign key lookups.

### 2.2 Nullability Contradiction Pruning
Attributes in `.imps` have an explicit nullability bitmask and exact `NullCount`:
* **Rule 1 (`NullCount == 0`)**: `attr != null` folds to `true`; `attr == null` folds to `false`.
* **Rule 2 (`NullCount == NodeCount`)**: `attr != null` folds to `false`; `attr == null` folds to `true`.
* **Impact**: Eliminates null-checking branch instructions and null-bitmap scans across hot SIMD loops.

### 2.3 Empty & Degenerate Relation Elimination
If a query specifies a traversal across relation $\mathcal{E}_R$ (e.g., `(u:User)-[:SUSPENDED_BY]->(a:Admin)`):
* **Rule**: If `RelationDirectoryEntry.EdgeCount == 0`, the traversal result is strictly the empty set $\emptyset$.
* **Impact**: The compiler replaces the entire traversal pipeline and subsequent downstream joins with an immediate empty vector return (`OP_RET_EMPTY`).

### 2.4 Disjoint Domain Contradiction
* **Rule**: If an expression asserts multiple mutually exclusive primary domains on a single variable (e.g., `(x:User:Group)`), the intersection $\mathcal{V}_{\text{User}} \cap \mathcal{V}_{\text{Group}} = \emptyset$ is provably empty by the `.imps` C-ABI specification.
* **Impact**: Static compilation error or instantaneous empty-set short-circuit.

### 2.5 String Dictionary / Bloom / Prefix Pruning
* **Rule**: For `u.country == "Atlantis"`, check string pool hash table or dictionary bounds. If the token does not exist in the snapshot's string pool:
  $$\text{StringPool.contains}(\text{"Atlantis"}) = \mathbf{False} \implies \text{Node} \to \mathbf{False}$$
* **Impact**: Avoids scanning SoA string offset tables and payload blobs entirely.

---

## 3. Snapshot Metadata & Statistics Specification

To empower the AST compiler, we formalize the exact statistics and structural invariants embedded within the `.imps` snapshot file layout.

### 3.1 Metadata Granularity & Sizing Budget

Statistics must remain lightweight to preserve $O(1)$ zero-copy cold start and fast memory mapping:
* **Per-Domain Statistics**: Embedded in `DomainCatalogEntry` (fixed 32 bytes).
* **Per-Relation Statistics**: Embedded in `RelationDirectoryEntry` (fixed 128 bytes) and extended via optional 64-byte structural descriptor blocks.
* **Per-Attribute Zone Maps**: Embedded in `AttributeDescriptor` (expanded from 44 bytes to fixed 64 bytes).

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        .imps Binary Snapshot Section Layout                            │
├────────────────────────┬───────────────────────────┬───────────────────────────────────┤
│ DomainCatalogEntry     │ RelationDirectoryEntry    │ AttributeDescriptor (64B)         │
│ (32 Bytes per domain)  │ (128 Bytes per relation)  │ (Zone Maps, Monotonicity, Nulls)  │
│ ├── DomainID           │ ├── RelationID            │ ├── NameOffset & TypeCode         │
│ ├── NodeCount (N)      │ ├── EdgeCount (E)         │ ├── DataOffset & DataBytes        │
│ ├── ActiveNodeCount    │ ├── Multiplicity (M:N..)  │ ├── MinVal (8B raw int/float/off) │
│ └── DensityFlags       │ ├── Min/Max/Avg OutDegree │ ├── MaxVal (8B raw int/float/off) │
│                        │ ├── Min/Max/Avg InDegree  │ ├── NullCount (32-bit uint)       │
│                        │ └── StructuralFlags       │ ├── DistinctCount (32-bit uint)   │
│                        │     (DAG, Inj, Bij, Sym)  │ └── MonotonicityFlags (8-bit enum)│
└────────────────────────┴───────────────────────────┴───────────────────────────────────┘
```

### 3.2 Extended Attribute Descriptor Layout (64 Bytes)

We extend the fixed POD `AttributeDescriptor` to embed exact zone maps and distribution metrics:

| Byte Offset | Field Name | C-ABI Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x0000` – `0x0003` | `NameOffset` | `uint32_t` | 4 Bytes | Offset into Shared String Table. |
| `0x0004` | `TypeCode` | `uint8_t` | 1 Byte | Base Primitive Type (`Bits 0..6`) + Nullable Flag (`Bit 7`). |
| `0x0005` | `Monotonicity` | `uint8_t` | 1 Byte | `0` = None, `1` = Monotonic Ascending, `2` = Monotonic Descending, `3` = Constant. |
| `0x0006` – `0x0007` | `Reserved` | `uint16_t` | 2 Bytes | Alignment padding (`0x0000`). |
| `0x0008` – `0x000B` | `Dimension` | `uint32_t` | 4 Bytes | Dimension ($1$ for scalar, $D > 1$ for embedding vectors). |
| `0x000C` – `0x0013` | `DataOffset` | `uint64_t` | 8 Bytes | 128B-aligned file offset to contiguous SoA payload. |
| `0x0014` – `0x001B` | `DataBytes` | `uint64_t` | 8 Bytes | Byte length of payload array. |
| `0x001C` – `0x0023` | `OffsetsOffset` | `uint64_t` | 8 Bytes | File offset to var-length offset array (`0` for fixed-width). |
| `0x0024` – `0x002B` | `OffsetsBytes` | `uint64_t` | 8 Bytes | Byte length of offset array. |
| `0x002C` – `0x0033` | `MinVal` | `uint64_t` | 8 Bytes | Exact minimum primitive value (scalar cast to `uint64_t` / `double`). |
| `0x0034` – `0x003B` | `MaxVal` | `uint64_t` | 8 Bytes | Exact maximum primitive value (scalar cast to `uint64_t` / `double`). |
| `0x003C` – `0x003F` | `NullCount` | `uint32_t` | 4 Bytes | Exact count of `NULL` elements in the column. |
| `0x0040` – `0x0043` | `DistinctCount` | `uint32_t` | 4 Bytes | Exact distinct value count (cardinality of active attribute values). |

### 3.3 Topology Multiplicity & Structural Flags

In `RelationDirectoryEntry`, `SectionFeatures` encodes strict relational topology classifications:

```c
// Topology Multiplicity (Bits 3..4)
#define IMP_REL_CARDINALITY_MASK     (3ULL << 3)
#define IMP_REL_CARDINALITY_M_N      (0ULL << 3) // Many-to-Many
#define IMP_REL_CARDINALITY_M_1      (1ULL << 3) // Many-to-One (Functional: Out-Degree <= 1)
#define IMP_REL_CARDINALITY_1_M      (2ULL << 3) // One-to-Many (Injective: In-Degree <= 1)
#define IMP_REL_CARDINALITY_1_1      (3ULL << 3) // One-to-One  (Bijective: In-Degree <= 1 && Out-Degree <= 1)

// Algebraic Structural Topology Flags (Bits 8..15)
#define IMP_REL_STRUCT_ACYCLIC       (1ULL << 8)  // Directed Acyclic Graph (DAG) - Guarantees termination
#define IMP_REL_STRUCT_SYMMETRIC     (1ULL << 9)  // Undirected / Symmetric (CSR == CSC)
#define IMP_REL_STRUCT_REFLEXIVE     (1ULL << 10) // Self-loops on all nodes (id <= R)
#define IMP_REL_STRUCT_TRANSITIVE    (1ULL << 11) // Transitive closure pre-materialized (R ∘ R ⊆ R)
#define IMP_REL_STRUCT_SURJECTIVE    (1ULL << 12) // Every target node has In-Degree >= 1
```

---

## 4. Algebraic Property Taxonomy & AST Node Labeling

During query compilation, the AST is decorated with an **Algebraic Property Vector** $\mathcal{P}(N)$ at every node $N$.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                AST Node Decoration Schema                              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ struct ImpulseAstNode {                                                                │
│     AstNodeType           type;            // CALL, IDENT, LITERAL, TRAVERSAL, FOLD    │
│     AstTypeSignature      data_type;       // BOOL, INT64, FLOAT64, NODE_SET, VECTOR   │
│     ImpulseIntervalBound  interval;        // [MinBound, MaxBound] (for ints/floats)   │
│     ImpulseNullability    null_state;      // DEFINITELY_NULL, NON_NULL, MAYBE_NULL    │
│     ImpulseMorphismClass  morphism;        // INJECTIVE, SURJECTIVE, BIJECTIVE, FN     │
│     ImpulseAlgebraicClass algebra;         // MONOID, SEMILATTICE, IDEMPOTENT, ABELIAN │
│     uint64_t              cardinality_max; // Upper bound on set/vector output size    │
│     uint8_t               monotonicity;    // MONO_ASC, MONO_DESC, NON_MONOTONIC      │
│ };                                                                                     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Taxonomy of Algebraic Labels

```
                                  Morphism Taxonomy
                                ┌───────────────────┐
                                │     Relation      │
                                └─────────┬─────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
         ┌─────────────────┐                             ┌─────────────────┐
         │ Functional (Fn) │                             │ Injective (Inj) │
         │ OutDegree ≤ 1   │                             │  InDegree ≤ 1   │
         └────────┬────────┘                             └────────┬────────┘
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          │
                                          ▼
                                 ┌─────────────────┐
                                 │ Bijective (Bij) │
                                 │ In=1, Out=1     │
                                 └─────────────────┘

                              Aggregation Algebra
                                ┌───────────────────┐
                                │     Semigroup     │
                                │   (Associative)   │
                                └─────────┬─────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
         ┌─────────────────┐                             ┌─────────────────┐
         │     Monoid      │                             │   Semilattice   │
         │ (Identity elem) │                             │  (Idempotent)   │
         └────────┬────────┘                             └────────┬────────┘
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          │
                                          ▼
                                 ┌─────────────────┐
                                 │   Join-Monoid   │
                                 │ (Comm + Idemp)  │
                                 └─────────────────┘
```

| Algebraic Label | Formal Mathematical Axiom | Examples in Impulse | Optimization Enabled |
| :--- | :--- | :--- | :--- |
| **Injective ($\mathrm{Inj}$)** | $f(x) = f(y) \implies x = y$ | Relations with `InDegree <= 1` (e.g., `EMBEDDED_IN`) | Deduplication (`DISTINCT`) can be skipped entirely; $|f(S)| = |S|$. |
| **Functional ($\mathrm{Fn}$)** | $\forall x, |\{y \mid (x, y) \in R\}| \le 1$ | Many-to-One relations (e.g., `BELONGS_TO_TENANT`) | Forward traversal replaces CSR search with $O(1)$ direct array index lookup. |
| **Bijective ($\mathrm{Bij}$)** | Injective $\land$ Functional $\land$ Surjective | One-to-One relations (e.g., `USER_TO_PROFILE`) | Isomorphism: forward and reverse traversals are 1:1, invertible without path explosion. |
| **Idempotent ($\mathrm{Idemp}$)** | $x \oplus x = x$ | $\max(a, b)$, $\min(a, b)$, Set Union ($\cup$), Bitwise OR ($\lor$) | Re-traversing visited nodes does not alter aggregate; cycle deduplication can be relaxed. |
| **Commutative ($\mathrm{Comm}$)** | $x \oplus y = y \oplus x$ | Addition ($+$), Multiplication ($\times$), $\land$, $\lor$, $\cup$ | Parallel SIMD reduction order is arbitrary; OpenMP thread reduction requires no critical locks. |
| **Associative ($\mathrm{Assoc}$)** | $(x \oplus y) \oplus z = x \oplus (y \oplus z)$ | Monoid operations $(\Sigma, \oplus, \varepsilon)$ | Associative tree rebalancing; map-reduce vector folding. |
| **Join-Semilattice** | Partially ordered set with LUB ($\sqcup$), idempotent, commutative, associative | Reachability sets, lattice-based authorization levels | Monotonic fixed-point iteration converges in $O(\text{height})$; early termination on $\top$. |
| **Distributive** | $a \otimes (b \oplus c) = (a \otimes b) \oplus (a \otimes c)$ | Semiring matrix-vector products $(\oplus, \otimes)$ | Push down multiplications/filters before aggregations/joins. |
| **Monotonic ($\mathrm{Mono}$)** | $x \le y \implies f(x) \le f(y)$ | Sorted timestamp attributes, cumulative sums | Range search via binary search ($O(\log N)$) rather than full SIMD vector scan ($O(N)$). |

---

## 5. Compiler Optimization Passes Enabled by AST Labels

```
                 ┌──────────────────────────────────────────────┐
                 │       Initial Un-optimized CEL/Query AST     │
                 └──────────────────────┬───────────────────────┘
                                        │
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │  Pass 1: Algebraic Dead Code Elimination     │
                 │  • Interval arithmetic fold ([L, U])         │
                 │  • Zone map & dictionary pruning             │
                 └──────────────────────┬───────────────────────┘
                                        │
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │  Pass 2: Deduplication & Bitset Elimination  │
                 │  • Injective/Bijective path check            │
                 │  • Skip OP_SET_DEDUPLICATE & bitset pooling  │
                 └──────────────────────┬───────────────────────┘
                                        │
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │  Pass 3: Semilattice & Reducer Pushdown      │
                 │  • Fold aggregators directly into CSR loops  │
                 │  • Exploit idempotency (x ⊕ x = x)           │
                 └──────────────────────┬───────────────────────┘
                                        │
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │  Pass 4: Join Direction & Topology Inversion │
                 │  • Compare AvgOutDegree vs AvgInDegree       │
                 │  • Select CSR (0x10) vs CSC (0x18)           │
                 └──────────────────────┬───────────────────────┘
                                        │
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │  Pass 5: Monotonic Range Slicing             │
                 │  • Replace linear vector scans with binary   │
                 │    search slicing on sorted columns          │
                 └──────────────────────┬───────────────────────┘
                                        │
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │  Pass 6: impOps Emitter (ImpScheme / ImpAsm) │
                 └──────────────────────────────────────────────┘
```

### 5.1 Pass 1: Algebraic Dead Code Elimination & Interval Arithmetic

The compiler traverses AST expressions bottom-up, synthesizing interval bounds $[L_i, U_i]$:
* **Addition $[a, b] + [c, d]$**: $[a + c, b + d]$
* **Multiplication $[a, b] \times [c, d]$** (for non-negative ranges): $[a \cdot c, b \cdot d]$
* **Relational Comparison**: If $[L_{\text{lhs}}, U_{\text{lhs}}] \cap [L_{\text{rhs}}, U_{\text{rhs}}] = \emptyset$, fold comparison node to constant `true` or `false`.

```
Example AST Rewrite:
  WHERE u.age > 100 AND u.score * 0.1 > 50
  Snapshot Bounds:
    u.age ∈ [18, 80]     ===> (u.age > 100) folds to FALSE
    u.score ∈ [0, 100]   ===> u.score * 0.1 ∈ [0, 10] ===> ( > 50) folds to FALSE

  Compiler Transformation:
    AND(FALSE, FALSE) ===> FALSE
    Result: Whole query is pruned. Zero bytecode emitted.
```

### 5.2 Pass 2: Deduplication (`DISTINCT`) & Bitset Elimination

In standard graph engines, traversing a multi-hop path `(a)-[:R1]->(b)-[:R2]->(c)` requires storing intermediate node frontiers in dynamic hash sets or Roaring bitsets to prevent duplicates:

$$\text{Cardinality Explosion}: \quad |S_k| = O(d^k)$$

**Theorem (Injective Path Uniqueness)**:
> Let $\tau = R_k \circ R_{k-1} \circ \dots \circ R_1$ be a path relation. If every constituent relation $R_i$ is labeled **Injective** ($\mathrm{Inj}$) or **Bijective** ($\mathrm{Bij}$), then for any initial node set $S_0$ where elements are distinct:
> $$|\tau(S_0)| = \sum_{v \in S_0} |\tau(\{v\})| \quad \text{and all destination IDs are guaranteed distinct.}$$

* **Compiler Transformation**:
  1. Inspect path relation sequence $[R_1, R_2, \dots, R_k]$.
  2. If $\forall i, \text{Multiplicity}(R_i) \in \{\mathrm{1:1}, \mathrm{1:M}\}$ (injective in forward direction):
     - **ELIMINATE** all intermediate `OP_SET_DEDUPLICATE` opcodes.
     - **ELIMINATE** scratch bitset acquisition (`acquire_bitset`).
     - **EMIT** direct streaming pipeline writing directly to the output register.

### 5.3 Pass 3: Semilattice & Reducer Pushdown

When a query computes an aggregation over a traversal (e.g., `MAX(p.rating)` or `COUNT(g)`):
* **Traditional Execution**:
  $$\text{Source Set} \xrightarrow{\text{Expand}} \text{Target Nodes} \xrightarrow{\text{Materialize}} \text{Load Attributes} \xrightarrow{\text{Fold}} \text{Scalar}$$
* **Semilattice Reduction ($\sqcup$)**:
  Because $(\max, -\infty)$ forms a join-semilattice where $x \sqcup x = x$ (idempotence) and $x \sqcup y = y \sqcup x$ (commutativity):
  - The compiler **pushes the reduction directly into the CSR neighborhood inner loop**.
  - **No intermediate node array or target vector is ever materialized**.
  - Register `R_acc` holds the rolling scalar accumulator, updated with SIMD `_mm512_max_epi32`.

### 5.4 Pass 4: Join Direction & Topology Inversion

Given a traversal query between two node sets $\mathcal{A}$ and $\mathcal{B}$ connected by relation $\mathcal{E}_R$:
* **Forward Cost**: $|\mathcal{A}| \times \text{AvgOutDegree}(R)$
* **Reverse Cost**: $|\mathcal{B}| \times \text{AvgInDegree}(R)$

* **Compiler Transformation**:
  The compiler inspects `RelationDirectoryEntry` statistics:
  $$\text{If } |\mathcal{B}| \times \text{AvgInDegree}(R) < |\mathcal{A}| \times \text{AvgOutDegree}(R) \land \text{SectionFeatures.has}(\text{CSC}):$$
  $$\text{REWRITE } \mathcal{A} \xrightarrow{R} \mathcal{B} \quad \Longrightarrow \quad \mathcal{B} \xleftarrow{R^T} \mathcal{A}$$
  - Switches opcode from `OP_CSR_WALK` (`0x10`) to `OP_CSC_WALK` (`0x18`).
  - Swaps source/target binding registers, cutting CPU cache misses by orders of magnitude.

### 5.5 Pass 5: Monotonic Range Slicing & Binary Search

For range predicates like `WHERE post.created_at >= 1700000000 AND post.created_at < 1700086400`:
* If `AttributeDescriptor.Monotonicity == MONOTONIC_ASC`:
  - **Do NOT emit** `OP_NODE_FILTER` (linear $O(N)$ SIMD scan).
  - **Emit** `OP_RANGE_SLICE_ASC` ($O(\log N)$ binary search over contiguous SoA array).
  - Directly extracts contiguous index slice $[i_{\text{start}}, i_{\text{end}}]$, generating the node frontier in $< 10\text{ ns}$.

---

## 6. End-to-End Concrete Optimization Walkthroughs

### 6.1 Walkthrough 1: ReBAC / ABAC Policy Expression

Consider a fine-grained authorization check written in CEL:

```javascript
// Policy: Document read permission
user.status == "ACTIVE" && 
(user.clearance_level >= doc.classification_level || 
 user.id in doc.explicit_readers)
```

#### Snapshot Binding & Statistics
* Domain `User`: `NodeCount = 50,000`
* Domain `Document`: `NodeCount = 1,000,000`
* Bound Instances: `user.id = 42`, `doc.id = 999`
* Snapshot Metadata:
  - `User.status.DistinctCount = 1` (All users in this snapshot are `"ACTIVE"`).
  - `User.clearance_level.MaxVal = 3`.
  - `doc[999].classification_level = 5`.
  - Relation `doc.explicit_readers`: `EdgeCount = 0` (No explicit readers configured for `doc#999`).

#### AST Property Decoration & Optimization Trace

```
1. Initial AST:
   AND(
     EQUALS(user.status, "ACTIVE"),
     OR(
       GTE(user.clearance_level, doc.classification_level),
       IN(user.id, doc.explicit_readers)
     )
   )

2. Property Labeling & Interval Evaluation:
   • user.status == "ACTIVE":
     - Snapshot invariant: user.status is uniformly "ACTIVE"
     - Folds to: TRUE
   • GTE(user.clearance_level, doc.classification_level):
     - Interval(user.clearance_level) = [1, 3]
     - Literal(doc[999].classification_level) = 5
     - [1, 3] >= 5 is impossible ===> Folds to: FALSE
   • IN(user.id, doc.explicit_readers):
     - Relation explicit_readers for doc#999 has Degree = 0
     - Folds to: FALSE

3. Algebraic Reduction:
   • OR(FALSE, FALSE) ===> FALSE
   • AND(TRUE, FALSE) ===> FALSE

4. Final Generated ImpScheme / ImpAsm:
   ; Zero graph traversals, zero memory lookups executed!
   CONST_BOOL R0, 0
   OP_RET R0
```

### 6.2 Walkthrough 2: Multi-Hop Traversal with Aggregation

Consider an analytical Cypher / ImpK query:

```cypher
MATCH (u:User {id: 101})-[:BELONGS_TO]->(t:Tenant)-[:HAS_PROJECT]->(p:Project)
RETURN MAX(p.priority)
```

#### Snapshot Invariants
* Relation `BELONGS_TO`: Multiplicity `M:1` (Functional, Out-Degree $\le 1$).
* Relation `HAS_PROJECT`: Multiplicity `1:M` (Injective, In-Degree $\le 1$).
* Aggregator `MAX`: Join-semilattice $(\mathbb{Z}, \max, -\infty)$, idempotent and commutative.
* Attribute `Project.priority`: `TypeCode = INT32`, `NullCount = 0`, `MinVal = 1`, `MaxVal = 10`.

#### AST Optimization Trace

```
1. Multiplicity Analysis:
   • BELONGS_TO is M:1 ===> Exactly 1 tenant ID (or 0). Flat array lookup.
   • HAS_PROJECT is 1:M (Injective) ===> Disjoint project ID sets per tenant.
     ===> NO DEDUPLICATION NEEDED.

2. Aggregator Pushdown:
   • MAX is an idempotent semilattice fold.
   • Push MAX directly into HAS_PROJECT CSR neighborhood scanner.
   • No intermediate Project NodeSet vector materialized in memory.

3. Generated ImpAsm Bytecode:
```

```nasm
; --- Optimized ImpAsm Assembly Output ---
; R0: User ID (Literal 101)
; R1: Tenant ID (Resolved via flat M:1 array)
; R2: Max Priority Accumulator (Initialized to INT32_MIN)

.text
_query_start:
    ; Step 1: O(1) Flat Dereference for M:1 relation (no CSR row offsets needed)
    OP_LOAD_FLAT_EDGE     R1, REL_BELONGS_TO, 101       ; R1 = Tenant ID
    CMP_EQ_IMM            R1, 0xFFFFFFFF, _empty_exit   ; If no tenant, exit early

    ; Step 2: Pushdown MAX aggregator directly into CSR traversal loop
    OP_CSR_FOLD_MAX_I32   R2, REL_HAS_PROJECT, R1, ATTR_PROJECT_PRIORITY

    ; Step 3: Return scalar result in R2
    OP_RET                R2

_empty_exit:
    OP_RET_NULL
```

---

## 7. C-ABI Structural Definitions for Compiler Integration

To implement this optimization engine in `impulse-graph-compile` and `impulse-graph-core`, the following C-ABI structures define the compiler interface:

```c
#ifndef IMPULSE_CEL_AST_OPTIMIZE_H
#define IMPULSE_CEL_AST_OPTIMIZE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Monotonicity enum
typedef enum ImpulseMonotonicity {
    IMP_MONO_NONE       = 0x00,
    IMP_MONO_ASCENDING  = 0x01,
    IMP_MONO_DESCENDING = 0x02,
    IMP_MONO_CONSTANT   = 0x03
} ImpulseMonotonicity;

// Algebraic Morphism Classification
typedef enum ImpulseMorphismClass {
    IMP_MORPHISM_GENERAL    = 0x00,
    IMP_MORPHISM_FUNCTIONAL = 0x01, // Many-to-One (Out-Degree <= 1)
    IMP_MORPHISM_INJECTIVE  = 0x02, // One-to-Many (In-Degree <= 1)
    IMP_MORPHISM_BIJECTIVE  = 0x03  // One-to-One  (In-Degree <= 1 && Out-Degree <= 1)
} ImpulseMorphismClass;

// Algebraic Structure Classification
typedef enum ImpulseAlgebraicClass {
    IMP_ALG_NONE         = 0x00,
    IMP_ALG_SEMIGROUP    = 0x01, // Associative
    IMP_ALG_MONOID       = 0x02, // Associative + Identity
    IMP_ALG_COMMUTATIVE  = 0x04, // Commutative (Abelian)
    IMP_ALG_IDEMPOTENT   = 0x08, // x ⊕ x = x (Semilattice)
    IMP_ALG_DISTRIBUTIVE = 0x10  // a ⊗ (b ⊕ c) = (a ⊗ b) ⊕ (a ⊗ c)
} ImpulseAlgebraicClass;

// Scalar Value Interval
typedef struct ImpulseIntervalBound {
    int64_t  min_int;
    int64_t  max_int;
    double   min_double;
    double   max_double;
---

## 7. Functional Programming Perspective: Monotonic Homomorphisms & Kleisli Composition

Through the lens of **Category Theory** and **Functional Programming**, queries and graph traversals are compositions of functors, monads, and algebraic homomorphisms.

```
       Category-Theoretic Commuting Diagram for Monotonic Homomorphisms
       
                       f = log (Strictly Monotonic Increasing)
               Set(A) ─────────────────────────────────────────> Set(B)
                 │                                                 │
                 │                                                 │
          fold(max)                                          fold(max)
                 │                                                 │
                 ▼                                                 ▼
                 A    ─────────────────────────────────────────>   B
                                       f = log
```

### 7.1 Monotonicity as a Lattice Homomorphism: $\max(f(X)) \equiv f(\max(X))$

#### 7.1.1 The Mathematical Principle
Let $(A, \le_A)$ and $(B, \le_B)$ be totally ordered sets viewed as **join-semilattices** where the join operation is supremum / maximum ($x \sqcup y = \max(x, y)$).

A function $f: A \to B$ is a **join-semilattice homomorphism** if and only if it preserves finite joins:
$$f(x \sqcup y) = f(x) \sqcup f(y) \quad \iff \quad f(\max(x, y)) = \max(f(x), f(y))$$

By induction, for any non-empty finite collection $S \subseteq A$:
$$\max_{x \in S} f(x) = f\left(\max_{x \in S} x\right) \quad \text{(when $f$ is strictly monotonic increasing)}$$

Conversely, if $g: A \to B$ is **strictly monotonic decreasing** (such as $g(x) = -x$ or $g(x) = \frac{1}{x}$ for $x > 0$), $g$ inverts joins into meets (infimum / minimum):
$$\max_{x \in S} g(x) = g\left(\min_{x \in S} x\right) \quad \text{and} \quad \min_{x \in S} g(x) = g\left(\max_{x \in S} x\right)$$

#### 7.1.2 The Execution Complexity Leap

Consider the query:
```sql
SELECT MAX(x) FROM (SELECT log(v) AS x FROM table_t);
```

```
Un-optimized Pipeline:
  Array[N] of v ──[Compute log(v) N times]──> Array[N] of floats ──[Fold MAX]──> Result
  Complexity: O(N) transcendental Math.log calls + O(N) float comparisons + temporary array allocation.

Optimized Pipeline via Homomorphism Pushdown:
  Array[N] of v ──[Fold MAX on raw ints/floats]──> max_v ──[Compute log(max_v) ONCE]──> Result
  Complexity: O(N) SIMD vector MAX + EXACTLY 1 Math.log call.
  
Zero-Scan Instantaneous Zone Map Path (if query is unfiltered over entire domain):
  max_v = metadata.attr("v").MaxVal ──[Compute log(max_v) ONCE]──> Result
  Complexity: O(1) latency (< 2 nanoseconds), ZERO array reads, ZERO vector scans!
```

---

### 7.2 AST Node Labels Required to Enable Monotonic & Algebraic Rewrites

To make such rewrites trivial for compiler passes to identify, the AST nodes are decorated with the following explicit algebraic labels:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                         AST Algebraic & Functorial Labels                              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Variance / Monotonicity Label (VarianceClass)                                       │
│    ├── MONO_STRICT_INC : x < y  ⟹  f(x) < f(y)   (e.g., log(x), exp(x), x + c, 2*x)   │
│    ├── MONO_WEAK_INC   : x ≤ y  ⟹  f(x) ≤ f(y)   (e.g., floor(x), ceil(x))            │
│    ├── MONO_STRICT_DEC : x < y  ⟹  f(x) > f(y)   (e.g., -x, 1/x for x>0)              │
│    ├── MONO_WEAK_DEC   : x ≤ y  ⟹  f(x) ≥ f(y)   (e.g., -floor(x))                    │
│    └── NON_MONOTONIC   : (e.g., sin(x), hash(x), x^2 over negative & positive reals)   │
│                                                                                        │
│ 2. Homomorphism Commutativity Bitmask (HomomorphismFlags)                              │
│    ├── COMMUTES_WITH_MAX  : f(max(S)) ≡ max(f(S))                                     │
│    ├── COMMUTES_WITH_MIN  : f(min(S)) ≡ min(f(S))                                     │
│    ├── COMMUTES_WITH_SUM  : f(∑ x) ≡ ∑ f(x)    (Linear: f(x) = c * x)                  │
│    └── DISTRIBUTES_OVER_OR: f(a ∨ b) ≡ f(a) ∨ f(b)                                     │
│                                                                                        │
│ 3. Domain Range Guard (DomainRangeBound)                                                │
│    ├── Validity Interval : e.g., log(x) requires x ∈ (0, ∞)                            │
│    └── Snapshot Guard   : Bound checked against Attr.MinVal > 0                        │
│                                                                                        │
│ 4. Purity & Determinism                                                                │
│    └── IS_PURE_DETERMINISTIC : Guarantees f(x) has no side-effects and is repeatable   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

#### AST Structure Before and After Labeling

```
      [AGG_FOLD: op=MAX]                        [AGG_FOLD: op=MAX]
              │                                         │
              ▼                                         ▼
      [MAP_EXPR: f=log]                 ───►    [MAP_EXPR: f=log]
              │                                   Labels:
              ▼                                     • Variance: MONO_STRICT_INC
      [COLUMN_REF: attr="v"]                        • Homomorphism: COMMUTES_WITH_MAX
                                                    • Guard: [MinVal=2, MaxVal=1000] > 0
                                                    • Purity: PURE_DETERMINISTIC
                                                        │
                                                        ▼
                                                [COLUMN_REF: attr="v"]
```

#### Compiler Rewrite Rule (Pattern Match)

$$\text{AGG\_FOLD}(\max, \text{MAP\_EXPR}(f, X)) \xrightarrow{f \in \text{MONO\_STRICT\_INC} \land \text{ValidGuard}(f, X)} f(\text{AGG\_FOLD}(\max, X))$$

$$\text{AGG\_FOLD}(\max, \text{MAP\_EXPR}(g, X)) \xrightarrow{g \in \text{MONO\_STRICT\_DEC} \land \text{ValidGuard}(g, X)} g(\text{AGG\_FOLD}(\min, X))$$

---

### 7.3 Kleisli Composition & Transitive Relational Fusion

In the **Kleisli Category** of the Semiring-Weighted Monad $\mathbf{Kl}(\mathcal{W}_R)$, a multi-hop graph traversal is the Kleisli composition of relational morphisms:

$$(g \odot f)(x) = \mu_{\mathcal{W}_R}\left(\mathcal{W}_R(g)(f(x))\right) = \bigoplus_{y \in f(x)} g(y)$$

```
                     f: A → W_R(B)             g: B → W_R(C)
           NodeSet<A> ────────────> NodeSet<B> ────────────> NodeSet<C>
               │                                                ▲
               │                                                │
               └────────────────────────────────────────────────┘
                                  g ⊙ f: A → W_R(C)
```

#### AST Labels for Kleisli Optimizations
When multiple traversal steps appear in sequence:
* **`KLEISLI_AFFINE`**: Each step has multiplicity $M:1$ or $1:1$ ($\text{OutDegree} \le 1$). The composition $g \odot f$ collapses into a single direct array lookup `g.target_array[f.target_array[x]]` with zero intermediate allocations.
* **`TRANSITIVE_REDUCTION`**: If a snapshot metadata indicates relation $R$ has `IMP_REL_STRUCT_TRANSITIVE` enabled ($R \circ R \subseteq R$), repeated Kleisli self-composition $(R \odot R \odot \dots \odot R)$ collapses to a single step $R$.
* **`MONOIDAL_FUSION`**: When a map-reduce aggregate is composed after a Kleisli traversal:
  $$\text{fold}_{\oplus}(\mu(M(f)(S))) \equiv \bigoplus_{x \in S} \text{fold}_{\oplus}(f(x))$$
  The intermediate frontier is never materialized; the reduction folds directly during the CSR row traversal.

---

## 8. Frontier State Semantics, Filter-Reduction Commutation & Morphism Theorems

### 8.1 Frontier Formalization: The Sheaf of State Fibers $(\mathcal{V} \times \mathcal{S})$

In Impulse Graph Engine, a frontier is not merely a collection of node IDs; it is a **Grothendieck Sheaf / Vector Fiber Bundle** over the base space of discrete node domains:

$$\mathcal{F} \subseteq \mathcal{V} \times \mathcal{S}$$

Where:
* $\mathcal{V}$ is the discrete base manifold of Node IDs ($0 \dots N-1$).
* $\mathcal{S}$ is the **State Fiber** carried along each node (e.g., accumulated path weight, minimum hop distance, security label bitmask, lineage vector).

```
                      The Frontier State Fiber Bundle
                      
      State Fiber (S) ┌───┐       ┌───┐       ┌───┐
                      │s_1│       │s_2│       │s_3│   (Weights / Labels / Distances)
                      └───┘       └───┘       └───┘
                        │           │           │     (Fibration Projection π)
      Base Space (V)    ▼           ▼           ▼
                      Node 0      Node 1      Node 2  (0 ... N-1 Off-Heap Index)
```

A relational traversal step is a **Kleisli Morphism in the State-Weighted Monad**:
$$\mathcal{T}_R: (v, s) \mapsto \left\{ (u, s') \;\middle|\; u \in \mathrm{Adj}_R(v), \; s' = \delta(s, v, u, e_{v \to u}) \right\}$$

#### The Implicit Monoidal Reduction on Collision ($\mu$)
When multiple traversal paths reach the same target node $u \in \mathcal{V}$, an **implicit monoidal reduction** folds the incoming state fibers:

$$s_{\text{final}}(u) = \bigoplus_{(v, s) \in \mathrm{In}(u)} \delta(s, v, u, e_{v \to u})$$

The algebraic properties of the reduction operator $(\mathcal{S}, \oplus, \varepsilon)$ determine how the compiler manages frontier memory and state:

| Fiber Monoid $(\mathcal{S}, \oplus)$ | Concrete Example | Memory Representation | Hardware Implementation |
| :--- | :--- | :--- | :--- |
| **Trivial Monoid $(\mathbf{1}, \land)$** | Pure Reachability (Visited / Not Visited) | Dense Roaring Bitset or Flat Byte Mask | `OP_CSR_WALK` + AVX-512 bitwise OR |
| **Join-Semilattice $(\mathbb{R} \cup \{\infty\}, \min)$** | Shortest Path / Bellman-Ford | Flat SoA `float weights[N]` | `_mm512_min_ps` atomic vector scatter |
| **Bounded Set Monoid $(\mathcal{P}_{\le 64}(K), \cup)$** | Multi-tenant lineage bitmask | Flat SoA `uint64_t masks[N]` | `_mm512_or_epi64` |
| **Linear Vector Space $(\mathbb{R}^D, +)$** | GNN Message Passing ($\sum W h_v$) | Contiguous SoA matrix $[N \times D]$ | AVX-512 FMA (`_mm512_fmadd_ps`) |

---

### 8.2 Shoving Filters Through Reductions (Filter-Reduction Commutation)

A fundamental challenge in graph query compilation is determining when a predicate filter $P: \mathcal{S} \to \text{Bool}$ can be **pushed through (before) the implicit reduction $\bigoplus$**.

```
    Standard Pipeline:
      Frontier ──[Traverse Relation R]──> Raw States ──[Fold ⨁]──> Reduced States ──[Filter P]──> Result

    Commutative Pushdown Pipeline (Zero Unnecessary Expansions):
      Frontier ──[Prune via Guard P_pre]──> Filtered Frontier ──[Traverse R]──> Reduced States (P Holds)
```

#### Theorem 1 (Semilattice Ideal Filter Pushdown / Branch-and-Bound)
> Let $(\mathcal{S}, \sqsubseteq, \sqcup)$ be a join-semilattice where the reduction is $\sqcup$. A filter predicate $P(s) \equiv (s \sqsubseteq K)$ is a **lower ideal**. Because $s_1 \sqcup s_2 \sqsubseteq K \iff (s_1 \sqsubseteq K) \land (s_2 \sqsubseteq K)$, the filter **distributes perfectly over the reduction**:
> $$P\left(\bigoplus_{i} s_i\right) \equiv \bigwedge_{i} P(s_i)$$

* **Compiler Optimization**:
  - **Distance Bounding (`distance <= MaxHops`)**: If accumulated hop count exceeds $K$, prune the path **before** traversal.
  - **Alpha-Beta / Score Pruning**: In $(\max, +)$ routing, if $s + \text{heuristic}(v) < \text{current\_max}$, drop node $v$ from the active frontier prior to CSR expansion.

#### Theorem 2 (Annihilator Short-Circuiting / Absorptive Boundary)
> If the monoid $(\mathcal{S}, \oplus, \varepsilon)$ contains an **absorbing element (annihilator $\top$)** such that $x \oplus \top = \top$:
> * For $(\text{Bool}, \lor, \mathbf{0})$: $\top = \mathbf{1}$ (`true`).
> * For $(\text{SecurityLattice}, \sqcup, \bot)$: $\top = \text{ROOT\_ADMIN}$.

* **Compiler Optimization**:
  As soon as any state fiber evaluates to $\top$, the reduction is instantaneously complete for that target node. The compiler emits an early-exit loop break (`CMP_EQ_IMM + JMP`), skipping all remaining incoming edges for that node.

---

### 8.3 Distinct Count ($\text{COUNT}(\text{DISTINCT } X)$) & Algebraic Cardinality Bypass

Traditional engines compute `COUNT(DISTINCT attr)` via expensive hash tables ($O(N)$ allocations and hash collisions). Impulse uses snapshot algebraic labels to eliminate deduplication:

```
                  Algebraic Deduplication Elimination Hierarchy
                  
                       Is the Relation Injective (1:M / 1:1)?
                                     │
                       ┌─────────────┴─────────────┐
                      YES                          NO
                       │                           │
         ┌─────────────▼─────────────┐     ┌───────▼───────────────────┐
         │ Zero Deduplication Needed │     │ Is Aggregator Idempotent? │
         │ COUNT(DISTINCT) ≡ COUNT() │     │ (e.g., MAX, MIN, OR)      │
         │ Cost: O(1) sum of degrees │     └───────┬───────────────────┘
         └───────────────────────────┘             │
                                       ┌───────────┴───────────┐
                                      YES                      NO
                                       │                       │
                         ┌─────────────▼──────────┐  ┌─────────▼───────────────┐
                         │ Deduplication Bypass   │  │ Flat Scratch Bitset     │
                         │ Multi-paths fold safely│  │ Deduplication (No Hash) │
                         └────────────────────────┘  └─────────────────────────┘
```

1. **Injective Path Invariance**: If relation $R$ is **Injective** ($\mathrm{InDegree} \le 1$), then distinct source nodes map to strictly disjoint target node sets:
   $$\text{COUNT}(\text{DISTINCT } R(S)) \equiv |R(S)| \equiv \sum_{v \in S} \text{OutDegree}(v)$$
   * **Compiler Transformation**: Replaces `OP_SET_DEDUPLICATE` with a simple summation over CSR row offset differences $\sum (\text{offsets}[v+1] - \text{offsets}[v])$ in $O(|S|)$ without reading target IDs.
2. **Snapshot Header $O(1)$ Direct Lookup**:
   If the query asks for `COUNT(DISTINCT node.attr)` across an entire domain without filters:
   $$\text{Result} = \text{AttributeDescriptor.DistinctCount}$$
   * **Cost**: Evaluates in **$< 1\text{ ns}$ ($O(1)$)** directly from Section 2 Header metadata.

---

### 8.4 Categorical Isomorphisms, Endomorphisms & Monad Powering

```
                            Categorical Morphism Spectrum
                            
    ┌──────────────────────────┬──────────────────────────┬──────────────────────────┐
    │       Isomorphisms       │      Endomorphisms       │       Idempotent         │
    │     (Reversible 1:1)     │      (A → A Loops)       │      Monad Closures      │
    ├──────────────────────────┼──────────────────────────┼──────────────────────────┤
    │ • Perfect Invertibility  │ • Binary Exponentiation  │ • Pre-materialized       │
    │ • Zero-Loss Bidirection  │   (R^8 = ((R^2)^2)^2)    │   Transitive Closure     │
    │ • Flat Array Lookup      │ • Self-Adjoint (R = R^T) │ • Multi-hop R^+ ⟹ R*    │
    │   in O(1)                │ • Spectral GraphBLAS     │ • O(1) Reachability      │
    └──────────────────────────┴──────────────────────────┴──────────────────────────┘
```

#### 8.4.1 Endomorphism Powering & Binary Exponentiation ($O(k) \to O(\log k)$)
When a relation is an **endomorphism** on a homogenous domain ($\mathcal{E}_R: \mathcal{V}_A \to \mathcal{V}_A$), multi-hop traversal $R^k$ represents matrix powering over the semiring $(K, \oplus, \otimes)$:

$$\mathbf{A}_{R^k} = (\mathbf{A}_R)^k$$

* **Compiler Optimization**:
  For deep constant hop reachability (e.g., $k = 16$):
  - Standard engine: Executes 16 sequential frontier expansion passes ($O(16 \cdot E)$).
  - Impulse Compiler: Emits **matrix exponentiation by squaring** ($(\mathbf{A}^2 \to \mathbf{A}^4 \to \mathbf{A}^8 \to \mathbf{A}^{16})$), executing in $\log_2(16) = 4$ matrix multiplies.

#### 8.4.2 Self-Adjoint Morphisms (Undirected Graphs)
If snapshot metadata labels a relation as **Symmetric / Self-Adjoint** (`IMP_REL_STRUCT_SYMMETRIC`):
$$\mathbf{A}_R = \mathbf{A}_R^T \quad (\mathrm{CSR} \equiv \mathrm{CSC})$$
* **Compiler Optimization**:
  - `OP_CSC_WALK` is rewritten to `OP_CSR_WALK`.
  - The CSC transpose array is omitted from disk, saving $50\%$ storage.

#### 8.4.3 The "Banana-Split" Theorem (Catamorphism Fusion)
In Category Theory, folds over inductive structures are **Catamorphisms** ($\mathrm{cata}(f)$). When a query computes multiple aggregations over the same traversal:
```sql
SELECT COUNT(x), SUM(x.val), MAX(x.val), MIN(x.val) FROM ...
```

By the **Banana-Split Theorem** for catamorphisms:
$$\langle \mathrm{cata}(f), \mathrm{cata}(g) \rangle \equiv \mathrm{cata}(f \times g)$$

* **Compiler Optimization**:
  Instead of 4 separate passes or dynamic tuple allocations, the compiler fuses all 4 reducers into a **single vectorized register pass**:
  ```nasm
  ; Single-pass SIMD register accumulator
  VPADDD   ZMM0, ZMM0, ZMM_VAL   ; ZMM0 = Rolling Sum
  VPADDD   ZMM1, ZMM1, ZMM_ONE   ; ZMM1 = Rolling Count
  VPMAXSD  ZMM2, ZMM2, ZMM_VAL   ; ZMM2 = Rolling Max
  VPMINSD  ZMM3, ZMM3, ZMM_VAL   ; ZMM3 = Rolling Min
  ```

---

## 9. C-ABI Structural Definitions for Compiler Integration

To implement this optimization engine in `impulse-graph-compile` and `impulse-graph-core`, the following C-ABI structures define the compiler interface:

```c
#ifndef IMPULSE_CEL_AST_OPTIMIZE_H
#define IMPULSE_CEL_AST_OPTIMIZE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Monotonicity / Variance enum
typedef enum ImpulseMonotonicity {
    IMP_MONO_NONE       = 0x00,
    IMP_MONO_STRICT_INC = 0x01, // Strictly increasing: x < y => f(x) < f(y)
    IMP_MONO_WEAK_INC   = 0x02, // Non-decreasing: x <= y => f(x) <= f(y)
    IMP_MONO_STRICT_DEC = 0x03, // Strictly decreasing: x < y => f(x) > f(y)
    IMP_MONO_WEAK_DEC   = 0x04, // Non-increasing: x <= y => f(x) >= f(y)
    IMP_MONO_CONSTANT   = 0x05
} ImpulseMonotonicity;

// Homomorphism Commutativity Flags
typedef enum ImpulseHomomorphismFlags {
    IMP_HOMO_NONE               = 0x0000,
    IMP_HOMO_COMMUTES_WITH_MAX  = 0x0001, // f(max(S)) == max(f(S))
    IMP_HOMO_COMMUTES_WITH_MIN  = 0x0002, // f(min(S)) == min(f(S))
    IMP_HOMO_COMMUTES_WITH_SUM  = 0x0004, // f(sum(S)) == sum(f(S)) [Linear]
    IMP_HOMO_DISTRIBUTES_OR     = 0x0008, // f(a || b) == f(a) || f(b)
    IMP_HOMO_DISTRIBUTES_AND    = 0x0010  // f(a && b) == f(a) && f(b)
} ImpulseHomomorphismFlags;

// Algebraic Morphism Classification
typedef enum ImpulseMorphismClass {
    IMP_MORPHISM_GENERAL    = 0x00,
    IMP_MORPHISM_FUNCTIONAL = 0x01, // Many-to-One (Out-Degree <= 1)
    IMP_MORPHISM_INJECTIVE  = 0x02, // One-to-Many (In-Degree <= 1)
    IMP_MORPHISM_BIJECTIVE  = 0x03  // One-to-One  (In-Degree <= 1 && Out-Degree <= 1)
} ImpulseMorphismClass;

// Algebraic Structure Classification
typedef enum ImpulseAlgebraicClass {
    IMP_ALG_NONE         = 0x00,
    IMP_ALG_SEMIGROUP    = 0x01, // Associative
    IMP_ALG_MONOID       = 0x02, // Associative + Identity
    IMP_ALG_COMMUTATIVE  = 0x04, // Commutative (Abelian)
    IMP_ALG_IDEMPOTENT   = 0x08, // x ⊕ x = x (Semilattice)
    IMP_ALG_DISTRIBUTIVE = 0x10  // a ⊗ (b ⊕ c) = (a ⊗ b) ⊕ (a ⊗ c)
---

## 9. Universal Algebraic Type System & Equational Rewrite Engine

To avoid the **"Whack-a-Mole" Anti-Pattern** (writing ad-hoc heuristic rewrite rules for every combination of functions and operators), Impulse implements a **Universal Algebraic Type System** grounded in Universal Algebra and Category Theory.

Instead of matching specific function names (e.g. `log`, `sin`, `age`), the compiler assigns every AST node an **Algebraic Signature**:

$$\Sigma = \langle \mathcal{C}, \oplus, \varepsilon, \top, \sqsubseteq, \mathcal{A} \rangle$$

Where:
* $\mathcal{C}$: Carrier data type (e.g. `uint32`, `float64`, $\mathcal{V} \times \mathcal{S}$).
* $\oplus$: Binary composition / reduction operator.
* $\varepsilon$: Identity (neutral) element.
* $\top$: Absorbing (annihilating) element.
* $\sqsubseteq$: Partial ordering relation.
* $\mathcal{A} \subseteq \{\text{Assoc}, \text{Comm}, \text{Idemp}, \text{Distrib}, \text{Invertible}, \text{StrictMono}\}$: Satisfied algebraic axioms.

```
                  The Axiomatic Algebraic Hierarchy
                  
               Magma (Closed binary operation ⊕)
                         │
                         ▼ [+ Assoc: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)]
                     Semigroup
                         │
                         ▼ [+ Identity: a ⊕ ε = a]
                      Monoid
                         │
        ┌────────────────┴────────────────┐
        ▼ [+ Commutative: a ⊕ b = b ⊕ a]   ▼ [+ Idempotent: a ⊕ a = a]
   Abelian Monoid                     Join-Semilattice (⊔)
        │                                 │
        └────────────────┬────────────────┘
                         ▼
               Commutative Semilattice
                         │
                         ▼ [+ Second op ⊗ with Distributivity]
                     Semiring (K, ⊕, ⊗, 0, 1)
```

---

### 9.1 Systematic Bottom-Up Algebraic Property Inference

Properties are inferred systematically using an **Algebraic Type Inference Pass** via inductive compositional rules:

```
                            AST Property Inference Rules
                            
        Leaf Nodes (Literals, Columns) ──[Snapshot Metadata Binding]──┐
                                                                      ▼
        Composite Expressions (f ∘ g)  ──[Functorial Composition Rules]──► Annotated AST
                                                                      ▲
        Folds & Reducers (argMin, sum) ──[Product Monoid Construction]─┘
```

#### Rule 1: Leaf Axioms (Bound from Snapshot Metadata)
* **Constant Literals $c$**: Type is scalar, `IntervalBound` is $[c, c]$, `Variance` is `CONSTANT`.
* **Column Reference $v$**: `IntervalBound` is $[Attr.MinVal, Attr.MaxVal]$, `Nullability` is determined by $Attr.NullCount$, `Monotonicity` is inherited from $Attr.Monotonicity$.

#### Rule 2: Unary & Binary Morphism Composition ($h = f \circ g$)
Monotonicity and variance compose like sign multiplication in arithmetic:

$$\begin{array}{|c|c||c|}
\hline
\text{Variance}(f) & \text{Variance}(g) & \text{Variance}(f \circ g) \\
\hline
\text{MONO\_STRICT\_INC} & \text{MONO\_STRICT\_INC} & \text{MONO\_STRICT\_INC} \\
\text{MONO\_STRICT\_INC} & \text{MONO\_STRICT\_DEC} & \text{MONO\_STRICT\_DEC} \\
\text{MONO\_STRICT\_DEC} & \text{MONO\_STRICT\_DEC} & \text{MONO\_STRICT\_INC} \\
\text{MONO\_WEAK\_INC} & \text{MONO\_STRICT\_INC} & \text{MONO\_WEAK\_INC} \\
\text{NON\_MONOTONIC} & \text{Any} & \text{NON\_MONOTONIC} \\
\hline
\end{array}$$

#### Rule 3: Product Monoid Construction (Solving `argMin` / `argMax` / Top-K)
A common pitfall is treating `argMin` as an un-optimizable ad-hoc operation. If `argMin` discards the comparison value, it loses associativity.

**The Product Monoid Solution**:
We model `argMin` as a **Lexicographical Product Monoid** over the carrier $\mathcal{C} = \mathcal{W} \times \mathcal{V}$ (where $\mathcal{W}$ is the comparison weight and $\mathcal{V}$ is the entity node ID):

$$(w_1, v_1) \oplus_{\text{argMin}} (w_2, v_2) = \begin{cases} (w_1, v_1) & \text{if } w_1 < w_2 \lor (w_1 = w_2 \land v_1 \le v_2) \\ (w_2, v_2) & \text{otherwise} \end{cases}$$

* **Associativity**: Guaranteed by the strict total order on $\mathcal{W} \times \mathcal{V}$.
* **Identity ($\varepsilon$)**: $(\infty, \text{UINT32\_MAX})$.
* **Idempotence**: $(w, v) \oplus_{\text{argMin}} (w, v) = (w, v)$ (Join-Semilattice!).
* **Commutativity**: Enforced deterministically via the tie-breaking node ID $v_1 \le v_2$.

* **Compiler Impact**: `argMin` is classified as a **Commutative Idempotent Monoid** (Join-Semilattice). It immediately inherits:
  1. Full OpenMP multi-threaded parallel reduction.
  2. SIMD vector reduction using `_mm512_min_ps` on packed $(w, v)$ pairs.
  3. Safe execution over cyclic graphs without deduplication bitsets!

---

### 9.2 The Universal Algebraic Equational Rewrite Calculus

Once AST nodes are annotated with their algebraic signature $\Sigma$, the optimizer applies a **closed, sound set of universal equational theorems**. No manual "whack-a-mole" case analysis is required.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                     Universal Equational Rewrite Calculus Table                        │
├────────────────────┬──────────────────────────────────────┬────────────────────────────┤
│ Axiom Present in Σ │ Formal Mathematical Theorem          │ Compiler Engine Action     │
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Associativity**   │ $(a \oplus b) \oplus c = a \oplus (b \oplus c)$ │ **Tree Rebalancing**:      │
│                    │                                      │ Split linear reductions    │
│                    │                                      │ into $O(\log N)$ parallel  │
│                    │                                      │ SIMD vector tree folds.    │
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Identity (ε)**   │ $x \oplus \varepsilon = x$           │ **Neutral Cancellation**:  │
│                    │ $\text{fold}(\emptyset) = \varepsilon$│ Eliminate empty scans;     │
│                    │                                      │ replace $x + 0 \to x$.     │
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Commutativity**  │ $a \oplus b = b \oplus a$            │ **Unordered Scatter**:     │
│                    │                                      │ Permit out-of-order SIMD   │
│                    │                                      │ accumulation; skip sorting.│
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Idempotence**    │ $x \oplus x = x$                     │ **Deduplication Bypass**:  │
│                    │                                      │ Skip bitset tracking &     │
│                    │                                      │ `DISTINCT` across cycles.  │
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Absorbing (⊤)**  │ $x \oplus \top = \top$               │ **Loop Annihilation**:     │
│                    │ $x \otimes \mathbf{0} = \mathbf{0}$  │ Short-circuit immediately  │
│                    │                                      │ on encountering $\top$.    │
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Distributivity** │ $a \otimes (b \oplus c) = (a \otimes b) \oplus (a \otimes c)$ │ **Filter & Map Pushdown**: │
│                    │                                      │ Push transforms *inside*   │
│                    │                                      │ CSR loops before folds.    │
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Lattice**        │ $a \sqcup (a \sqcap b) = a$          │ **Absorption Simplification│
│ **Absorption**     │ $a \sqcap (a \sqcup b) = a$          │ Collapse redundant nested  │
│                    │                                      │ filter expressions.        │
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Strict**         │ $f(\sup(S)) = \sup(f(S))$            │ **Homomorphism Pushdown**: │
│ **Monotonicity**   │ $g(\sup(S)) = \inf(g(S))$ (Dec)      │ Execute $f$ ONCE on the    │
│                    │                                      │ scalar reduced result.     │
├────────────────────┼──────────────────────────────────────┼────────────────────────────┤
│ **Galois**         │ $f(x) \sqsubseteq y \iff x \sqsubseteq g(y)$│ **Adjunction Migration**:  │
│ **Connection**     │                                      │ Migrate predicates across  │
│                    │                                      │ relational boundaries.     │
└────────────────────┴──────────────────────────────────────┴────────────────────────────┘
```

---

### 9.3 Unified Optimization Architecture Pipeline

```
---

### 9.4 Virtual Super-Relation Coproduct Decomposition & Heterogeneous Physical Path Planning

In `.imps` snapshots (Section 3.3.2), **Virtual Super-Relations** (`IMP_REL_FEATURE_VIRTUAL`) define logical relations as the union (coproduct) of up to 65,536 constituent physical relations:

$$\mathrm{VR} = \coproduct_{i=1}^k R_i = R_1 \oplus R_2 \oplus \dots \oplus R_k$$

```
              Virtual Relation Coproduct Decomposition Pipeline
              
                          Virtual Super-Relation VR
                         (VR = R1 + R2 + R3 + R4)
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
           Constituent R1      Constituent R2      Constituent R3
         (Forward CSR Dense)  (Low In-Degree CSC)  (Functional M:1)
                 │                   │                   │
                 ▼                   ▼                   ▼
           OP_CSR_WALK          OP_CSC_WALK       OP_LOAD_FLAT_EDGE
                 │                   │                   │
                 └───────────────────┬───────────────────┘
                                     ▼
                      Monoidal Semilattice Join (⨁)
                               (OP_SET_UNION)
```

#### 9.4.1 The Coproduct Functorial Distributive Law
A graph traversal over a virtual super-relation $\mathrm{VR}$ is a functor that distributes over coproducts in the category of schemas $\mathbf{C}_{\text{Schema}}$:

$$\mathcal{T}_{\mathrm{VR}}(S) = \mathcal{T}_{\bigoplus_{i=1}^k R_i}(S) \equiv \bigoplus_{i=1}^k \mathcal{T}_{R_i}(S)$$

Because the reduction operator $\bigoplus$ is an **Associative, Commutative Semilattice** (such as boolean reachability bitset OR $\lor$, set union $\cup$, or weighted semiring sum $+$), **the execution of each constituent physical relation $R_i$ is completely decoupled and independently optimizable**.

#### 9.4.2 Heterogeneous Physical Path Planning per Constituent

A naive query compiler would execute a uniform forward multi-CSR walk (`OP_CSR_WALK_MULTI([R1, R2, R3, R4])`). Impulse's algebraic AST optimizer analyzes the physical metadata of each constituent $R_i$ to plan a **heterogeneous execution plan**:

1. **Constituent Inversion via CSC Transpose**:
   - If physical relation $R_2$ possesses a pre-materialized CSC transpose index (`IMP_REL_FEATURE_CSC`) and exhibits degree asymmetry ($\text{AvgInDegree}(R_2) \ll \text{AvgOutDegree}(R_2)$):
   - **Optimization**: The compiler emits `OP_CSC_WALK(R2)` for $R_2$, while keeping forward CSR for $R_1$.
2. **Multiplicity Specialization ($M:1$ Flat Array Fast-Path)**:
   - If constituent $R_3$ is Many-to-One (`IMP_REL_CARDINALITY_M_1`), it has no CSR row offset array.
   - **Optimization**: The compiler emits `OP_LOAD_FLAT_EDGE(R3)`, reading the target node in a single $O(1)$ flat array dereference.
3. **Zone Map & Attribute Predicate Elimination**:
   - If the query filters edges via predicate $P(e)$ (e.g. `WHERE rel.weight > 100`), and constituent $R_4$ has `weight.MaxVal = 50`:
   - **Optimization**: The entire constituent sub-branch is pruned at compile-time ($\mathcal{T}_{R_4}(S) \to \emptyset$), emitting **zero bytecode instructions** for $R_4$.
4. **Fused Multi-Matrix CSR Batching**:
   - The remaining homogeneous CSR components ($R_1$) are batched together via `OP_CSR_WALK_MULTI([R1])`.

#### 9.4.3 Concrete Assembly Emission Comparison

Given a query:
```cypher
MATCH (u:User {id: 42})-[:MEMBER_OF_ANY]->(g:Group)
RETURN g.id
```
Where `MEMBER_OF_ANY` is a virtual relation $\mathrm{VR} = R_{\text{DirectMember}} + R_{\text{AssignedRole}} + R_{\text{InheritedOrg}}$:
* $R_{\text{DirectMember}}$: Multiplicity $M:1$ (Functional).
* $R_{\text{AssignedRole}}$: Dense Many-to-Many with CSC Transpose available.
* $R_{\text{InheritedOrg}}$: Standard CSR.

```nasm
; --- Heterogeneous Physical Assembly Generated for Virtual Relation ---
.text
_traverse_vr:
    ; Path 1: Fast O(1) flat array dereference for M:1 constituent
    OP_LOAD_FLAT_EDGE     R1, REL_DIRECT_MEMBER, 42
    OP_BITSET_SET         REG_ACCUMULATOR, R1

    ; Path 2: CSC Transpose Walk for inverted low-degree constituent
    OP_CSC_WALK           R2, REL_ASSIGNED_ROLE, 42
    OP_BITSET_UNION       REG_ACCUMULATOR, R2

    ; Path 3: Forward CSR vector walk for standard CSR constituent
    OP_CSR_WALK           R3, REL_INHERITED_ORG, 42
    OP_BITSET_UNION       REG_ACCUMULATOR, R3

    OP_RET                REG_ACCUMULATOR
```

#### 9.4.4 Partition Elimination for Free via Virtual Relations & Invariant Folding

A natural consequence of combining Virtual Super-Relations with Snapshot Zone Maps is **Zero-Cost Static Partition Elimination**.

```
                           Zero-Cost Static Partition Elimination
                           
             Query: (s:Store)-[:IN_SECTION {section: 'FRUIT'}]->(p:Product)
                                            │
                                            ▼
                    Logical Virtual Super-Relation: IN_SECTION
                     (VR = SEC_FRUIT + SEC_BREAD + SEC_DAIRY)
                                            │
                ┌───────────────────────────┼───────────────────────────┐
                ▼                           ▼                           ▼
        Constituent: SEC_FRUIT      Constituent: SEC_BREAD      Constituent: SEC_DAIRY
        Zone Map: section='FRUIT'   Zone Map: section='BREAD'   Zone Map: section='DAIRY'
        Eval: 'FRUIT'=='FRUIT'      Eval: 'BREAD'=='FRUIT'      Eval: 'DAIRY'=='FRUIT'
        Result: TRUE                Result: FALSE               Result: FALSE
                │                           │                           │
                ▼                           ▼                           ▼
        [EMIT OP_CSR_WALK]          [PRUNED AT COMPILE-TIME]    [PRUNED AT COMPILE-TIME]
        (Filter stripped from loop!)    (Zero Bytecode)             (Zero Bytecode)
```

##### 1. Physical Snapshot Construction
When building a `.imps` snapshot, high-cardinality heterogeneous edges (e.g. inventory items, financial transactions, event logs) can be physically partitioned into dedicated constituent physical relations:
* Physical Relation `SEC_FRUIT` ($R_1$): Contains exclusively fruit edges.
  - `section` attribute zone map: $\text{MinVal} = \text{"FRUIT"}$, $\text{MaxVal} = \text{"FRUIT"}$, $\text{DistinctCount} = 1$.
* Physical Relation `SEC_BREAD` ($R_2$): Contains exclusively bread edges.
  - `section` attribute zone map: $\text{MinVal} = \text{"BREAD"}$, $\text{MaxVal} = \text{"BREAD"}$, $\text{DistinctCount} = 1$.
* Physical Relation `SEC_DAIRY` ($R_3$): Contains exclusively dairy edges.
  - `section` attribute zone map: $\text{MinVal} = \text{"DAIRY"}$, $\text{MaxVal} = \text{"DAIRY"}$, $\text{DistinctCount} = 1$.
* Logical Virtual Relation `IN_SECTION`: Registered in Section 2 Header with `IMP_REL_FEATURE_VIRTUAL` over $[R_1, R_2, R_3]$.

##### 2. The Compile-Time Double-Optimization Leap
When a user executes `WHERE e.section IN ['FRUIT']` or `e.section == 'FRUIT'`:

1. **Static Partition Pruning**:
   The compiler evaluates the predicate against each constituent's zone map:
   - For $R_2$ (`SEC_BREAD`): $\text{"BREAD"} \in [\text{"FRUIT"}] = \mathbf{False} \implies \mathcal{T}_{R_2}(S) \to \emptyset$.
   - For $R_3$ (`SEC_DAIRY`): $\text{"DAIRY"} \in [\text{"FRUIT"}] = \mathbf{False} \implies \mathcal{T}_{R_3}(S) \to \emptyset$.
   - **Result**: $R_2$ and $R_3$ are discarded at compile time. No memory is mapped, no offsets are read, and zero VM bytecode is emitted.
2. **Inner-Loop Filter Stripping (Invariant Folding)**:
   Inside the surviving constituent $R_1$ (`SEC_FRUIT`):
   - The compiler knows that by construction, $100\%$ of edges satisfy `e.section == 'FRUIT'`.
   - The edge predicate `e.section == 'FRUIT'` folds to constant $\mathbf{True}$.
   - **Result**: The attribute filter is **completely stripped from the inner CSR traversal loop**!
   - The runtime executes a raw, unmasked, branchless `OP_CSR_WALK(REL_SEC_FRUIT)` with **zero edge attribute lookups, zero string comparisons, and zero cache lines wasted on loading the `section` column**.

##### 3. Temporal Range Partitioning
The identical mechanism provides automatic range partition pruning for time-series graph queries:
* Partitions: `TX_2026_Q1` ($[\text{Jan}, \text{Mar}]$), `TX_2026_Q2` ($[\text{Apr}, \text{Jun}]$).
* Query: `WHERE tx.timestamp >= 2026-04-15`.
* Compilation: `Q1`'s zone map $[\text{Jan}, \text{Mar}] \cap [\text{Apr}, \infty) = \emptyset$ prunes `Q1` instantly. The query compiles to a single scan over `TX_2026_Q2`.

---

#### 9.4.5 Dynamic Partition Elimination for Parameterized Queries (`WHERE section == @p1`)

When a query is parameterized (e.g. `WHERE e.section == @p1` or `WHERE tx.timestamp >= @min_time`), the parameter value `@p1` is not known at static AST compile time.

Instead of degrading to an un-optimized full scan across all physical partitions, Impulse utilizes **three zero-overhead dynamic dispatch strategies**:

```
                       Dynamic Partition Elimination Strategies
                       
             Parameterized Query: WHERE e.section == @p1
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
       Categorical Parameter (@p1)       Continuous Range Parameter (@p1)
       ┌───────────────────────────┐     ┌───────────────────────────────┐
       │ Strategy 1: O(1) String   │     │ Strategy 2: Scalar Zone-Map   │
       │ Dictionary Jump Table     │     │ Guard Preambles (CMP + JMP)   │
       └─────────────┬─────────────┘     └───────────────┬───────────────┘
                     │                                   │
                     ▼                                   ▼
          Direct Jump to Specialized         Scalar register compare skips
          Partition Bytecode Block           entire multi-megabyte CSR walk
```

##### Strategy 1: $O(1)$ Dictionary Jump Table (Categorical Partition Dispatch)
When partitioning is discrete (e.g. `section ∈ {'FRUIT', 'BREAD', 'DAIRY'}`):
1. The compiler generates an **$O(1)$ Jump Table / Switch Dispatch Block** indexed by the parameter's 32-bit String Pool Offset / Hash:
   $$\text{JumpTarget} = \mathrm{Table}[\mathrm{Hash}(@p1)]$$
2. The VM executes a single scalar lookup, jumping directly to the pre-compiled, **filter-stripped bytecode block** for that specific partition!
3. If `@p1` is not present in the snapshot dictionary, it jumps immediately to `_empty_exit` without touching any graph relations.

```nasm
; --- Dynamic Categorical Partition Jump Table (ImpAsm) ---
.text
_dynamic_partition_dispatch:
    ; R_PARAM: Holds incoming @p1 string ID
    OP_SWITCH_HASH        R_PARAM, _dispatch_table, _empty_exit

_dispatch_table:
    .entry HASH_FRUIT,  _walk_sec_fruit
    .entry HASH_BREAD,  _walk_sec_bread
    .entry HASH_DAIRY,  _walk_sec_dairy

_walk_sec_fruit:
    ; Filter stripped! Raw unmasked vector walk
    OP_CSR_WALK           REG_OUT, REL_SEC_FRUIT, R_SRC_NODE
    OP_RET                REG_OUT

_walk_sec_bread:
    OP_CSR_WALK           REG_OUT, REL_SEC_BREAD, R_SRC_NODE
    OP_RET                REG_OUT

_walk_sec_dairy:
    OP_CSR_WALK           REG_OUT, REL_SEC_DAIRY, R_SRC_NODE
    OP_RET                REG_OUT

_empty_exit:
    OP_RET_EMPTY
```

##### Strategy 2: Zone Map Guard Preambles (Continuous Range Parameters)
For range predicates like `WHERE tx.timestamp >= @min_time`:
1. The compiler wraps each constituent physical relation walk in a **1-cycle scalar register guard check** using the partition's static Zone Map $[L_i, U_i]$:
   - **Complete Exclusion ($@\text{min\_time} > U_i$)**: Skips partition traversal entirely (`JMP _next_partition`).
   - **Complete Inclusion ($@\text{min\_time} \le L_i$)**: Executes **raw unmasked** `OP_CSR_WALK` (filter stripped!).
   - **Partial Overlap ($L_i < @\text{min\_time} \le U_i$)**: Executes filtered vector walk `OP_CSR_WALK_FILTERED`.

```nasm
; --- Dynamic Range Guard Preamble (ImpAsm) ---
.text
_traverse_range_partitions:
    ; --- Partition 1: TX_2026_Q1 (Zone Map: [Jan 1, Mar 31] = [1704067200, 1711929600]) ---
    CMP_GT_IMM            R_MIN_TIME, 1711929600, _skip_q1   ; If @min_time > Mar 31, skip Q1 completely!
    CMP_LE_IMM            R_MIN_TIME, 1704067200, _run_q1_raw; If @min_time <= Jan 1, 100% match!
    OP_CSR_WALK_GE_I64    R_ACC, REL_TX_Q1, R_SRC, ATTR_TIME, R_MIN_TIME
    JMP                   _skip_q1
_run_q1_raw:
    OP_CSR_WALK           R_ACC, REL_TX_Q1, R_SRC            ; Filter stripped!
_skip_q1:

    ; --- Partition 2: TX_2026_Q2 (Zone Map: [Apr 1, Jun 30] = [1711929600, 1719792000]) ---
    CMP_GT_IMM            R_MIN_TIME, 1719792000, _skip_q2   ; If @min_time > Jun 30, skip Q2 completely!
    CMP_LE_IMM            R_MIN_TIME, 1711929600, _run_q2_raw; If @min_time <= Apr 1, 100% match!
    OP_CSR_WALK_GE_I64    R_ACC, REL_TX_Q2, R_SRC, ATTR_TIME, R_MIN_TIME
    JMP                   _skip_q2
_run_q2_raw:
    OP_CSR_WALK           R_ACC, REL_TX_Q2, R_SRC            ; Filter stripped!
_skip_q2:

    OP_RET                R_ACC
```

##### Strategy 3: JIT Parameter Template Specialization (Hot-Path Caching)
For high-frequency OLTP/ReBAC queries, `ImpulseVM` caches specialized bytecode instances keyed by $(Q_{\text{hash}}, \text{Partition}(\vec{p}))$. 
* The first execution with `@p1 = "FRUIT"` dynamically instantiates the static template.
* Subsequent invocations with `@p1 = "FRUIT"` execute the **zero-branch, direct single-partition path** with zero dispatch overhead ($< 10\text{ ns}$ execution latency).

---

#### 9.4.6 Advanced Parameter-Driven Optimizations: Annihilators, Adaptive CSR/CSC Swaps & Kernel Dispatch

When query parameters are evaluated at runtime, the combination of parameter values and snapshot topology unlocks four categories of dynamic algebraic rewrites:

```
                  Advanced Dynamic Parameter Optimizations
                  
  ┌─────────────────────────┬─────────────────────────┬─────────────────────────┐
  │ 1. Value Short-Circuits │ 2. Adaptive CSR/CSC     │ 3. Kernel Dispatch      │
  │    (Absorbing Elements) │    Direction Inversion  │    (Scale Specialization│
  ├─────────────────────────┼─────────────────────────┼─────────────────────────┤
  │ • @is_admin == true     │ • Compare |src| × Deg   │ • |ids| == 1 ⟹ Scalar   │
  │   ⟹ Skip Traversal     │   vs |dst| × InDeg      │ • |ids| ≤ 64 ⟹ AVX-512  │
  │ • @scale == 0 ⟹ Ret 0   │ • Super-Node Inversion  │ • |ids| > 64 ⟹ OpenMP   │
  │ • @limit == 1 ⟹ 1st BFS│   (500,000x Speedup)    │ • @k ≤ 32 ⟹ Reg Top-K  │
  └─────────────────────────┴─────────────────────────┴─────────────────────────┘
```

##### 1. Parameter Value-Specific Algebraic Short-Circuits (Absorbing Annihilators)
* **Boolean & Security Lattice Annihilation**:
  For an authorization check: `WHERE @is_admin || (user.id IN doc.explicit_readers)`:
  - At runtime, if `@is_admin == true`, the Boolean absorbing law ($\mathbf{True} \lor X \equiv \mathbf{True}$) triggers in **1 CPU cycle**.
  - The entire graph reachability traversal over `explicit_readers` is **completely bypassed** (0 cache misses, 0 memory reads).
* **Semiring Multiplicative Zero ($\mathbf{0}$ Annihilator)**:
  In GraphBLAS / GNN expressions like $\alpha \cdot (\mathbf{A} \cdot \mathbf{x})$:
  - If parameter `@alpha == 0.0`, the property $0 \cdot \mathbf{v} = \mathbf{0}$ immediately returns a zero vector without executing matrix-vector multiplications.
* **Extreme Boundary Zone-Map Collapse**:
  For predicate `WHERE node.score >= @min_score`:
  - If `@min_score > Domain.MaxVal("score")`: Return $\emptyset$ instantaneously.
  - If `@min_score <= Domain.MinVal("score")`: 100% of nodes match; strip the filter and emit a direct bulk vector memory copy!

##### 2. Adaptive CSR vs. CSC Traversal Inversion (Super-Node Inversion)
Consider a bidirectional path query parameterized on source and destination sets:
```cypher
MATCH (src)-[:FOLLOWS]->(dst)
WHERE src.id IN @src_list AND dst.id IN @dst_list
RETURN dst.id
```

At query execution time, the VM performs an **Adaptive Degree-Weighted Cost Comparison** in 2 CPU cycles:

$$\text{Forward Cost} = |\text{src\_list}| \times \text{AvgOutDegree}(\text{FOLLOWS})$$
$$\text{Reverse Cost} = |\text{dst\_list}| \times \text{AvgInDegree}(\text{FOLLOWS})$$

* **If $\text{Reverse Cost} < \text{Forward Cost}$**: The VM dynamically inverts the traversal, executing `OP_CSC_WALK` starting from `dst_list` backward to `src_list`.

```
                  The Super-Node Traversal Inversion
                  
   Scenario: Path check between Influencer (@src, OutDeg=1,000,000) and Normal User (@dst, InDeg=2)
   
   Forward CSR Walk (Naive):
     @src (1M edges) ──[Scan 1,000,000 edges]──► Massive Frontier ──► Intersect with @dst
     Cost: 1,000,000 edge lookups + large bitset allocation.
     
   Reverse CSC Transpose Walk (Inverted):
     @dst (2 edges) ──[Scan 2 incoming edges]──► Tiny Frontier {u1, u2} ──► Match @src
     Cost: EXACTLY 2 edge lookups!
     
   Speedup Factor: 500,000x faster, zero allocation!
```

##### 3. Dynamic Kernel & Register Top-K Specialization
Based on numeric parameter magnitudes, the execution engine dynamically routes to specialized hardware kernels:

| Parameter Pattern | Dynamic Condition | Hardware Kernel Selected | Latency / Memory Impact |
| :--- | :--- | :--- | :--- |
| **Point Query** | `|@ids| == 1` | `OP_CSR_WALK_SCALAR` (single pointer jump) | $< 5\text{ ns}$ |
| **Small Vector Batch** | `2 <= |@ids| <= 64` | `OP_CSR_WALK_AVX512` (unrolled SIMD gather) | $3\times$ cache throughput |
| **Massive Parallel Batch** | `|@ids| > 64` | `OP_CSR_WALK_OPENMP` (multi-core thread pool) | Linear CPU scaling |
| **Micro Top-K** | `@limit <= 32` | `OP_TOPK_REG32` (kept in 32 ZMM registers) | Zero scratch memory allocation |
| **First-Hit Short-Circuit** | `@limit == 1` | `OP_BFS_FIRST_HIT` (exits immediately on match) | Traversal terminates in $< 1\text{ hop}$ |

---

### 9.5 Unified Optimization Architecture Pipeline

## 10. C-ABI Structural Definitions for Compiler Integration

To implement this optimization engine in `impulse-graph-compile` and `impulse-graph-core`, the following C-ABI structures define the compiler interface:

```c
#ifndef IMPULSE_CEL_AST_OPTIMIZE_H
#define IMPULSE_CEL_AST_OPTIMIZE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Monotonicity / Variance enum
typedef enum ImpulseMonotonicity {
    IMP_MONO_NONE       = 0x00,
    IMP_MONO_STRICT_INC = 0x01, // Strictly increasing: x < y => f(x) < f(y)
    IMP_MONO_WEAK_INC   = 0x02, // Non-decreasing: x <= y => f(x) <= f(y)
    IMP_MONO_STRICT_DEC = 0x03, // Strictly decreasing: x < y => f(x) > f(y)
    IMP_MONO_WEAK_DEC   = 0x04, // Non-increasing: x <= y => f(x) >= f(y)
    IMP_MONO_CONSTANT   = 0x05
} ImpulseMonotonicity;

// Homomorphism Commutativity Flags
typedef enum ImpulseHomomorphismFlags {
    IMP_HOMO_NONE               = 0x0000,
    IMP_HOMO_COMMUTES_WITH_MAX  = 0x0001, // f(max(S)) == max(f(S))
    IMP_HOMO_COMMUTES_WITH_MIN  = 0x0002, // f(min(S)) == min(f(S))
    IMP_HOMO_COMMUTES_WITH_SUM  = 0x0004, // f(sum(S)) == sum(f(S)) [Linear]
    IMP_HOMO_DISTRIBUTES_OR     = 0x0008, // f(a || b) == f(a) || f(b)
    IMP_HOMO_DISTRIBUTES_AND    = 0x0010  // f(a && b) == f(a) && f(b)
} ImpulseHomomorphismFlags;

// Algebraic Morphism Classification
typedef enum ImpulseMorphismClass {
    IMP_MORPHISM_GENERAL    = 0x00,
    IMP_MORPHISM_FUNCTIONAL = 0x01, // Many-to-One (Out-Degree <= 1)
    IMP_MORPHISM_INJECTIVE  = 0x02, // One-to-Many (In-Degree <= 1)
    IMP_MORPHISM_BIJECTIVE  = 0x03  // One-to-One  (In-Degree <= 1 && Out-Degree <= 1)
} ImpulseMorphismClass;

// Algebraic Axiomatic Flags
typedef enum ImpulseAlgebraicClass {
    IMP_ALG_NONE         = 0x00,
    IMP_ALG_SEMIGROUP    = 0x01, // Associative: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
    IMP_ALG_MONOID       = 0x02, // Associative + Neutral Identity (ε)
    IMP_ALG_COMMUTATIVE  = 0x04, // Commutative: a ⊕ b = b ⊕ a
    IMP_ALG_IDEMPOTENT   = 0x08, // Idempotent (Semilattice): x ⊕ x = x
    IMP_ALG_DISTRIBUTIVE = 0x10, // Distributive: a ⊗ (b ⊕ c) = (a ⊗ b) ⊕ (a ⊗ c)
    IMP_ALG_ABSORBING    = 0x20, // Has Absorbing Annihilator (⊤ ⊕ x = ⊤)
    IMP_ALG_INVERTIBLE   = 0x40  // Group: Has Inverse Element (-x)
} ImpulseAlgebraicClass;

// Scalar Value Interval
typedef struct ImpulseIntervalBound {
    int64_t  min_int;
    int64_t  max_int;
    double   min_double;
    double   max_double;
    bool     is_valid;
} ImpulseIntervalBound;

// AST Node Property Annotation Record
typedef struct ImpulseAstAnnotation {
    ImpulseIntervalBound    interval;
    ImpulseMorphismClass    morphism;
    uint32_t                algebra_flags;      // Bitmask of ImpulseAlgebraicClass
    ImpulseMonotonicity     monotonicity;
    uint32_t                homomorphism_flags; // Bitmask of ImpulseHomomorphismFlags
    uint32_t                cardinality_upper;  // Upper bound on intermediate elements
    bool                    is_pure;            // True if free of side-effects
    bool                    is_constant_known;
    bool                    constant_bool_val;
    uint64_t                constant_raw_val;
} ImpulseAstAnnotation;

// Core Compiler API: Annotate and Optimize AST bound to Snapshot
int impulse_ast_bind_snapshot(
    void*                   ast_root,
    const void*             snapshot_handle,
    ImpulseAstAnnotation*   out_annotation_tree
);

int impulse_ast_optimize_and_emit_impas(
    const void*             ast_root,
    const ImpulseAstAnnotation* annotations,
    char*                   out_impas_buffer,
    size_t                  buffer_capacity,
    size_t*                 out_impas_length
);

#ifdef __cplusplus
}
#endif

#endif // IMPULSE_CEL_AST_OPTIMIZE_H
```

---

## 11. Summary Matrix: Metadata $\to$ AST Label $\to$ Optimization Rule

| Snapshot Metadata | AST Property Label | Compiler Optimization Rule | Performance / Memory Gain |
| :--- | :--- | :--- | :--- |
| `Attr.MinVal`, `Attr.MaxVal` | `IntervalBound[L, U]` | **Zone Map Pruning**: Eliminate unreachable branches if $[L, U] \cap \text{Pred} = \emptyset$. | $100\%$ CPU elimination (prunes traversal branches). |
| `Attr.NullCount == 0` | `NonNullable` | **Null-Check Elimination**: Strip null bitmaps and ternary null branch logic. | Unmasked AVX-512 vectorization ($2\times - 4\times$ speedup). |
| `Attr.DistinctCount` | `ExactCardinality` | **$O(1)$ Distinct Count**: Read precomputed distinct count from Section 2 Header. | Zero memory scan ($< 1\text{ ns}$). |
| `Attr.Monotonicity == ASC` | `MonotonicAsc` | **Binary Search Slicing**: Replace linear SIMD scans with $O(\log N)$ range slices. | $O(N) \to O(\log N)$ latency ($100\times - 1,000\times$ faster). |
| `Func.Variance == STRICT_INC` | `COMMUTES_WITH_MAX` | **Monotonic Homomorphism Pushdown**: $\max(f(X)) \to f(\max(X))$. | $N$ transcendental math calls $\to 1$ scalar call (or $O(1)$ from Zone Map). |
| `Func.Variance == STRICT_DEC` | `COMMUTES_WITH_MIN` | **Monotonic Inverse Pushdown**: $\max(g(X)) \to g(\min(X))$. | $N$ math calls $\to 1$ scalar call over raw column min. |
| `Rel.Multiplicity == 1:M` | `Injective` | **Deduplication Bypass**: Skip `DISTINCT` and scratch bitset allocation. | Zero-allocation, eliminates $O(|V|)$ memory overhead. |
| `Rel.Multiplicity == M:1` | `Functional` | **Flat Array Dereference**: Dereference target node in $O(1)$ without CSR row offset scan. | $3\times$ faster single-hop traversal. |
| `Rel.SectionFeatures.DAG` | `Acyclic` | **Cycle-Check Bypass**: Omit visited-bitset maintenance in variable-length paths. | $50\%$ reduction in traversal memory traffic. |
| `Aggregator == MAX/MIN/OR` | `JoinSemilattice` | **Aggregator Pushdown**: Fold accumulator directly inside CSR loop without materializing target vector. | Zero heap/vector allocation; $O(1)$ memory footprint. |
| `Aggregator == argMin/argMax` | `LexicographicalMonoid` | **Product Monoid SIMD Reduction**: Vectorize $(w, v)$ pairs with `_mm512_min_ps` without deduplication. | Multi-threaded lock-free Top-1/Top-K reduction. |
| `Rel.Feature == VIRTUAL` | `CoproductDecomposition` | **Heterogeneous Physical Path Planning**: Decompose $\mathrm{VR} = \coproduct R_i$ into optimal constituent ops (`CSC(R2) + CSR(R1)`). | Maximizes index usage and minimizes degree fan-out across constituent sub-relations. |
| `Rel.IsEndomorphism == true` | `MatrixPowering` | **Binary Exponentiation**: Compute $R^k$ in $O(\log k)$ matrix multiplications. | Exponential speedup on deep fixed-hop traversals. |
| `Catamorphism Tuple` | `BananaSplitFusion` | **Multi-Aggregate Fusion**: Combine `COUNT`, `SUM`, `MAX`, `MIN` into single SIMD pass. | Single pass over data; 4x fewer vector loads. |

---

## 12. Implementation Roadmap & Architecture Milestones

1. **Milestone 1: Snapshot Header & Descriptor Updates (`impulse-graph-spec`)**:
   - Expand `AttributeDescriptor` to 64 bytes with `MinVal`, `MaxVal`, `NullCount`, `DistinctCount`, and `Monotonicity`.
   - Update C-ABI validation test vectors (`tc01`..`tc36`).
2. **Milestone 2: Universal Algebraic Type Inference Pipeline (`impulse-graph-compile`)**:
   - Implement bottom-up type & algebraic inference pass over CEL and Cypher ASTs.
   - Construct Product Monoids for complex reducers (`argMin`, `Top-K`).
   - Annotate AST nodes with `ImpulseAstAnnotation` structs upon snapshot binding.
3. **Milestone 3: Universal Equational Rewrite Engine (`impulse-graph-compile`)**:
   - Pass 1: Identity & Absorbing Element Elimination ($x \oplus \varepsilon \to x$, $x \otimes \mathbf{0} \to \mathbf{0}$).
   - Pass 2: Monotonic Homomorphism Pushdown ($\max(f(X)) \to f(\max(X))$).
   - Pass 3: Injective Path & Semilattice Deduplication Elimination.
   - Pass 4: Semilattice & Ideal Filter Pushdown (Distance bounding & branch pruning).
   - Pass 5: Banana-Split Catamorphism Multi-Aggregator Fusion.
   - Pass 6: CSR/CSC Traversal Inversion & Binary Exponentiation.
4. **Milestone 4: Code Emission to `ImpScheme` & `ImpAsm` (`impulse-graph-tooling`)**:
   - Emit optimized register assembly `.impas` executing on `ImpulseVM`.
   - Validate zero-allocation execution via benchmark test harnesses.


