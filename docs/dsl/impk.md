# ImpK Specification (`.impk`)

> **Architectural Role**: **Primary User Frontend DSL (Array & Vector Math)**
>
> **ImpK** (`.impk`) is the high-level array and vector domain-specific language for the **Impulse Graph Engine**, designed for GraphBLAS matrix mathematics, PageRank, connected components, triangle counting, and SIMD vector operations. It compiles down to `ImpScheme` (`.impscm`) intermediate representation before being emitted as `ImpulseVM` bytecode (`impOps`).


---

## 1. Syntax & Core Primitives

ImpK treats graphs as sparse adjacency matrices, frontiers as bitsets/vectors, and traversals as matrix-vector products.

### Operator Primitives

| ImpK Infix Operator | Operation | Compiles To S-Expression IR |
| :--- | :--- | :--- |
| `g @[f; "REL"]` | Sparse Matrix-Vector Product (CSR Walk) | `(g:walk-csr g f "REL")` |
| `a &~ b` | Bitset Difference (AND-NOT) | `(bitset:and-not a b)` |
| `a \| b` | Bitset Union (OR) | `(bitset:or a b)` |
| `a & b` | Bitset Intersection (AND) | `(bitset:and a b)` |
| `bitset start_node` | Bitset creation from single node | `(bitset:from start_node)` |

---

## 2. Code Example: 1-Hop ReBAC Filtered Traversal in ImpK

```q
/ Multi-Hop ReBAC Authorization Check in ImpK (.impk)
fn check_reachability(g, start_user, target_doc) {
    frontier: bitset start_user
    visited: bitset start_user

    / Advance frontier via CSR walk and compute bitset difference
    frontier: (g @[frontier; "MEMBER_OF"]) &~ visited
    visited: visited | frontier

    return true
}
```

---

## 3. Code Example: PageRank (GraphBLAS Plus-Times Semiring)

```q
/ PageRank Algorithm in ImpK
fn pagerank(g, damping, max_iters, epsilon) {
    n: g.node_count
    p: vector(n, 1.0 / n)
    deg: g.out_degrees
    teleport: (1.0 - damping) / n

    until[iter >= max_iters] {
        norm_p: p / deg
        incoming: g @[norm_p; +*]
        p: (incoming * damping) + teleport
    }

    return p
}
```

---

## 4. Compiling ImpK

Using the `impulse-graph` CLI toolchain:

```bash
# 1. Compile .impk source directly into canonical .impas assembly text
impulse compiler compile algorithm.impk -o algorithm.impas

# 2. Inspect intermediate ImpScheme AST S-Expressions
impulse compiler compile algorithm.impk --emit-ir

# 3. Assemble text assembly into binary bytecode (.impb)
impulse compiler assemble algorithm.impas -o algorithm.impb

# 4. Execute compiled bytecode program against a snapshot
impulse run --snapshot production.imps --bytecode algorithm.impb
```
