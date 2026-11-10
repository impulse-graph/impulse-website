# ImpK Specification (`.impk`)

> **Architectural Role**: **Primary User Frontend DSL (GraphBLAS & Vector Math)**
>
> **ImpK** (`.impk`) is the high-level array and vector domain-specific language for the **Impulse Graph Engine**, designed for GraphBLAS matrix mathematics, PageRank, connected components, triangle counting, and SIMD vector operations. It compiles down to `ImpScheme` (`.impscm`) intermediate representation before being emitted as `ImpulseVM` bytecode (`impOps`).

---

## 1. Syntax & Core Primitives

ImpK treats graph relations as sparse adjacency matrices, node frontiers as dense vectors or bitsets, and traversals as algebraic matrix-vector multiplications. The syntax consists of declarative statement assignments evaluated in sequence.

### Statement Operations

| ImpK Statement | Operation | Lowered `impOps` Bytecode |
| :--- | :--- | :--- |
| `y = A * x` | Semiring Matrix-Vector Product (SpMV) | `OP_MXV` (`0x41`) |
| `z = x + y` | Element-wise Vector Addition | `OP_EWISE_ADD` (`0x43`) |
| `z = x * y` | Element-wise Vector Multiplication | `OP_EWISE_MULT` (`0x44`) |
| `p = pagerank(A, x, 0.85)` | PageRank ($k$ iterations, damping $\alpha$) | `OP_MXV` + vector scale & bias loop |
| `cc = afforest(A)` | Afforest / FastSV Connected Components | `OP_CC_AFFOREST` (`0x40`) |
| `d = degree(A)` | Out-Degree Vector Projection | `OP_DEGREE_STREAM` (`0x4A`) |
| `top = topk(v, 10)` | Top-$K$ Value & Node Selection | `OP_TOPK` (`0x34`) |

---

## 2. Multi-Lane Bit-Sliced SpMM & Vector Operations

ImpK provides first-class operations for 64-lane bit-sliced contingency screening (`0xC0`..`0xC9`) and hybrid vector search (`0xCA`..`0xCB`):

```
// 1. Seed up to 64 independent query lanes
F0 = lane_seeds([0, 1])

// 2. Configure counterfactual edge trips for contingency screening
F1 = lane_edge_mask(A, [12, 45])

// 3. Bit-sliced forward SpMM walk across relation A
F2 = lane_spmm(A, F0, true)

// 4. Reverse (CSC) bit-sliced SpMM walk
F3 = lane_spmm_csc(A, F2, false)

// 5. Evaluate quorum across surviving lanes (>= 2 lanes active)
B = lane_quorum(F3, 2)

// 6. Vector ANN search and exact dot-product reranking
cands = ann_search([0.15, -0.42, 0.88], 10, 0, false)
scores = rerank_dot(cands, [0.15, -0.42, 0.88], 0, cosine)
```

---

## 3. Code Example: PageRank in ImpK

```
// PageRank with damping factor 0.85 and uniform initial distribution
x = uniform_vector(1.0)
p = pagerank(FOLLOWS, x, 0.85)
top10 = topk(p, 10)
```

---

## 4. Compiling ImpK via CLI

Using the `impulse-graph` CLI toolchain:

```bash
# 1. Compile .impk source directly into canonical .impas assembly text
impulse-graph compile algorithm.impk -o algorithm.impas

# 2. Assemble text assembly into binary bytecode (.impb)
impulse-graph assemble -i algorithm.impas -o algorithm.impb

# 3. Execute compiled bytecode program against a snapshot
impulse-graph run --snapshot production.imps --bytecode algorithm.impb
```

---

## 5. Executing `.impk` Programs from Host SDKs

In-process compilation and execution of `.impk` scripts is supported directly through the C-ABI (`IMPULSE_LANG_IMPK`), C++20 `impulse::impk::ImpKCompiler`, and Java 25 `ImpKCompiler`:

=== "Java 25 (`ImpKCompiler`)"
    ```java
    // Compile and execute ImpK scripts directly in-process
    String script = "y = FOLLOWS * x\n";
    CompiledQuery query = ImpKCompiler.compileToExecutable(script, snapshot, arena);
    QueryResult result = query.execute(inputNodeId);
    ```

=== "C / C++20 (`impulse_compile_and_execute`)"
    ```c
    #include "impulse_vm.h"

    const char* impk_script = "y = FOLLOWS * x\n";

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

!!! note "Compile-Time Annotations Roadmap"
    Direct script compilation via `ImpKCompiler.compileToExecutable(...)` is available today. Compile-time Java source code annotations (`@ImpKQuery`) and macro metaprogramming frontends are scheduled for the `v1.0.0` release.
