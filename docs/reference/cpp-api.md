# C++20 API & VM Reference (`impulse-graph-core/impulse-cpp`)

This reference documents the **C++20 Native Engine, Optimizing Compiler, and Fluent VM API** located in `impulse-graph-core/impulse-cpp`.

!!! info "C-ABI Reference & Generated Doxygen HTML"
    * **Low-Level C-ABI Reference**: See the [**C-ABI Kernel & VM Reference (`c-abi.md`)**](c-abi.md) for all C structs, enums, prepared statements, and function signatures.
    * **Generated Doxygen HTML**: Browse the interactive header documentation at [**`/doxygen/index.html`**](/doxygen/index.html).

---

## 1. Library Architecture & Headers

`impulse-cpp` provides two programming layers:

1. **C-ABI Kernel Headers** (documented in detail in [C-ABI Reference](c-abi.md)):
   * `#include "impulse_format_v0_9.h"`: Binary Snapshot v0.9.0 POD structures and protocol enums.
   * `#include "impulse_graph.h"`: Snapshot `mmap` loader, catalog inspection, CSR/CSC buffer accessors, streaming writer, and delta compaction.
   * `#include "impulse_vm.h"`: Raw 64-bit VM opcode definitions (`impulse_instruction_t`), 640-byte state frame (`impulse_vm_state_t`), off-heap context (`impulse_vm_context_t`), in-kernel compiler C-ABI, and `impulse_stmt_t` prepared statements.
   * `#include "impulse_index.h"`: Secondary non-vector index builders and query evaluators.
   * `#include "impulse_simd.h"` & `#include "impulse_math_ops.h"`: Highway SIMD kernels and 54-function analytical vector math catalog.

2. **C++20 Fluent Query & Compiler Headers**:
   * `#include "impulse_vm_fluent.hpp"`: Type-safe fluent bytecode builder (`impulse::vm::QueryBuilder`), `CompiledQuery`, and `QueryResult`.
   * `#include "impulse_compiler.hpp"`: Zero-dependency C++20 multi-pass optimizing compiler (`impulse::compiler::CompilerOptions`, `ImpScmNode` AST hierarchy, kernel fusion, direction selection, and register ping-ponging).
   * `#include "impulse_cel.h"`: Pratt recursive-descent CEL parser, AST constant-folding optimizer (`impulse::cel::AstOptimizer`), and `ImpScheme` lowering (`impulse::cel::CelCompiler`).
   * `#include "impulse_cypher.hpp"`, `#include "impulse_impk.hpp"`, `#include "impulse_implog.hpp"`, `#include "impulse_impscm.hpp"`: C++20 DSL frontend parsers and lowering passes.

---

## 2. C-ABI Snapshot Engine (`impulse_graph.h`)

### Opening and Closing Snapshots
Impulse Graph opens `.imps` binary snapshot files direct-to-disk using zero-copy OS memory mapping (`mmap`). Physical memory usage remains $O(1)$ regardless of snapshot size.

```cpp
#include "impulse_graph.h"

impulse_status_t status = IMPULSE_OK;
impulse_snapshot_t* snapshot = impulse_snapshot_open("datasets/rbac.imps", &status);

if (status == IMPULSE_OK && snapshot) {
    uint32_t magic = impulse_snapshot_magic(snapshot);       // 0x494D5053 ("IMPS")
    uint16_t version = impulse_snapshot_version(snapshot);   // 9 (v0.9.0 spec)
    uint16_t domains = impulse_snapshot_domain_count(snapshot);
    uint16_t rels = impulse_snapshot_relation_count(snapshot);
}

// Always close to unmap physical memory regions
impulse_snapshot_close(snapshot);
```

### Direct Reachability & SIMD Neighbor Sampling
Query graph topology directly via lock-free C-ABI kernel calls:

```cpp
// 1. Direct edge reachability check (Relation 0, Source Node 0 -> Target Node 5)
bool connected = impulse_snapshot_is_reachable(snapshot, 0 /*relation_index*/, 0 /*src_id*/, 5 /*tgt_id*/);

// 2. SIMD Neighborhood Sampling (sample up to k=10 neighbors for node 0)
uint64_t src_nodes[] = { 0 };
uint64_t out_src[64];
uint64_t out_tgt[64];
size_t out_count = 0;

impulse_status_t st = impulse_snapshot_sample_neighbors(
    snapshot,
    0,            // relation_index
    src_nodes, 1, // seed nodes array & count
    10,           // k_samples (-1 for full expansion)
    1337,         // random seed
    out_src, out_tgt, 64, &out_count
);
```

---

## 3. C++20 Fluent Query API (`impulse::vm`)

The `impulse::vm::QueryBuilder` provides a type-safe, fluent interface for constructing, compiling, and executing Impulse VM queries without manually managing registers or writing raw 64-bit opcode instructions.

### Builder Core (`QueryBuilder`)

```cpp
#include "impulse_vm_fluent.hpp"

using namespace impulse::vm;

// Construct query builder
QueryBuilder builder;
builder.inputNode(0)                           // Set R0 as input seed node
       .walkEdge(0)                            // CSR walk on Relation 0
       .filterNode(101)                        // Apply node filter ID 101
       .repeat(3, [](QueryBuilder& q) {        // Fixed-count loop (3 iterations)
           q.walkEdge(1);
       })
       .collectBitset();                       // Materialize bitset output handle

// Compile into immutable bytecode pipeline
CompiledQuery query = builder.compile();
```

### Method Reference Table

| Category | Method | Description |
| :--- | :--- | :--- |
| **Inputs & Constants** | `.inputNode(dst_reg=0)` | Initialize input seed node parameter into `dst_reg` (`OP_INIT_INPUT_NODE`). |
| | `.inputSet(dst_reg=0)` | Initialize input seed set parameter into `dst_reg` (`OP_INIT_INPUT_SET`). |
| | `.loadConstInt(val, dst_reg=0)` | Load 64-bit integer constant into `dst_reg` (`OP_LOAD_CONST_INT`). |
| | `.loadConstFloat(val, dst_reg=0)` | Load 32-bit float constant into `dst_reg` (`OP_LOAD_CONST_FLOAT`). |
| | `.loadKeys(keys, count, dst_reg=0)` | Map string keys to dense node IDs (`OP_MAP_KEYS_TO_DENSE`). |
| **CSR/CSC Walks** | `.walkEdge(rel_id, flags=0)` | Perform lock-free CSR forward traversal over `rel_id` (`OP_CSR_WALK`). |
| | `.walkEdgeFiltered(rel_id, filter_id)` | CSR traversal filtered by attribute predicate (`OP_CSR_WALK_FILTERED`). |
| | `.walkEdgePredicate(rel_id, filter_id)` | CSR traversal with inline predicate evaluation (`OP_CSR_WALK_PREDICATE`). |
| | `.walkDegree(rel_id)` | Compute node output degree for `rel_id` (`OP_CSR_DEGREE`). |
| | `.walkReduceSum(rel_id, val_reg)` | CSR walk computing sum reduction of attributes (`OP_CSR_WALK_REDUCE_SUM`). |
| | `.walkCsc(rel_id)` | Perform bottom-up reverse CSC traversal (`OP_CSC_WALK`). |
| **Filters** | `.filterNode(filter_id)` | Filter current candidate set against node attribute `filter_id` (`OP_NODE_FILTER`). |
| | `.filterNodeStrPrefix(prefix)` | Filter nodes matching string prefix (`OP_NODE_FILTER_STR_PREFIX`). |
| **Set Algebra** | `.unionWith(src_reg)` | Set Union: $R_{\text{current}} = R_{\text{current}} \cup R_{\text{src}}$ (`OP_SET_UNION`). |
| | `.intersectWith(src_reg)` | Set Intersection: $R_{\text{current}} = R_{\text{current}} \cap R_{\text{src}}$ (`OP_SET_INTERSECT`). |
| | `.differenceWith(src_reg)` | Set Difference: $R_{\text{current}} = R_{\text{current}} \setminus R_{\text{src}}$ (`OP_SET_DIFFERENCE`). |
| | `.cardinality()` | Compute population count / cardinality (`OP_SET_CARDINALITY`). |
| **GraphBLAS & LinAlg**| `.matrixVectorMul(mat_reg, semiring)`| SpMV Matrix-Vector multiplication ($\mathbf{y} = \mathbf{A} \oplus.\otimes \mathbf{x}$) (`OP_MXV`). |
| | `.vectorMatrixMul(mat_reg, semiring)`| Vector-Matrix multiplication ($\mathbf{y}^T = \mathbf{x}^T \oplus.\otimes \mathbf{A}$) (`OP_VXM`). |
| | `.ewiseAdd(other_reg, binary_op)` | Elementwise addition of vector registers (`OP_EWISE_ADD`). |
| | `.ewiseMult(other_reg, binary_op)`| Elementwise multiplication of vector registers (`OP_EWISE_MULT`). |
| **Graph Analytics** | `.afforest()` | Afforest parallel Connected Components (`OP_CC_AFFOREST`). |
| | `.tcSweepBatch()` | Batch Transitive Closure sweep (`OP_TC_SWEEP_BATCH`). |
| | `.brandesForward()` / `.brandesBackward()` | Brandes Betweenness Centrality forward/backward passes (`OP_BRANDES_*`). |
| | `.deltaStepRelax(weight_reg)` | Delta-stepping Shortest Path edge relaxation (`OP_DELTA_STEP_RELAX`). |
| | `.sampleNeighbors(rel_id, k, seed)`| Zero-copy SIMD neighborhood sampler (`OP_SAMPLE_NEIGHBORS`). |
| | `.randomWalk(rel_id, steps, seed)`| SIMD Random Walk trajectory generator (`OP_RANDOM_WALK`). |
| | `.rebacCheck(permission_id)` | Fine-grained Relationship-Based Access Control check (`OP_REBAC_CHECK`). |
| **Control Flow** | `.repeat(count, body_fn)` | Repeat sub-builder pipeline `count` times using `OP_LOOP_DECR`. |
| | `.repeatUntilStable(body_fn)` | Repeat sub-builder pipeline until bitset set generation converges (`OP_STABLE_CHECK`). |
| | `.jmp(offset)` / `.jz(offset)` / `.jnz(offset)` | Direct, zero-jump, or non-zero jump branching instructions. |
| **Terminals** | `.collectBitset()` | Materialize result into an off-heap BitSet handle (`OP_COLLECT_BITSET`). |
| | `.collectArray()` | Collect dense node ID array (`OP_COLLECT_ARRAY`). |
| | `.collectValueMap()` | Materialize key-value projection map (`OP_COLLECT_VALUE_MAP`). |

---

## 4. Query Execution & Result Handling

### `CompiledQuery`
An immutable, reusable compiled bytecode executable.

```cpp
CompiledQuery query = builder.compile();

// Execute query against snapshot graph
QueryResult result = query.execute(snapshot, 42 /* input_param */);

if (result.isOk()) {
    std::cout << "Query executed cleanly. Result Register: R" << result.result_register << "\n";
    std::cout << "Result Type Tag: " << (int)result.result_type << "\n";
    std::cout << "Raw Register Value: " << result.raw_value << "\n";
}
```

### `QueryResult`
Type-safe result handle wrapper supporting scalar and off-heap handle unwrapping:

```cpp
// 1. Unwrap scalar integer / float / double
uint64_t intVal = result.asInt();
float floatVal  = result.asFloat();
double dblVal   = result.asDouble();

// 2. Query membership against context bitset (if result_type == TYPE_BITSET_HANDLE)
if (result.result_type == TYPE_BITSET_HANDLE) {
    bool hasAccess = result.testBitset(ctx, targetNodeId);
}
```

---

## 5. End-to-End C++ Application Example

```cpp
#include "impulse_graph.h"
#include "impulse_vm_fluent.hpp"
#include <iostream>

int main() {
    // 1. Open snapshot file via mmap
    impulse_status_t status = IMPULSE_OK;
    impulse_snapshot_t* snapshot = impulse_snapshot_open("datasets/rbac.imps", &status);
    if (status != IMPULSE_OK || !snapshot) {
        std::cerr << "Failed to open snapshot.\n";
        return 1;
    }

    // 2. Build ReBAC permission evaluation query using C++ Fluent API
    using namespace impulse::vm;
    CompiledQuery rebacQuery = QueryBuilder()
        .inputNode(0)                                  // User Node ID
        .walkEdge(0)                                   // userToGroup relation
        .repeatUntilStable([](QueryBuilder& q) {       // Transitive group inheritance
            q.walkEdge(1);                             // groupToGroup relation
        })
        .walkEdge(2)                                   // groupToRole relation
        .collectBitset()
        .compile();

    // 3. Execute compiled query
    impulse_vm_context_t* ctx = nullptr;
    QueryResult result = rebacQuery.execute(snapshot, 100 /* User 100 */, &ctx);

    if (result.isOk()) {
        std::cout << "[+] ReBAC Query executed successfully!\n";
        bool canAccessRole42 = result.testBitset(ctx, 42);
        std::cout << "    User 100 -> Role 42 permission: " 
                  << (canAccessRole42 ? "ALLOWED" : "DENIED") << "\n";
    }

    // 4. Cleanup off-heap handles and snapshot memory
    if (ctx) impulse_vm_context_destroy(ctx);
    impulse_snapshot_close(snapshot);
    return 0;
}
```

---

## 6. C++20 Optimizing Compiler & CEL AST (`impulse_compiler.hpp`, `impulse_cel.h`)

The C++20 compiler pipeline (`impulse::compiler`) and CEL parser/optimizer (`impulse::cel`) lower query expressions into `ImpScheme` S-expression IR and 8-byte `impOps` instructions:

```cpp
#include "impulse_compiler.hpp"
#include "impulse_cel.h"

// 1. Parse and constant-fold a CEL predicate expression
impulse::cel::Parser parser("node.age >= (18 + 3) && !(!node.active)");
auto raw_ast = parser.parse_expression();
auto opt_ast = impulse::cel::AstOptimizer::optimize(raw_ast);
std::string scm_ir = impulse::cel::CelCompiler::to_impscheme(opt_ast);

// 2. Configure C++20 compiler optimization passes
auto opts = impulse::compiler::CompilerOptions::default_options();
opts.enable_kernel_fusion = true;       // Fuse 2-hop CSR walks into OP_CSR_WALK_2HOP
opts.enable_direction_selection = true; // Select CSR vs CSC based on frontier density
opts.enable_register_ping_pong = true;  // Reuse R0 <-> R1 across sequential walks
```

---

## 7. Auto-Generating Full Doxygen HTML Documentation

All C-ABI headers (`impulse_format_v0_9.h`, `impulse_graph.h`, `impulse_vm.h`, `impulse_index.h`, `impulse_simd.h`, `impulse_math_ops.h`) and C++20 headers (`impulse_vm_fluent.hpp`, `impulse_compiler.hpp`, `impulse_cel.h`) contain Doxygen annotations.

Browse the hosted Doxygen HTML at [**`/doxygen/index.html`**](/doxygen/index.html), or generate it locally:

```bash
cd impulse-graph-core/impulse-cpp
doxygen Doxyfile
```

The output HTML site will be generated at `impulse-graph-core/impulse-cpp/build/docs/html/index.html`.

