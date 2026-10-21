# ImpLog Specification (`.implog`)

> **Architectural Role**: **Primary User Frontend DSL (Declarative Datalog & Logic)**
>
> **ImpLog** (`.implog`) is the high-level declarative Datalog logic domain-specific language for the **Impulse Graph Engine**, designed for fine-grained Relationship-Based Access Control (ReBAC / Google Zanzibar), transitive reachability, security policy verification, and recursive graph analytics. It compiles down to `ImpScheme` (`.impscm`) intermediate representation before being emitted as `ImpulseVM` bytecode (`impOps`).

---

## 1. Executive Summary & Core Value Proposition

While traditional query languages (such as Cypher or SQL) struggle with recursive traversals, unbounded path reachability, and combinatorial path explosions, **ImpLog provides pure set-theoretic declarative logic rules with guaranteed polynomial-time least fixed-point convergence (Minimal Herbrand Model)**.

```
 Traditional Graph Traversal (Cypher / SQL) ImpLog Declarative Logic (.implog)
 ──────────────────────────────────────────        ───────────────────────────────────
 • Path iteration with combinatorial explosion    • Pure Set-Theoretic Deduplication (NodeSet<T>)
 • Manual loop limits (e.g. [*1..5])              • Unbounded Transitive Closure (Kleene Star τ*)
 • Ad-hoc DISTINCT deduplication                  • Semi-Naïve Evaluation with Roaring Bitsets
 • Dynamic heap allocation & GC stalls            • Zero-Copy Off-Heap Execution directly over .imps
```

---

## 2. Syntax & Grammar Specification

ImpLog specifies computation through **Type Declarations**, **Relations**, **Facts**, and **Rules** (`Head :- Body`).

### 2.1 Relation Declarations & Stratification
```prolog
// Relation declarations specify strongly typed domain arguments
.decl direct_member(user: User, group: Group)
.decl group_hierarchy(child: Group, parent: Group)
.decl has_role(user: User, role: Role)
.decl role_permission(role: Role, perm: Permission)
.decl is_admin(user: User)
```

### 2.2 Rule Clauses & Operators

| ImpLog Syntax | Meaning | Compiled `ImpulseVM` Engine Behavior |
| :--- | :--- | :--- |
| `H(X, Z) :- R1(X, Y), R2(Y, Z).` | **Conjunction (Join)** | Multi-hop edge traversal via `OP_CSR_WALK` / `OP_CSC_WALK`. |
| `H(X, Y) :- R1(X, Y) ; R2(X, Y).`| **Disjunction (Union)**| Union of derivations via `OP_SET_UNION` / bitset OR. |
| `H(X) :- R(X), !Forbidden(X).` | **Stratified Negation** | Fast bitset difference via `OP_ROARING_BITMAP_AND_NOT`. |
| `Dist(S, D, min(C)) :- ...` | **Lattice / Aggregation** | Monoidal in-flight reduction ($\bigoplus$) at destination fiber. |
| `?- can_access(1042, Doc).` | **Bound Query Goal** | Magic Sets rewriting to push seed bindings into traversal roots. |

---

## 3. Advanced Language Features

### 3.1 Lattice Datalog & In-Flight Recursive Aggregations
ImpLog natively supports **Lattice Datalog ($\text{Datalog}^\mathcal{L}$)**, allowing numerical attributes from semirings to be accumulated directly *inside recursive loops* without breaking fixed-point convergence:

```prolog
// All-Pairs Shortest Path via In-Flight Monoidal Minimum:
.decl shortest_path(src: Node, dst: Node, cost: float64)

shortest_path(X, Y, min(C)) :- 
    road(X, Y, C) ;
    (shortest_path(X, Z, C1), road(Z, Y, C2), C = C1 + C2).
```

Because $(\mathbb{R}^+ \cup \{\infty\}, \min, +)$ is an **idempotent and monotonic semiring**, Tarski's Fixed-Point Theorem guarantees convergence in at most $|\mathcal{V}|$ iterations without infinite looping.

---

### 3.2 Magic Sets Rewriting (Goal-Directed Query Optimization)
When a query provides bound variables (e.g. checking authorization for a single user `?- can_view(42, D)`), a naive Datalog engine computes group memberships for all users in the database.

The ImpLog compiler automatically applies **Magic Sets Transformation**:
1. It analyzes the Adorned Dependency Graph.
2. It generates a companion `magic_user(42)` relation.
3. It rewrites recursive rules so traversal expands **only the transitive subgraph reachable from user 42**, skipping 99.9% of unrelated graph nodes.

---

### 3.3 Stratified Negation & Difference
Negation (`!rel(X)`) is verified for strict stratification (no negative cycles in the rule dependency graph). Stratified negation compiles to zero-allocation hardware bitwise operations:

$$\Delta_{\text{valid}} = \Delta_{\text{derived}} \land \neg \text{Forbidden}$$

```prolog
// Revocation / Deny-List Overrides
can_access(U, Resource) :- 
    has_permission(U, Resource), 
    !account_locked(U), 
    !ip_banned(U).
```

---

## 4. Showcase: ReBAC (Zanzibar) Authorization Policies

ImpLog is the primary DSL for **Relationship-Based Access Control (ReBAC)**:

```prolog
// ReBAC Zanzibar Authorization Schema (.implog)
.decl direct_member(u: User, g: Group)
.decl group_parent(child: Group, parent: Group)
.decl doc_owner(d: Document, u: User)
.decl doc_editor(d: Document, g: Group)
.decl doc_viewer(d: Document, g: Group)
.decl can_view(u: User, d: Document)
.decl can_edit(u: User, d: Document)

// 1. Transitive Group Membership (Recursive Base + Step)
member(U, G) :- direct_member(U, G).
member(U, Parent) :- member(U, Child), group_parent(Child, Parent).

// 2. Ownership Implies Full Rights
can_edit(U, D) :- doc_owner(D, U).
can_view(U, D) :- doc_owner(D, U).

// 3. Role-Based Group Permissions
can_edit(U, D) :- member(U, G), doc_editor(D, G).
can_view(U, D) :- member(U, G), doc_viewer(D, G).

// 4. Permission Inheritance: Editors are Viewers
can_view(U, D) :- can_edit(U, D).
```

---

## 5. Semi-Naïve Evaluation & Hardware Acceleration

The ImpLog compiler lowers recursive rules to the **Semi-Naïve Fixed-Point Iteration Algorithm**, ensuring no intermediate edge is traversed twice:

$$\Delta \mathcal{S}_{t+1} = \text{Traverse}(\Delta \mathcal{S}_t) \setminus \mathcal{S}_{\text{visited}}$$
$$\mathcal{S}_{\text{visited}} = \mathcal{S}_{\text{visited}} \cup \Delta \mathcal{S}_{t+1}$$

```
                ┌──────────────────────────────────────────────┐
                │ Seed Input: ΔS₀ = { User_ID }       │
                └──────────────────────┬───────────────────────┘
                                       │
                                       ▼
    ┌───────────────────────────> Loop Step t ───────────────────────────┐
    │                                  │                                 │
    │                                  ▼                                 │
    │ OP_CSR_WALK / OP_CSC_WALK                        │
    │ Expand outbound group neighbors                  │
    │                                  │                                 │
    │                                  ▼                                 │
    │ OP_ROARING_BITMAP_AND_NOT                        │
    │                   ΔS_{t+1} = Expanded ∖ Visited                    │
    │                                  │                                 │
    │                     ┌────────────┴────────────┐                    │
    │                     ▼                         ▼                    │
    │            ΔS_{t+1} is Empty?         ΔS_{t+1} has Elements?       │
    │                     │                         │                    │
    │                     ▼                         ▼                    │
    │             [ EXIT LOOP ] OP_ROARING_BITMAP_OR         │
    │ Return Visited Set Visited = Visited ∪ ΔS_{t+1} │
    │                                               │                    │
    └───────────────────────────────────────────────┴────────────────────┘
```

---

## 6. ImpLog vs. Other Datalog Engines

| Dimension | Classical Soufflé | Differential Datalog (DDlog) | Impulse ImpLog |
| :--- | :--- | :--- | :--- |
| **Storage Architecture** | In-memory RAM B-Trees | In-memory DD Collections | **Zero-Copy Memory-Mapped (`.imps` )** |
| **Cold-Start Latency** | $O(\text{data})$ Physical CSV Loading | $O(\text{data})$ State Replay | **$O(1)$ Instant Mount ($< 1\,\mu\text{s}$)** |
| **Bitset Traversal** | Scalar / 64-bit word | Differential Multi-sets | **AVX-512 SIMD Vector Bitsets (512 bits/inst)** |
| **Hardware Alignment** | General Heap pointers | Rust Heap structs | **Strict 128-byte hardware cache alignment** |
| **Query Specialization**| Native C++ code generation | Rust crate compilation | **ImpScheme Free Monad $\to$ `impOps` Bytecode** |

---

## 7. Compilation & CLI Toolchain

Using the `impulse-graph` CLI developer tools:

```bash
# 1. Compile .implog source into human-readable ImpAsm (.impas)
impulse compile authz.implog -o authz.impas

# 2. Inspect intermediate S-Expression AST (ImpScheme IR)
impulse compile authz.implog --emit-ir

# 3. Assemble text assembly into binary bytecode (.impb)
impulse assemble authz.impas -o authz.impb

# 4. Execute query program against an immutable snapshot
impulse run --snapshot production.imps --bytecode authz.impb --input-val 1042
```

