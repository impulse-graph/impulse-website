# Impulse Graph Engine Domain-Specific Languages (DSLs)

The **Impulse Graph Engine** compiler suite (`impulse-graph-tooling`) features a multi-frontend compiler pipeline designed to target the low-level **ImpulseVM bytecode ISA (`impOps`)** via intermediate S-Expression IR (`ImpScheme`).

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ ImpK (Array)   │  │ ImpLog (Datalog) │  │ ImpScheme (S-Expr)│
│ `g @[f; rel]`    │  │ `head :- body`   │  │ `(g:walk-csr ...)`│
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │ (Translates to ImpScm IR)
                               ▼
            ┌──────────────────────────────────────────────┐
            │ ImpScm (Universal Compiler IR)         │
            │   • Vector Fusion Pass (&~ -> AND_NOT)       │
            │   • Direction Selection (CSR vs CSC)         │
            │   • Linear Scan Reg Allocator (R0..R63)      │
            └──────────────────────┬───────────────────────┘
                                   │
                                   ▼
            ┌──────────────────────────────────────────────┐
            │ canonical .impas Emitter              │
            │ OP_CSR_WALK, OP_ROARING_BITMAP_AND_NOT    │
            └──────────────────────────────────────────────┘
```

## Available Language Dialects & Compiler Hierarchy

1. **[Google CEL (`.cel`)](cel.md)**: **Universal Expression Engine (Filters & Projections)**. Standardized expression language for boolean graph filters (`WHERE`), calculated column projections (`RETURN`), ReBAC security policies, and 46 vector math functions with automated constant folding.
2. **[ImpK (`.impk`)](impk.md)**: **Primary User Frontend DSL (Array/Vector)**. High-level language targeting GraphBLAS matrix math, PageRank, connected components, and SIMD vector operations.
3. **[ImpLog (`.implog`)](implog.md)**: **Primary User Frontend DSL (Datalog/Logic)**. High-level declarative language targeting Relationship-Based Access Control (ReBAC / Zanzibar), transitive reachability, and security rules.
4. **[ImpScheme (`.impscm`)](impscm.md)**: **Internal Compiler IR & Low-Level Macro Target**. Homoiconic S-Expression AST compiler bus between high-level frontends (`Fluent API`, `openCypher`, `CEL`, `ImpK`, `ImpLog`) and the `impOps` bytecode emitter. Exposed for compiler pass debugging and low-level macro authoring, though most users should prefer the Fluent API or `openCypher`.
5. **ImpAsm (`.impas`)**: **Canonical Assembly Text Format**. Human-readable assembly text representation of `ImpulseVM` registers (`R0`..`R63`).
6. **impOps (`.impb`)**: **Virtual Machine Bytecode ISA**. Register-based opcode instruction set architecture (opcodes `0x01`..`0x6A`). Formally specified in the core engine spec.


## Virtual Relations & Compiler Optimization Passes

### Virtual Relations (Synthetic Views)
In Impulse Graph Engine, physical relations are zero-copy CSR/CSC binary arrays stored in `.imps` snapshot files. **Virtual Relations** are non-materialized, dynamically evaluated relation views defined declaratively at the DSL level:
* **ImpLog Virtual Relations**: Defined via Datalog rules without physical `.decl` tables (e.g. `member(U, G2) :- member(U, G1), group_parent(G1, G2)`).
* **ImpK Virtual Relations**: Functional matrix transformations such as transposed matrices (`G.transpose("FOLLOWS")`), filtered masks (`G.walk_filtered("FOLLOWS", ACTIVE)`), or combined relation paths.
* **ImpScheme Macro Expansion**: Lowered into homoiconic S-Expressions that expand directly into zero-copy `ImpulseVM` vector walks.

### Compiler Optimization Passes
1. **Partition Elimination & Dead Branch Pruning (`passes::partition_elimination`)**:
   - **Empty Set Pruning**: Rewrites `(g:walk-csr g (bitset:empty) rel)` $\to$ `(bitset:empty)`, eliminating unneeded graph traversals over empty input frontiers.
   - **Domain Disjoint Elimination**: Prunes relation walks when source/target domain boundaries ($D_{src} \cap D_{tgt} = \emptyset$) cannot produce valid edges.
2. **Vector & Bitset Opcode Fusion (`passes::vector_fusion`)**:
   - Fuses `(bitset:and a (bitset:not b))` into single SIMD zero-copy `(bitset:and-not a b)` (`OP_ROARING_BITMAP_AND_NOT`).
   - Fuses `(bitset:and (g:walk-csr g f rel) mask)` into `(g:walk-csr-filtered g f rel mask)` (`OP_CSR_WALK_FILTERED`).
3. **Linear Scan Register Allocation (`regalloc::linear_scan`)**:
   - Maps AST variable symbols into physical 64-bit hardware registers (`R0`..`R63`) with zero runtime stack frame allocations.
