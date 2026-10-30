# ImpScheme Specification (`.impscm`)

!!! note "Internal Compiler IR — Prefer Higher-Level APIs for Application Queries"
    **ImpScheme (`.impscm`) is primarily an internal compiler implementation detail**—the homoiconic S-Expression Intermediate Representation (IR) that sits between Impulse's user-facing frontends and the `impOps` bytecode emitter.

    While writing `.impscm` directly is fully supported (and useful for compiler pass debugging, custom macro authoring, or low-level benchmarking), **application developers will almost always be better served by higher-level options**:

    * **[Fluent Traversal API](../query-api/fluent-api.md)** (`snap.domain("User").fromKey(...).out(...)`)
    * **[openCypher Prepared Statements](opencypher.md)** (`snap.prepare("MATCH ... WHERE ... RETURN ...")`)
    * **[Google CEL Filters & Projections](cel.md)** (`node.age >= 21 && edge.amount > 1000.0`)
    * **[ImpK](impk.md)** or **[ImpLog](implog.md)** domain-specific languages

    All of those higher-level interfaces automatically compile down to this exact `ImpScheme` IR under the hood.

> **Architectural Role**: **Universal Compiler IR & Low-Level Macro Extension Target**
>
> **ImpScheme** (`.impscm`) serves as the common AST compiler bus where logical optimization passes (filter fusion, partition elimination, direction selection, and register allocation) are performed before emitting `ImpulseVM` bytecode.


---

## 1. Syntax & Core Primitives

ImpScheme uses parenthesized Lisp/Scheme forms. All expressions are evaluated prefix style.

### Primitive Data Types
* `node` (u32 node index)
* `bitset` (Roaring bitmap / dense bitset handle)
* `lane-frontier` (8/16/32/64-bit multi-lane bit-sliced frontier handle, `TYPE_LANE_FRONTIER = 0x10`, `v0.9.1`)
* `graph` (snapshot handle)
* `int` / `float` / `bool` (scalar primitives)

### Core Language Forms

```scheme
;; Defining a Query Function
(define-query (fn-name [arg1 : type1] [arg2 : type2]) -> return-type
  body ...)

;; Lexical Bindings
(let ([var1 val1]
      [var2 val2])
  body ...)

;; Variable Mutation
(set! var val)

;; Return Form
(return expr)

;; Conditional Branching
(if condition then-expr else-expr)
```

---

## 2. Graph & Vector Operators

ImpScheme exposes native `impOps` primitives directly as S-expressions:

| ImpScheme Form | Functionality | Target `impOps` Opcode |
| :--- | :--- | :--- |
| `(bitset:from node)` | Create bitset from root node ID | `OP_INIT_INPUT_SET` |
| `(g:walk-csr g frontier "REL")` | Advance 1-hop across relation via CSR | `OP_CSR_WALK` |
| `(g:walk-csc g frontier "REL")` | Reverse 1-hop traversal via CSC | `OP_CSC_WALK` |
| `(bitset:and a b)` | Bitwise AND intersection | `OP_ROARING_BITMAP_AND` (`OP_SET_INTERSECT`) |
| `(bitset:or a b)` | Bitwise OR union | `OP_ROARING_BITMAP_OR` (`OP_SET_UNION`) |
| `(bitset:not a)` | Bitwise NOT complement | `OP_MASK_NOT` (fused into `OP_ROARING_BITMAP_AND_NOT`) |
| `(bitset:and-not a b)` | Fused Bitwise AND-NOT difference | `OP_ROARING_BITMAP_AND_NOT` (`OP_SET_DIFFERENCE`) |
| `(g:walk-csr-filtered g f "REL" m)` | Fused CSR Walk & Bitset Mask Filter | `OP_CSR_WALK_FILTERED` |
| `(lane-init-seeds seed_reg width_flag)` | Initialize `TYPE_LANE_FRONTIER` from up to 64 seed node IDs (`v0.9.1`) | `OP_LANE_INIT_SEEDS` (`0xC0`) |
| `(lane-init-groups pairs_reg num_groups)` | Initialize `TYPE_LANE_FRONTIER` from `(node_id, group_idx)` pairs (`v0.9.1`) | `OP_LANE_INIT_GROUPS` (`0xC1`) |
| `(lane-set-edge-mask pairs_reg "REL")` | Attach counterfactual per-edge trip mask for relation `"REL"` (`v0.9.1`) | `OP_LANE_SET_EDGE_MASK` (`0xC2`) |
| `(lane-walk-csr "REL" [1])` | Bit-sliced forward CSR step (optional `1` enables `FIXPOINT` loop) (`v0.9.1`) | `OP_LANE_CSR_WALK` (`0xC3`) |
| `(lane-walk-csc "REL" [1])` | Bit-sliced reverse CSC step (optional `1` enables `FIXPOINT` loop) (`v0.9.1`) | `OP_LANE_CSC_WALK` (`0xC4`) |
| `(lane-prune-mask mode arg0 arg1)` | Prune lane bits (`0` = deny mask, `1` = `ALLOW & ~DENY`, `2` = hub quorum) (`v0.9.1`) | `OP_LANE_PRUNE_MASK` (`0xC5`) |
| `(lane-filter-quorum min_quorum mask_reg)` | Filter nodes with `popcount(lanes[u] & req_mask) >= min_quorum` into `TYPE_BITSET_HANDLE` (`v0.9.1`) | `OP_LANE_FILTER_QUORUM` (`0xC6`) |
| `(lane-reduce-and)` | Bitwise AND reduction across all domain nodes (`v0.9.1`) | `OP_LANE_REDUCE_AND` (`0xC7`) |
| `(lane-reduce-attr attr_id reduce_op)` | Per-lane attribute reduction (`SUM`, `MIN`, `MAX`, `COUNT`, `ARGMIN`, `ARGMAX`) (`v0.9.1`) | `OP_LANE_REDUCE_ATTR` (`0xC8`) |
| `(lane-set-cover mask_reg mode)` | Greedy minimum witness node cover or 2-node pair cover over `mask_reg` (`v0.9.1`) | `OP_LANE_SET_COVER` (`0xC9`) |
| `(vector-ann-search q_reg top_k idx_id fused)` | Vamana ANN beam search (`fused = 1` outputs `TYPE_LANE_FRONTIER`) (`v0.9.1`) | `OP_VECTOR_ANN_SEARCH` (`0xCA`) |
| `(vector-rerank-dot q_reg attr_id metric)` | Exact SIMD similarity reranking (`L2`, `COSINE`, `DOT`) over active frontier (`v0.9.1`) | `OP_VECTOR_RERANK_DOT` (`0xCB`) |

---

## 3. Code Example: Multi-Hop BFS Reachability

```scheme
;; ====================================================================
;; Multi-Hop BFS Reachability Check in ImpScheme (.impscm)
;; ====================================================================

(define-query (bfs-reachability [g : graph] [start : node] [target : node])
  (let ([frontier (bitset:from start)]
        [visited (bitset:from start)])

    ;; Perform 1-hop CSR walk and remove visited nodes
    (set! frontier (bitset:and-not (g:walk-csr g frontier "FOLLOWS") visited))
    (set! visited (bitset:or visited frontier))

    (return #t)))
```

---

## 4. Automatic Vector Fusion Passes

The ImpScheme compiler performs term rewriting optimization passes before register allocation.

### Example: Fusing `AND` + `NOT` into `OP_ROARING_BITMAP_AND_NOT`

When the compiler encounters:
```scheme
(bitset:and next-nodes (bitset:not visited))
```

The AST term rewriter collapses it to:
```scheme
(bitset:and-not next-nodes visited)
```

Generating a single hardware-accelerated Roaring Bitset operation:
```assembly
OP_ROARING_BITMAP_AND_NOT R8, R9, R11
```

---

## 5. Compiling & Executing ImpScheme

Using the `impulse-graph` CLI:

```bash
# 1. Compile .impscm source to canonical .impas assembly text
impulse compile reachability.impscm -o reachability.impas

# 2. Inspect intermediate AST S-Expressions
impulse compile reachability.impscm --emit-ir

# 3. Assemble .impas text into binary bytecode (.impb)
impulse assemble -i reachability.impas -o reachability.impb

# 4. Execute query program against snapshot
impulse run --snapshot production.imps --bytecode reachability.impb --input-val 1042
```
