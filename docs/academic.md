# Mathematical, Categorical & GraphBLAS Foundations

This page formalizes the mathematical foundation of the **Impulse Graph Engine** query and execution model—connecting **Semiring-Weighted Kleisli Algebras**, **Grothendieck Fibrations**, **GraphBLAS Sparse Linear Algebra**, and **Substructural Linear Types** directly to physical `.imps` memory layouts and `ImpulseVM` bytecode optimizations.

For the peer-reviewed computer science papers behind each subsystem, see **[Research Literature, Annotated Bibliography & Design Lineage](academic/literature-and-influences.md)**.

---

## 1. The Unifying Systems & Algebraic Thesis

Traditional relational and property-graph databases optimize under **runtime uncertainty**: because tables and adjacency lists mutate concurrently in place, the query planner relies on sampled cardinality estimates and evaluates multi-hop traversals as **multiset (bag) joins** that dynamically allocate intermediate tuples on the heap.

Impulse Graph rests on the opposite structural premise:

!!! important "Core Algebraic Thesis"
    **An immutable, schema-typed binary graph snapshot (`.imps`) with exact catalog cardinalities ($N_d$), degree bounds, and relational multiplicity invariants ($1:1, 1:N, N:1$) transforms graph query execution from runtime bag-join heuristics into a statically verifiable Kleisli semiring algebra—eliminating dynamic heap allocation, intermediate path explosion, and redundant synchronization.**

---

## 2. Semiring-Weighted Set Monad ($\mathcal{W}_R$) vs. Multiset Bag Monad ($\mathcal{M}$)

### 2.1 Why Bag-Based Path Engines Explode
Relational SQL joins, standard Cypher, and Gremlin evaluate traversals in the **Multiset (Bag) Monad** $\mathcal{M}(X) = X \to \mathbb{N}$, whose monadic flatten $\mu_{\mathcal{M}}$ preserves duplicate path multiplicities:

$$\mu_{\mathcal{M}}(F)(x) = \sum_{f \in \mathcal{M}(X)} F(f) \cdot f(x)$$

If a destination node $d$ is reachable via $k$ distinct paths of length $m$, a bag-based engine materializes $k$ intermediate path tuples. On scale-free graphs with average hub out-degree $\hat{d}$, intermediate state grows as $O(\hat{d}^m)$ ("path explosion"), requiring resizing hash tables (`DISTINCT`) and per-hop heap allocations.

### 2.2 The Semiring-Weighted Distribution Monad
Impulse Graph evaluates traversals in the **Semiring-Weighted Set Monad** $\mathcal{W}_R(X) = X \to R$ over a semiring $(R, \oplus, \otimes, \mathbf{0}, \mathbf{1})$:

* **Unit ($\eta$)**: Embeds a seed node $x \in \mathcal{V}_D$ as a Dirac basis indicator vector $\eta(x)(y) = \mathbf{1}$ if $y = x$, else $\mathbf{0}$.
* **Monadic Flatten ($\mu$)**: Collapses nested weighted frontiers at every hop using semiring addition ($\oplus$) and multiplication ($\otimes$):

$$\mu(F)(y) = \bigoplus_{f \in \mathcal{W}_R(X)} F(f) \otimes f(y)$$

```text
 Traditional Bag Engines (SQL / Cypher)             Impulse Graph Engine (.imps)
 ──────────────────────────────────────             ────────────────────────────
 • Multiset (Bag) Monad: M(X) = X → ℕ               • Semiring-Weighted Set: W_R(X) = X → R
 • Frontier cardinality: O(d^m) [Path Explosion]    • Frontier Bound: |S| ≤ |V_target| = N_Dst
 • Explicit DISTINCT hash-table deduplication       • Automatic Monoidal Fold (⊕) at every hop
 • Dynamic heap allocations per path tuple          • Pre-allocated off-heap arrays & BitSets
```

### 2.3 The Frontier Bounding Invariant
Because every domain $D$ in an `.imps` snapshot possesses an independent, contiguous dense integer space $\mathcal{V}_D = \{0, 1, \dots, N_D - 1\}$ and converging paths fold immediately by target dense ID, intermediate frontier cardinality is strictly bounded above by target domain cardinality:

$$\forall \tau: \mathcal{V}_{\text{Src}} \to \mathcal{V}_{\text{Dst}}, \quad |\tau(\mathcal{S}_{\text{Src}})| \le |\mathcal{V}_{\text{Dst}}| = N_{\text{Dst}}$$

Consequently, exponential path explosion is impossible by construction, and the exact scratch and result buffer byte size (`impulse_stmt_buffer_size`) is known statically at `prepare` time before execution begins.

### 2.4 Kleisli Composition $\equiv$ GraphBLAS Matrix Multiplication
In the **Kleisli Category** $\mathbf{Kl}(\mathcal{W}_R)$, objects are typed node domains $\mathcal{V}_A, \mathcal{V}_B$ and morphisms are transition kernels $f: \mathcal{V}_A \to \mathcal{W}_R(\mathcal{V}_B)$. Composing two hops $f: \mathcal{V}_A \to \mathcal{W}_R(\mathcal{V}_B)$ and $g: \mathcal{V}_B \to \mathcal{W}_R(\mathcal{V}_C)$ yields:

$$(g \odot f)(a)(c) = (f(a) \gg= g)(c) = \bigoplus_{b \in \mathcal{V}_B} f(a)(b) \otimes g(b)(c)$$

Kleisli composition $g \odot f$ is algebraically identical to **GraphBLAS sparse matrix-matrix multiplication** ($\mathbf{A}_{R_1} \otimes_R \mathbf{A}_{R_2}$), and monadic bind ($\mathbf{v} \gg= f$) is sparse **vector-matrix multiplication** ($\mathbf{v}^T \otimes_R \mathbf{A}_R$, executed by `OP_VXM` / `OP_MXV`):

| Graph Workload | Frontier State $\mathbf{v}$ | Semiring $(R, \oplus, \otimes, \mathbf{0}, \mathbf{1})$ | Impulse Transition $\phi$ & Monoid $\oplus$ |
| :--- | :--- | :--- | :--- |
| **Boolean Reachability / ReBAC** | `OffHeapBitSet` ($\lceil N_d/64 \rceil$ words) | $(\mathbb{B}, \lor, \land, \text{false}, \text{true})$ | $\phi = \text{true}, \quad \oplus = \lor$ (Bitwise `OR`) |
| **Batched / $N-1$ Multi-Lane ($W \le 64$)** | `TYPE_LANE_FRONTIER` ($N_d \times W$-bit words) | $(\mathbb{B}^W, \lor_W, \land_W, \mathbf{0}_W, \mathbf{1}_W)$ | Word-parallel bitwise `OR` & edge mask `AND` (`0xC0`..`0xC9`) |
| **Shortest Path (BFS / Min-Plus)** | Distance vector (`float32`/`int64`) | $(\mathbb{R}_{\ge 0} \cup \{\infty\}, \min, +, \infty, 0)$ | $\phi = \sigma_s + e.\text{weight}, \quad \oplus = \min$ |
| **Widest Path / Bottleneck Capacity** | Capacity vector (`float64`) | $(\mathbb{R}_{\ge 0} \cup \{\infty\}, \max, \min, 0, \infty)$ | $\phi = \min(\sigma_s, e.\text{cap}), \quad \oplus = \max$ |
| **PageRank / Financial Exposure** | Score vector (`float64`) | $(\mathbb{R}, +, \times, 0, 1)$ | $\phi = \sigma_s \times e.\text{weight}, \quad \oplus = +$ (`SUM`) |
| **Transitive Datalog Closure ($\tau^*$)** | BitSet / state vector | Idempotent Kleene Algebra ($\sigma \oplus \sigma = \sigma$) | Least fixed point $\mu X.\; (\mathcal{S}_0 \oplus \tau(X))$ (`repeatUntilStable`) |

### 2.5 Expressiveness Boundary: Set Algebra vs. ISO GQL Path Modes & Cyclic Joins
Stating exact expressiveness boundaries clarifies how Impulse relates to ISO/IEC 39075 **GQL** and **SQL:2023 (SQL/PGQ)**:

1. **Reachability, Aggregation & Fixed Points (In-Algebra, $O(N_d)$ Space)**: Any query whose observable output depends on target node reachability, aggregated path weights over a semiring, bounded-hop neighborhoods, or monotonic Datalog recursion lowers directly into $\mathbf{Kl}(\mathcal{W}_R)$ with zero dynamic allocation.
2. **Explicit Path-History Enumeration (`TRAIL` / `ACYCLIC` Simple Paths)**: Queries that must enumerate every distinct simple path $p = (v_0, e_1, v_1, \dots, v_k)$ without repeated vertices require per-path history state in $\mathcal{M}(\mathcal{V}^*)$ rather than node-indexed state in $\mathcal{W}_R(\mathcal{V})$. Such path-bag queries cannot be evaluated in fixed $O(N_d)$ frontier memory without truncation or external path materialization.
3. **Cyclic Motif & Triangle Queries (Binary Joins vs. Worst-Case Optimal Joins)**: Sequential binary Kleisli steps evaluate acyclic chains and trees optimally in $O(|\text{active edges}|)$. On cyclic patterns such as triangle listing $A(x, y) \land B(y, z) \land C(x, z)$, pure binary join sequences can incur $O(m^{3/2})$ intermediate work compared to $O(m^{3/2})$-optimal multi-way **Worst-Case Optimal Join (WCOJ)** intersection (Ngo et al., PODS '12). Because `.imps` sorts CSR target slices monotonically per source row, cyclic closures intersect sorted neighbor lists directly via bitset/galloping set intersection (`OP_BITSET_AND`).

---

## 3. Property Graphs as Grothendieck Fibrations & Functional Optics

Pure GraphBLAS engines represent graphs as homogeneous scalar matrices $\mathbf{A} \in R^{N \times N}$, which creates friction on enterprise **labeled property graphs** containing dozens of heterogeneous node/edge columns (strings, timestamps, nullable numerics, `[N, D]` float32 embeddings) and dynamic filter predicates.

### 3.1 Separation of Base Topology and Attribute Sheaves
Category theory resolves this cleanly by modeling a typed property graph as a **Grothendieck Fibration** $\mathcal{P}: \mathbf{E} \to \mathbf{B}$:

* **Base Category $\mathbf{B}$ (Pure Topology)**: Objects are dense node ID spaces $\mathcal{V}_D = \{0 \dots N_D - 1\}$; generating morphisms are directed relations $\mathcal{E}_R: \mathcal{V}_{\text{Src}} \to \mathcal{V}_{\text{Dst}}$ stored physically as contiguous 128-byte-aligned **CSR (`row_offsets`, `col_targets`)** and **CSC (`csc_offsets`, `csc_sources`)** integer arrays.
* **Attribute Fibers $\mathcal{P}^{-1}(v), \mathcal{P}^{-1}(e)$ (Columnar Sheaves)**: Each node $v \in \mathcal{V}_D$ and edge index $e \in \{0 \dots M_R - 1\}$ carries a typed attribute record stored physically in separate **Structure-of-Arrays (SoA)** columns and Arrow-compatible validity bitmaps.

Traversals navigate the base category $\mathbf{B}$ at integer cache-line speed and project into attribute fibers $\mathbf{E}$ only when a filter or projection demands a specific column (**late materialization**).

### 3.2 Zero-Copy Functional Optics over `mmap` Segments
Attribute operations in `ImpScheme` and Google CEL lower directly into zero-allocation **Functional Optics**:

* **Indexed Lenses ($L: S \to A$) $\to$ SoA Pointer Arithmetic**: Reading `node.age` or `edge.amount` compiles to a direct `MemorySegment` / C-pointer base-plus-index load (`base_ptr + idx * sizeof(T)`), touching only the single requested column's cache lines.
* **Prisms ($P: S \to \mathrm{Option}\langle A \rangle$) $\to$ Zone-Map Partition Skipping**: Section 2 `[min, max]` attribute synopses act as prisms in `ZoneMapPruningPass`; if a predicate range `[low, high]` is disjoint from `[min, max]`, the entire relation or block short-circuits to $\mathbf{0}$ without scanning edges.
* **Guarded Kleisli Arrows $\to$ Functorial Predicate Pushdown**: Filtering at a target domain satisfies the pullback identity:

$$\mathrm{filter}(p) \circ \mathrm{walk}(R) = \mathrm{walk}(R \vert_p)$$

`FilterPushdownPass` fuses target and edge CEL predicates directly into the inner CSR/CSC neighbor loop (`OP_CSR_WALK_STREAM` / SIMD vector mask), discarding non-matching edges before state writeback.

---

## 4. Multiplicity-Driven Bytecode Simplification & Deforestation

Because an `.imps` snapshot is immutable, its Section 2 catalog records exact out-degree and in-degree bounds for every relation. The Stage 2 compiler exploits **relational multiplicity** to eliminate runtime synchronization and intermediate buffers that mutable graph engines must execute unconditionally:

| Multiplicity Class | Categorical / Degree Invariant | Matrix Structure | Compiler & `ImpulseVM` Optimization |
| :--- | :--- | :--- | :--- |
| **Injective ($1:N$)** | Monic inbound fiber: $\forall d,\; |\pi_2^{-1}(d)| \le 1$ (e.g., `Order -> LineItem`) | At most one `1` per column | **Monoid & Atomic Elimination (`InjectiveDeduplicationBypassPass`)**: Two active sources can never collide on the same target $d$. The monoid fold $\bigoplus_{i=1}^1 x = x$ degenerates to a direct unsynchronized store. |
| **Functional ($N:1$)** | $\forall s,\; \text{deg}^+(s) \le 1$ (e.g., `Account -> PrimaryOwner`) | At most one `1` per row | **Bounded-Degree Walk & Deforestation**: Guarantees at most one outgoing neighbor per active source; enables register-resident 2-hop fusion (`OP_CSR_WALK_2HOP`). |
| **Bijective ($1:1$)** | Isomorphism: $\text{deg}^+(s) \le 1 \land \text{deg}^-(d) \le 1$ | Partial permutation matrix $\mathbf{P}$ | **Distributivity over $\cap$ & Lossless Inverse**: $\tau(A \cap B) = \tau(A) \cap \tau(B)$ and $\tau^{-1}(\tau(\mathcal{S})) = \mathcal{S}$, allowing algebraic cancellation of round-trip hops. |
| **General ($M:N$)** | Unbounded $\text{deg}^+(s), \text{deg}^-(d)$ | General sparse CSR / CSC matrix $\mathbf{A}$ | Adaptive Push/Pull selection (`DirectionSelectionPass`) with full SIMD scan and monoidal reduction $\bigoplus$. |

### Wadler Deforestation Across Multi-Hop Chains
Applying Philip Wadler's deforestation theorem ($\mathrm{map}(f) \circ \mathrm{map}(g) = \mathrm{map}(f \circ g)$) to low-multiplicity relation pairs $R_1: \mathcal{V}_A \to \mathcal{V}_B$ and $R_2: \mathcal{V}_B \to \mathcal{V}_C$, `KernelFusionPass` emits `OP_CSR_WALK_2HOP` when intermediate fan-out satisfies `OptimizerConfig` multiplicity bounds—streaming from $\mathcal{V}_A$ through $\mathcal{V}_B$ into $\mathcal{V}_C$ in CPU registers without allocating or scanning an intermediate $\mathcal{V}_B$ bitset.

---

## 5. Algebraic Subtleties: Monoid Laws, Lexicographical Asymmetry & IEEE-754

Parallelizing or reordering reductions requires strict adherence to algebraic laws:

| Algebraic Property | Axiom | Compiler / VM Capability Unlocked | Consequence if Violated |
| :--- | :--- | :--- | :--- |
| **Associativity** | $(a \oplus b) \oplus c = a \oplus (b \oplus c)$ | Arbitrary SIMD lane trees and thread chunking. | Results vary with SIMD width or thread count. |
| **Commutativity** | $a \oplus b = b \oplus a$ | Out-of-order parallel target accumulation. | Race-dependent outputs under multi-threaded push. |
| **Idempotency** | $a \oplus a = a$ | CSC Pull early-exit on first active parent; chaotic lock-free fixed points. | Overcounting when duplicate paths converge (e.g., `+`). |
| **Zero Annihilation** | $a \otimes \mathbf{0} = \mathbf{0} = \mathbf{0} \otimes a$ | Skipping inactive source nodes ($v_s = \mathbf{0}$) in sparse CSR scans. | Incorrect baseline values on unvisited nodes. |

### 5.1 Non-Commutativity of Lexicographical Product Monoids
While a direct product of commutative monoids $(\Sigma_1 \times \Sigma_2, \oplus_1 \times \oplus_2)$ remains commutative, prioritized tie-breaking reducers such as `ArgMin(distance, node_id)` form a **lexicographical product**:

$$\langle d_1, u_1 \rangle \oplus_{\text{lex}} \langle d_2, u_2 \rangle = \begin{cases} \langle d_1, u_1 \rangle & \text{if } d_1 < d_2 \\ \langle d_2, u_2 \rangle & \text{if } d_2 < d_1 \\ \langle d_1, \min(u_1, u_2) \rangle & \text{if } d_1 = d_2 \end{cases}$$

Here $\oplus_{\text{lex}}$ is associative and commutative when tie-broken by $\min(u_1, u_2)$, **but switching primary vs. secondary projection coordinates is asymmetric**. Optimization passes never commute projection order across compound tuple reducers.

### 5.2 IEEE-754 Floating-Point Non-Associativity & Kleene 3VL
Over IEEE-754 `float32`/`float64`, floating-point addition $(a \oplus_{\text{fp}} b)$ is commutative but **not strictly associative** due to rounding ($(10^{20} + (-10^{20})) + 1.0 \neq 10^{20} + (-10^{20} + 1.0)$). Consequently:

* Boolean $(\mathbb{B}, \lor, \land)$, 64-lane bit-sliced $(\mathbb{B}^W, \lor_W, \land_W)$, integer modular arithmetic, and ordered $(\min, \max)$ reductions are **100% bitwise deterministic** across single-threaded and multi-threaded schedules.
* Floating-point `SUM` (`OP_MXV` / PageRank) guarantees bitwise cross-engine parity (`ICTX` v1) in deterministic execution mode (`threads = 1`), with canonical IEEE-754 `NaN`, `-0.0`, and **Kleene 3-valued logic (`TRUE`, `FALSE`, `NULL`)** semantics enforced identically across C++, Java 25, Rust, and the OCaml oracle.

---

## 6. Fixed-Point Convergence, Bit-Sliced Algebras & Direction Optimization

### 6.1 Least Fixed Points & Idempotent Chaotic Relaxation
Recursive `ImpLog` Datalog rules and `repeatUntilStable` traversals compute the Tarski **least fixed point** over the finite lattice of domain frontiers:

$$\mathcal{S}^* = \mathrm{lfp}\left(\lambda X.\; \mathcal{S}_0 \oplus \tau(X)\right)$$

When $\oplus$ is **idempotent** ($a \oplus a = a$, e.g., Boolean reachability $\lor$ or tropical shortest path $\min$) and $\tau$ distributes over $\oplus$:

1. **Semi-Naive Delta Tracking**: Only newly discovered frontier elements $\Delta \mathcal{S}^{(k)} = \mathcal{S}^{(k)} \setminus \mathcal{S}^{(k-1)}$ need to be expanded on iteration $k + 1$.
2. **Chaotic Asynchronous Convergence**: Under idempotent updates, concurrent worker threads can relax target states without per-iteration barriers while still converging to the unique least fixed point $\mathcal{S}^*$. Non-idempotent semirings ($+/\times$) preserve strict Bulk Synchronous Parallel (BSP) step boundaries so each path of length $k$ is accumulated exactly once.

### 6.2 Multi-Lane Bit-Sliced Semirings ($\mathbb{B}^W$, `0xC0`..`0xC9`)
Graph traversal is memory-bandwidth bound: fetching `row_offsets[u]` and `col_targets[e]` from DRAM dominates arithmetic. By lifting the scalar Boolean semiring $\mathbb{B}$ to the $W$-fold product Boolean algebra $\mathbb{B}^W$ ($W \in \{8, 16, 32, 64\}$, `TYPE_LANE_FRONTIER = 0x10`):

* Each node $u$ carries a $W$-bit lane word $L[u] \in \{0, 1\}^W$.
* A single CSR neighbor scan propagates **up to 64 independent seed queries or 64 counterfactual $N-1$ edge-outage scenarios** (`OP_LANE_SET_EDGE_MASK`) per memory read (`L_next[v] |= (L_curr[u] & edge_mask[e])`).
* Consensus / bridge discovery across $K$ semantic vector anchors (`OP_LANE_FILTER_QUORUM`, `0xC6`) reduces to hardware population count: $\mathrm{popcount}(L[v]) \ge q$.

### 6.3 Analytical Cost Model: CSR Push vs. CSC Pull vs. Linear Scan
Given source cardinality $n_{\text{src}}$, target cardinality $n_{\text{dst}}$, edge count $m$, and active source frontier cardinality $s = |\mathcal{S}_{\text{Src}}|$:

```text
                        Active Source Frontier Density (s / n_src)
 0%                         5% – 15%                          60%+                   100%
 ├─────────────────────────────┼────────────────────────────────┼────────────────────────┤
   CSR Push (OP_CSR_WALK)        CSC Pull (OP_CSC_WALK)           Linear BitSet / Stream
   • Work: O(s · d_out)          • Work: O(n_dst) w/ early exit   • Sequential SIMD scan
   • Sparse seed frontiers       • Zero target write conflicts    • Full-domain analytics
```

* **CSR Push (`OP_CSR_WALK`, $s / n_{\text{src}} < 5\%$)**: Reads only outgoing slices of the $s$ active sources ($O(s \cdot \hat{d}_{\text{out}})$).
* **CSC Pull (`OP_CSC_WALK`, $5\% \le s / n_{\text{src}} \le 60\%$, idempotent $\oplus$)**: Iterates sequentially over target nodes $d \in \mathcal{V}_{\text{Dst}}$, writing contiguously with zero scatter-write cache misses or atomic contention, and **early-exits** row $d$ upon encountering the first active parent in `csc_sources`.

---

## 7. GNN Message Passing & Substructural Linear Memory Typing

### 7.1 Equivalence with Message Passing Neural Networks (MPNN)
A Graph Neural Network layer (Gilmer et al., ICML '17) updates node representations $\mathbf{h}_v^{(\ell)} \in \mathbb{R}^D$ via:

$$\mathbf{m}_v^{(\ell+1)} = \bigoplus_{u \in \mathcal{N}(v)} \phi^{(\ell)}\!\left(\mathbf{h}_u^{(\ell)}, \mathbf{h}_v^{(\ell)}, \mathbf{e}_{uv}\right), \qquad \mathbf{h}_v^{(\ell+1)} = \psi^{(\ell)}\!\left(\mathbf{h}_v^{(\ell)}, \mathbf{m}_v^{(\ell+1)}\right)$$

The aggregation step $\mathbf{m}_v^{(\ell+1)}$ is structurally identical to Impulse's Kleisli fiber fold (§2.4) over the vector space $(\mathbb{R}^D, \oplus)$ where $\oplus \in \{\mathrm{sum}, \mathrm{mean}, \mathrm{max}\}$. Storing `[N, D]` feature tensors as 128-byte-aligned SoA columns inside `.imps` allows PyTorch (`impulse-gnn`) to execute neighborhood sampling (`sample_neighbors`) and `torch.from_numpy` / `from_dlpack` tensor slicing directly over shared `mmap` pages without Python heap copies.

### 7.2 Girard's Linear Logic & Zero-Allocation Register Reuse
Impulse's memory model corresponds directly to **Substructural (Linear) Type Theory** (Girard, 1987):

* **Exponential Modality ($!\mathcal{G}$)**: An immutable `.imps` snapshot is typed as $!\mathcal{G}$—a read-only resource mapped into clean OS page-cache pages that can be shared across unlimited concurrent threads and processes with zero locks or copy-on-write duplication.
* **Linear Frontier Buffers ($S_{\text{Src}} \multimap S_{\text{Dst}}$)**: Per-query scratch frontiers bound to VM registers (`R0`..`R63`) are linear resources consumed and recycled across non-overlapping liveness intervals by `RegisterAllocationPass`, guaranteeing **zero dynamic heap allocations (`malloc` / `new`)** in the hot execution loop.

---

## 8. Cross-Discipline Correspondence Glossary

| Category Theory / PL Concept | Sparse Linear Algebra (GraphBLAS) | Impulse Graph Physical Realization |
| :--- | :--- | :--- |
| **Object $D \in \mathrm{Ob}(\mathbf{C}_{\text{Schema}})$** | Vector module $R^{N_D}$ | Node domain with dense IDs $0 \dots N_D - 1$ (`uint16`/`32`/`64`) |
| **Morphism $R: A \to B$** | Sparse matrix $\mathbf{A}_R \in R^{N_A \times N_B}$ | 128B-aligned CSR (`A`) and CSC (`A^T`) segments |
| **Kleisli Bind ($\mathbf{v} \gg= f$)** | Vector-matrix multiply ($\mathbf{v}^T \otimes_R \mathbf{A}_R$) | `OP_CSR_WALK`, `OP_CSC_WALK`, `OP_VXM` |
| **$W$-Fold Boolean Algebra ($\mathbb{B}^W$)** | Bit-packed SpMM ($\mathbf{A} \otimes \mathbf{B}_{N \times W}$) | `TYPE_LANE_FRONTIER` (`0xC0`..`0xC9`, 8/16/32/64 lanes) |
| **Grothendieck Fibration ($\mathcal{P}: \mathbf{E} \to \mathbf{B}$)** | Topology separated from attribute tensors | Disjoint CSR/CSC sections vs. SoA attribute columns |
| **Functional Lens ($L: S \to A$)** | Column vector projection | Late SoA offset load on surviving frontier IDs |
| **Functional Prism ($P: S \to \mathrm{Opt}\langle A \rangle$)** | Block sparsity mask | Section 2 `[min, max]` Zone-Map pruning |
| **Monic Inbound Morphism ($1:N$)** | Column-monomial matrix ($\le 1$ entry/col) | `InjectiveDeduplicationBypassPass` (lock/monoid elision) |
| **Wadler Deforestation** | Fused two-step implicit SpGEMM | `OP_CSR_WALK_2HOP` register-resident 2-hop walk |
| **First Futamura Projection** | Specialized SpMV codegen | Java 25 `MethodHandle` combinator JIT (`ShaderCompiler`) |
| **Exponential / Linear Types ($!\mathcal{G}, S \multimap S$)** | Read-only matrix + ping-pong work vectors | Shared `mmap` `.imps` + caller-allocated `R0`..`R63` scratch arena |

---

## Next Steps

* **[Research Literature & Design Lineage](academic/literature-and-influences.md)**: Annotated bibliography of 31 peer-reviewed papers across GraphBLAS, register VMs, Vamana DiskANN, `mmap` DBMS storage theory, Datalog, and RCU concurrency.
* **[Compiler Pipeline & ImpulseVM](concepts/compiler-architecture.md)**: How Stage 1 and Stage 2 passes lower `ImpScheme` into 64-bit `impOps` bytecode.
* **[Data-Oriented Design](concepts/data-oriented-design.md)**: Cache-line packing, SIMD vectorization, and off-heap memory layout.
