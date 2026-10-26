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

## 4. Compiling ImpK via CLI

Using the `impulse-graph` CLI toolchain:

```bash
# 1. Compile .impk source directly into canonical .impas assembly text
impulse compile algorithm.impk -o algorithm.impas

# 2. Inspect intermediate ImpScheme AST S-Expressions
impulse compile algorithm.impk --emit-ir

# 3. Assemble text assembly into binary bytecode (.impb)
impulse assemble -i algorithm.impas -o algorithm.impb

# 4. Execute compiled bytecode program against a snapshot
impulse run --snapshot production.imps --bytecode algorithm.impb
```

---

## 5. Executing `.impk` Programs from Host SDKs

In-process compilation and execution of `.impk` scripts is exposed directly through the C-ABI (`IMPULSE_LANG_IMPK`), the C++20 `impulse::impk::ImpKCompiler`, or via pre-assembled `.impb` bytecode in Java and polyglot SDKs:

=== "C / C++20 (`impulse_compile_and_execute`)"
    ```c
    #include "impulse_vm.h"

    const char* impk_script =
        "fn reach(g, start_node) {\n"
        "    f: bitset start_node\n"
        "    return g @[f; \"MEMBER_OF\"]\n"
        "}\n";

    impulse_vm_state_t state = {0};
    state.query_context = impulse_vm_context_create(snap);

    impulse_vm_status_t status = impulse_compile_and_execute(
        snap,
        impk_script,
        IMPULSE_LANG_IMPK,
        &state,
        /*input_seed=*/ 42
    );

    impulse_vm_context_destroy((impulse_vm_context_t*)state.query_context);
    ```

=== "Java 25 (Pre-Compiled `.impb` or `OP_MXV`)"
    ```java
    // Execute a pre-compiled .impb program produced by `impulse compile` + `impulse assemble`
    byte[] bytecodeBytes = Files.readAllBytes(Path.of("algorithm.impb"));

    try (Arena arena = Arena.ofConfined()) {
        MemorySegment prog = arena.allocateFrom(ValueLayout.JAVA_BYTE, bytecodeBytes);
        int instructionCount = (int) (bytecodeBytes.length / VmStateLayout.INSTRUCTION_SIZE_BYTES);

        Object result = ImpulseVmInterpreter.execute(prog, instructionCount, graph, 0, arena);
    }
    ```

!!! note
    **Java `@ImpKQuery` Annotation Roadmap**: Direct in-process Java compilation of `.impk` scripts and `@ImpKQuery` annotations is scheduled for `v1.0.0` (currently supported natively in the C/C++20 kernel via `IMPULSE_LANG_IMPK` and in the `impulse compile` CLI).
