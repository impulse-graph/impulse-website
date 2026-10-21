# ImpScheme Specification (`.impscm`)

> **Architectural Role**: **Universal Compiler IR & Low-Level Macro Extension Target**
>
> **ImpScheme** (`.impscm`) is the homoiconic S-Expression intermediate representation and macro extension language for the **Impulse Graph Engine**. It serves as both the internal AST compiler bus for higher-level frontends (`ImpK` and `ImpLog`) and a directly authorable low-level scripting/macro language for compiler engineers and advanced power users.


---

## 1. Syntax & Core Primitives

ImpScheme uses parenthesized Lisp/Scheme forms. All expressions are evaluated prefix style.

### Primitive Data Types
* `node` (u32 node index)
* `bitset` (Roaring bitmap / dense bitset handle)
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
| `(bitset:from node)` | Create bitset from root node ID | `OP_COLLECT_BITSET` |
| `(g:walk-csr g frontier "REL")` | Advance 1-hop across relation via CSR | `OP_CSR_WALK` |
| `(g:walk-csc g frontier "REL")` | Reverse 1-hop traversal via CSC | `OP_CSC_WALK` |
| `(bitset:and a b)` | Bitwise AND intersection | `OP_ROARING_BITMAP_AND` |
| `(bitset:or a b)` | Bitwise OR union | `OP_ROARING_BITMAP_OR` |
| `(bitset:not a)` | Bitwise NOT complement | `OP_ROARING_BITMAP_NOT` |
| `(bitset:and-not a b)` | Fused Bitwise AND-NOT difference | `OP_ROARING_BITMAP_AND_NOT` |
| `(g:walk-csr-filtered g f "REL" m)` | Fused CSR Walk & Bitset Mask Filter | `OP_CSR_WALK_FILTERED` |

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
impulse compiler compile reachability.impscm -o reachability.impas

# 2. Inspect intermediate AST S-Expressions
impulse compiler compile reachability.impscm --emit-ir

# 3. Assemble .impas text into binary bytecode (.impb)
impulse compiler assemble reachability.impas -o reachability.impb

# 4. Execute query program against snapshot
impulse run --snapshot production.imps --bytecode reachability.impb --input-val 1042
```
