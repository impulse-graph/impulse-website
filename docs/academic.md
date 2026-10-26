# Mathematical & GraphBLAS Foundations

This page formalizes the mathematical foundation of the **Impulse Graph Engine** query model—contrasting its **set-theoretic, semiring-weighted semantics** with traditional **multi-set (bag) path engines** (SQL, Neo4j Cypher, Gremlin) and showing its exact duality with **GraphBLAS sparse linear algebra** and **Kleisli composition**.

---

## 1. Set-Theoretic State Semantics vs. Multi-Set (Bag) Path Enumeration

Traditional relational and property-graph databases evaluate queries in the **Multi-Set (Bag) Monad** $\mathcal{M}(X) = X \to \mathbb{N}$. If a destination node $d$ is reachable via $k$ distinct paths of length $m$, a bag-based engine emits $k$ duplicate intermediate path tuples—causing frontier cardinality to grow exponentially ($O(\hat{d}^m)$, "path explosion") and requiring dynamic heap allocations and hash-table deduplication (`DISTINCT`).

Impulse Graph replaces bag iteration with **Semiring-Weighted Set Semantics** ($\mathcal{W}_R(X) = X \to R$):

```text
 Traditional Engines (SQL / Cypher)                 Impulse Graph Engine (.imps)
 ──────────────────────────────────                 ────────────────────────────
 • Multi-Set (Bag) Monad: M(X) = X → ℕ              • Semiring-Weighted Set: W_R(X) = X → R
 • Frontier size: O(d^k) [Path Explosion]           • Frontier Bound: |S| ≤ |V_target|
 • Explicit DISTINCT hash-table deduplication       • Automatic Monoidal Reduction (⊕) at every hop
 • Dynamic heap allocations per path tuple          • Pre-determined, zero-allocation off-heap arrays
```

### The Frontier Bounding Invariant
Because intermediate states are keyed strictly by unique dense node IDs ($0 \dots N_d - 1$) in the active domain $\mathcal{V}_d$, the cardinality of any intermediate frontier $\mathcal{S}_d$ is bounded above by the domain's node count:

$$\forall \tau: \mathcal{V}_{\text{Src}} \to \mathcal{V}_{\text{Dst}}, \quad |\tau(\mathcal{S}_{\text{Src}})| \le |\mathcal{V}_{\text{Dst}}| = N_{\text{Dst}}$$

Path explosion is impossible by construction, and the exact memory required for any intermediate frontier is known statically before the query executes.

---

## 2. State-Tagged Node Sets, Monoidal Reduction & Kleisli Composition

Let an `.imps` snapshot define a heterogeneous typed graph $\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{A}_{\mathcal{V}}, \mathcal{A}_{\mathcal{E}})$, where $\mathcal{V} = \bigsqcup_{D} \mathcal{V}_D$ is partitioned into disjoint node domains and each relation $\mathcal{E}_R \subseteq \mathcal{V}_{\text{Src}} \times \mathcal{V}_{\text{Dst}}$ connects a source domain to a target domain.

### 2.1 State-Tagged Frontier ($\mathcal{S}_D$)
At any stage in a query pipeline anchored at domain $D$, the active frontier is a set of pairs:

$$\mathcal{S}_D \subseteq \mathcal{V}_D \times \Sigma$$

where $v \in \{0 \dots N_D - 1\}$ is a dense node ID, $\sigma_v \in \Sigma$ is its attached state payload, and $(\Sigma, \oplus, \mathbf{0})$ forms a **commutative monoid** with associative binary reduction operator $\oplus: \Sigma \times \Sigma \to \Sigma$ and identity element $\mathbf{0}$.

### 2.2 Edge Walk Transition ($\phi$) & Monoidal Fusion ($\bigoplus$)
Stepping across a directed relation $R: \mathcal{V}_{\text{Src}} \to \mathcal{V}_{\text{Dst}}$ applies an edge transition map $\phi(\sigma_s, s, e, d)$ along each active edge $e = (s, d) \in \mathcal{E}_R$ and immediately fuses all incoming values landing on the same destination node $d$ via $\bigoplus$:

$$\sigma_d' = \bigoplus_{(s, e) \in \text{Inbound}_R(d), \; (s, \sigma_s) \in \mathcal{S}_{\text{Src}}} \phi\left(\sigma_s, s, \mathcal{A}_{\mathcal{E}}(e), d\right)$$

* **Associativity & Commutativity of $\oplus$**: Guarantees deterministic results regardless of SIMD vector lane grouping or multi-threaded execution order.
* **Kleisli Pipeline Chaining ($\gg=$)**: Because every step $\tau_k$ consumes a valid $\langle D_{k-1}, \mathcal{S}_{k-1} \rangle$ and produces $\langle D_k, \mathcal{S}_k \rangle$, multi-hop queries compose associatively as Kleisli arrows:
  $$\text{Pipeline} = \text{Anchor}(D_0, \mathcal{S}_0) \gg= \tau_1 \gg= \tau_2 \dots \gg= \tau_k \gg= \text{Collect}()$$

### 2.3 Degeneracy to Pure BitSet Reachability ($\Sigma = \mathbb{B}$)
When a query tracks reachability without numeric state, $\Sigma$ degenerates to the Boolean monoid $(\{\text{false}, \text{true}\}, \lor, \text{false})$:

$$\sigma_d' = \bigvee_{(s, e) \in \text{Inbound}_R(d)} \sigma_s$$

The frontier $\mathcal{S}_D$ is simply a contiguous off-heap **BitSet** ($\lceil N_D / 64 \rceil$ 64-bit words), and monoidal reduction executes as a single bitwise `OR` instruction (`w_dst |= mask`).

---

## 3. GraphBLAS Semiring Duality ($\mathbf{u}^T = \mathbf{v}^T \otimes \mathbf{A}_R$)

Every domain-to-domain walk in Impulse Graph is isomorphic to sparse **vector-matrix multiplication (`MxV` / `vXM`)** over an algebraic **Semiring** $(R, \oplus, \otimes, \mathbf{0}, \mathbf{1})$:

$$u_d = \bigoplus_{s = 0}^{N_{\text{Src}} - 1} \left( v_s \otimes A_{s, d} \right)$$

| Graph Workload | Frontier State $\mathbf{v}$ | Semiring $(R, \oplus, \otimes, \mathbf{0}, \mathbf{1})$ | Impulse Transition $\phi$ & Monoid $\oplus$ |
| :--- | :--- | :--- | :--- |
| **Boolean Reachability / ReBAC** | BitSet ($\lceil N_d/64 \rceil$ words) | $(\mathbb{B}, \lor, \land, \text{false}, \text{true})$ | $\phi = \text{true}, \quad \oplus = \lor$ (Bitwise `OR`) |
| **Shortest Path (BFS / Dijkstra)** | Distance array (`float32`/`int32`) | $(\mathbb{R}_{\ge 0} \cup \{\infty\}, \min, +, \infty, 0)$ | $\phi = \sigma_s + e.\text{weight}, \quad \oplus = \min$ |
| **Widest Path / Max Capacity** | Capacity array (`float64`) | $(\mathbb{R}_{\ge 0} \cup \{\infty\}, \max, \min, 0, \infty)$ | $\phi = \min(\sigma_s, e.\text{cap}), \quad \oplus = \max$ |
| **PageRank / Financial Flow** | Score / amount array (`float64`) | $(\mathbb{R}, +, \times, 0, 1)$ | $\phi = \sigma_s \times e.\text{weight}, \quad \oplus = +$ (`SUM`) |
| **Fixed-Point Reachability ($\tau^*$)** | BitSet / state array | Idempotent Kleene Algebra ($\sigma \oplus \sigma = \sigma$) | $\mu \mathcal{S}'. (\mathcal{S}_0 \oplus \tau(\mathcal{S}'))$ via `repeatUntilStable` |

Because `.imps` stores relations natively as 128-byte-aligned **CSR (`A`)** and **CSC (`A^T`)** matrices, forward walks ($\mathbf{v}^T \otimes \mathbf{A}$) and reverse walks ($\mathbf{v}^T \otimes \mathbf{A}^T$) execute directly over the memory-mapped arrays with identical $O(\text{active edges})$ memory bandwidth.

---

## 4. Relational Multiplicities ($1:1, 1:N, N:1$) & Bytecode Simplifications

Each relation in an `.imps` snapshot records its exact degree bounds in the Section 2 catalog. The Stage 2 compiler exploits relational multiplicity to strip unnecessary runtime work at the bytecode level:

| Multiplicity | Degree Invariant | Matrix Structure | Algebraic & Bytecode Simplification |
| :--- | :--- | :--- | :--- |
| **$1:1$ (Bijective)** | $\text{Out}(s) \le 1 \land \text{In}(d) \le 1$ | Partial Permutation Matrix $\mathbf{P}$ | Exact distributivity over set intersection ($\cap$) and lossless inverse walk ($\tau^{-1}(\tau(\mathcal{S})) = \mathcal{S}$). |
| **$1:N$ (Injective)** | $\text{In}(d) \le 1$ (e.g., `Order` $\to$ `LineItem`) | At most 1 incoming edge per target $d$ | **Collision-Free Target Writes**: Two source nodes can never land on the same target $d$. Bypasses monoid reduction $\bigoplus$ and deduplication hashing (`InjectiveDeduplicationBypassPass`). |
| **$N:1$ (Functional)** | $\text{Out}(s) \le 1$ (e.g., `Account` $\to$ `Owner`) | At most 1 outgoing edge per source $s$ | **Direct 1D Lookup**: Replaces 2-array CSR offset indirection (`row_offsets` + `col_indices`) with a single $O(1)$ dense array lookup `target_id = col_indices[src_id]`. |
| **$M:N$ (General)** | Arbitrary degrees | Sparse CSR / CSC Matrix $\mathbf{A}$ | Full SIMD CSR/CSC vector-matrix scan with monoidal reduction $\bigoplus$. |

---

## 5. Analytical Cost Model: CSR Push vs. CSC Pull vs. COO Stream

Given source domain size $n_{\text{src}}$, target domain size $n_{\text{dst}}$, edge count $m$, and active source frontier size $s = |\mathcal{S}_{\text{Src}}|$, total step cost decomposes into memory access ($T_{\text{mem}}$), transition calculation ($T_{\text{calc}}$), and target reduction ($T_{\text{reduce}}$):

$$T_{\text{Step}} = T_{\text{mem}} + T_{\text{calc}} + T_{\text{reduce}}$$

```text
                        Active Source Frontier Density (s / n_src)
 0%                         5% – 15%                          60%+                   100%
 ├─────────────────────────────┼────────────────────────────────┼────────────────────────┤
   CSR Push (Forward Walk)       CSC Pull (Direction-Optimized)   COO / Dense BitSet Scan
   • Work: O(s · d_out)          • Work: O(n_dst) with early exit • 100% linear SIMD stream
   • Best for sparse seeds       • Sequential target writes       • Best for full-graph passes
```

| Execution Strategy | When Selected (`DirectionSelectionPass`) | Memory & Hardware Behavior |
| :--- | :--- | :--- |
| **1. CSR Push (`OP_CSR_WALK`)** | **Sparse Frontier ($s / n_{\text{src}} < 5\%$)** | Scans only outgoing edges of the $s$ active source nodes ($O(s \cdot \hat{d}_{\text{out}})$ reads). |
| **2. CSC Pull (`OP_CSC_WALK`)** | **Medium/Dense Frontier ($5\% \le s / n_{\text{src}} \le 60\%$)** and idempotent monoid ($\lor, \min, \max$) | Iterates sequentially over target nodes $d \in \mathcal{V}_{\text{Dst}}$; writes sequentially to target memory (`0` scatter-write cache misses) and **early-exits** as soon as the first active parent is found. |
| **3. Linear Stream / BitSet** | **Ultra-Dense / Full-Domain Scan ($s / n_{\text{src}} > 60\%$)** | Streams linearly across the contiguous edge array or packed 64-bit bitset words at peak hardware prefetcher bandwidth. |

---

## Next Steps

* **[Compiler Pipeline & ImpulseVM](concepts/compiler-architecture.md)**: How the two-stage optimizer applies these algebraic rules to emit `impOps` bytecode.
* **[Data-Oriented Design](concepts/data-oriented-design.md)**: How Dense IDs, CSR/CSC, and SoA columns map these mathematical structures onto CPU cache lines.
