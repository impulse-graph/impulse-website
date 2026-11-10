# Compiler Pipeline & ImpulseVM Execution

Every query in **Impulse Graph Engine**—whether written in the Fluent API, openCypher, Google CEL, ImpLog (Datalog), or ImpK (GraphBLAS)—compiles through a single multi-pass pipeline into **64-bit `impOps` bytecode** and executes on **`ImpulseVM`**.

```mermaid
flowchart LR
    FE["1. Query Frontends\nFluent API • openCypher\nCEL • ImpLog • ImpK"] --> IR["2. ImpScheme IR (.impscm)\nHomoiconic S-Expr AST"]
    IR --> S1["3. Stage 1 Optimizer\nSnapshot-Agnostic\nConstant Folding & Algebra"]
    S1 --> S2["4. Stage 2 Optimizer\nSnapshot-Bound\nZone Maps, Fusion, Push/Pull"]
    S2 --> VM["5. ImpulseVM (R0..R63)\n64-Bit impOps (.impb)\nJava 25 JIT & C++20 SIMD"]
```

---

## 1. The Immutable Snapshot Optimization Thesis

In traditional relational and graph databases, query optimizers operate under **probabilistic uncertainty**: because the database is mutating concurrently, the planner relies on sampled histograms and must compile conservative execution plans.

> **Because an `.imps` snapshot is 100% immutable, every structural statistic—domain cardinalities ($N_d$), degree bounds, relation multiplicities ($1:1, 1:N, N:1$), null counts, and per-attribute `[min, max]` Zone Maps—is exact.**

Binding a query AST to an `.imps` snapshot turns heuristic query planning into **deterministic algebraic simplification**.

### Two-Stage Optimization Pipeline

To support sub-microsecond plan caching across Blue/Green snapshot swaps, optimization is split into two stages:

| Stage | When It Runs | Key Optimization Passes | Concrete Impact |
| :--- | :--- | :--- | :--- |
| **Stage 1: Snapshot-Agnostic** | Once when a query is registered or parsed | • **AstNormalizationPass & ParameterBindingPass**<br>• **PreBindValidator & CelPredicateFlatteningPass**<br>• **ConstantFoldingPass & MonotonicHomomorphismPass**<br>• **ZoneMapPruningPass & AlgebraicTypeInferencePass** | • Flattens and normalizes CEL ASTs into canonical forms.<br>• Folds constant math and inverts monotonic expressions ($\sqrt{x} < c \implies x < c^2$).<br>• Commutes monotonic functions across reductions ($\max(f(X)) \to f(\max(X))$).<br>• Evaluates constant predicates and zone-map bounds when snapshot statistics are supplied. |
| **Stage 2: Snapshot-Bound** | When binding a query to a specific `.imps` file (`< 2 µs`) | • **BindTimeValidator & DirectionSelectionPass**<br>• **FilterPushdownPass & InjectiveDeduplicationBypassPass**<br>• **KernelFusionPass (`OP_CSR_WALK_2HOP`)**<br>• **VirtualRelationDecompositionPass**<br>• **PhysicalBindingPass & RegisterAllocationPass** | • Decomposes virtual relations and prunes non-matching partitions.<br>• Validates relation schema and chooses traversal direction (CSR vs. CSC).<br>• Pushes edge and node filters directly into traversal walk shaders.<br>• Bypasses deduplication on $1:N$ injective relations (`isInjective()`).<br>• Fuses low-multiplicity 2-hop CSR walks into `OP_CSR_WALK_2HOP`.<br>• Assigns 640-byte VM register frames (`R0`..`R63`). |

### Inspecting Bytecode Disassembly (`.impas`)

Any compiled query can be disassembled into canonical human-readable **ImpAsm (`.impas`)** text assembly (via `ImpAsmDisassembler.disassemble(program)` in Java or `impulse disassemble` in the CLI):

```impas
.version 0.9.0
.instructions 4

  0x0000: OP_CSC_WALK       flags=0x03, dst=R1, payload=0x00240000 ; Walk src=R0 -> dst=R1 via rel[36] [seed-inlined]
  0x0001: OP_CSR_WALK       flags=0x01, dst=R0, payload=0x00080001 ; Walk src=R1 -> dst=R0 via rel[8]  [early-exit]
  0x0002: OP_COLLECT_BITSET flags=0x00, dst=R0, payload=0x00000000 ; Materialize surviving bitset in R0
  0x0003: OP_HALT           flags=0x00, dst=R0, payload=0x00000000 ; Execution complete
```

---

## 2. Inside `ImpulseVM`: Registers, JIT & Parallelism

Once emitted as fixed 8-byte `impOps` instructions (`opcode[8] | flags[8] | dst_reg[16] | payload[32]`), the program executes on **`ImpulseVM`**:

### 2.1 640-Byte Cache-Aligned Register Frame (`R0`..`R63`)
Inspired by Lua 5+ and LuaJIT, `ImpulseVM` is a **register-based virtual machine** rather than a stack machine. Source and destination registers (`R0`..`R63`) are encoded directly in each 64-bit instruction word, eliminating `PUSH`/`POP` traffic and keeping the entire VM execution state (`impulse_vm_state_t`) inside a single **640-byte frame (10 CPU cache lines)** that stays resident in L1 cache.

### 2.2 Pure Java 25 `MethodHandle` JIT Combinators
In the Pure Java 25 engine (`impulse-graph-java`), queries do not sit inside a slow bytecode `switch` loop when evaluating per-edge or per-node filter/projection shaders (`OP_CSR_WALK_STREAM`, `OP_CSC_WALK_STREAM`):

* `ImpulseMethodHandleCompiler` and `ShaderCompiler` translate `impOps` instructions and CEL predicates into composable trees of `java.lang.invoke.MethodHandle` combinators (`MethodHandles.insertArguments`, `foldArguments`, `guardWithTest`).
* The JVM's **C2 JIT compiler** constant-folds the register offsets and inlines the entire chain of shader operations into a single contiguous block of native machine code with **zero virtual method or interpreter dispatch overhead**.
* Two-stage AST optimization and `MethodHandle` JIT tree generation complete in microsecond latencies on modern server hardware with zero runtime bytecode switch interpretation.

### 2.3 Single-Threaded (High-QPS) vs. Multi-Threaded (Batch Analytics) Execution
`ImpulseVM` supports two complementary concurrency modes depending on your workload:

1. **Inter-Query Concurrency (Default for Microservices & APIs)**:
   * Each query executes single-threaded (`threads = 1`) in its own isolated 640-byte register frame and caller buffer over the shared `mmap` snapshot.
   * Because `threads == 1` is checked once outside the inner opcode loop, the VM executes non-atomic bitset writes (`w_dst |= mask`), avoiding hardware `LOCK` prefix overhead while allowing thousands of concurrent gRPC/HTTP requests to scale linearly across all CPU cores.
2. **Intra-Instruction Parallelism (For Massive Batch Analytics & GNNs)**:
   * For analytical workloads over multi-billion-edge graphs (PageRank, Connected Components, full-graph BFS), configuring `OP_SET_MAX_DOP` (`0x75`) or the `IMPULSE_MAX_DOP` environment variable parallelizes individual `impOps` kernels across cores using OpenMP (`#pragma omp parallel for`) in C++20 and parallel vector partitions in Java 25.

---

## Next Steps

* **[Mathematical & GraphBLAS Foundations](../academic.md)**: Formal semiring algebra, Kleisli composition, $1:1 / 1:N / N:1$ multiplicity proofs, and the CSR/CSC/COO analytical cost model.
* **[ImpulseVM & `impOps` ISA Specification](../reference/spec/vm-specification.md)**: Normative bytecode instruction set reference (`0x00`..`0xCB`).
