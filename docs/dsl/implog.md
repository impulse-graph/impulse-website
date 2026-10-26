# ImpLog Specification (`.implog`)

**ImpLog (`.implog`)** is the declarative **Datalog & Logic DSL** for **Impulse Graph Engine**, designed for fine-grained Relationship-Based Access Control (ReBAC / Zanzibar), transitive reachability, security policy verification, and recursive graph analytics.

Unlike traditional query languages that struggle with unbounded recursion or duplicate path explosions, ImpLog evaluates Horn clauses (`Head :- Body`) using **set-theoretic semi-naïve fixed-point iteration** over off-heap bitsets, compiling directly to [`ImpScheme` IR](impscm.md) and `impOps` bytecode.

---

## 1. Syntax & Rule Primitives

ImpLog programs consist of **Relation Declarations (`.decl`)** and **Horn Rules (`Head :- Body.`)**:

```prolog
// 1. Typed Relation Declarations (mapped to .imps domains & relations)
.decl direct_member(user: User, group: Group)
.decl group_parent(child: Group, parent: Group)
.decl doc_owner(doc: Document, user: User)
.decl doc_editor(doc: Document, group: Group)
.decl doc_viewer(doc: Document, group: Group)
.decl account_locked(user: User)

// 2. Recursive Transitive Group Membership (Base + Inductive Step)
member(U, G)      :- direct_member(U, G).
member(U, Parent) :- member(U, Child), group_parent(Child, Parent).

// 3. Permission Derivation & Stratified Negation (!)
can_edit(U, D) :- doc_owner(D, U), !account_locked(U).
can_edit(U, D) :- member(U, G), doc_editor(D, G), !account_locked(U).
can_view(U, D) :- can_edit(U, D).
can_view(U, D) :- member(U, G), doc_viewer(D, G), !account_locked(U).
```

| ImpLog Construct | Syntax | Compiled `ImpulseVM` Execution |
| :--- | :--- | :--- |
| **Conjunction (Join)** | `H(X, Z) :- R1(X, Y), R2(Y, Z).` | Sequential CSR / CSC walk (`OP_CSR_WALK` / `OP_CSC_WALK`). |
| **Disjunction (Union)**| `H(X, Y) :- R1(X, Y) ; R2(X, Y).`| Bitset union (`OP_SET_UNION` / `OP_ROARING_BITMAP_OR`). |
| **Stratified Negation**| `H(X) :- R(X), !Banned(X).` | Bitset difference (`OP_ROARING_BITMAP_AND_NOT`). |
| **Lattice Aggregation**| `Dist(X, Y, min(C)) :- ...` | Monoidal in-flight reduction ($\bigoplus$) at target nodes. |
| **Bound Query Goal** | `?- can_view("usr_alice", Doc).` | **Magic Sets** rewrite pushing the seed binding to the root walk. |

---

## 2. Key Compiler Optimizations

1. **Semi-Naïve Fixed-Point Evaluation ($\Delta \mathcal{S}_{t+1} = \tau(\Delta \mathcal{S}_t) \setminus \mathcal{S}_{\text{visited}}$)**:
   * Recursive rules never re-traverse edges from already-visited nodes. Each iteration expands only the newly discovered delta frontier $\Delta \mathcal{S}_t$ and subtracts $\mathcal{S}_{\text{visited}}$ via a single `OP_ROARING_BITMAP_AND_NOT` instruction until $\Delta \mathcal{S}_{t+1} = \emptyset$.
2. **Magic Sets Goal-Directed Rewriting**:
   * When a query binds a specific entity (e.g., `?- can_view("usr_alice", Doc)`), the compiler rewrites the recursive rules so `ImpulseVM` expands **only the subgraph reachable from `"usr_alice"`** rather than materializing group memberships for every user in the snapshot.
3. **Lattice Datalog ($\text{Datalog}^\mathcal{L}$)**:
   * Supports monotonic semiring aggregations (`min`, `max`, `sum`) directly inside recursive rules (e.g., shortest-path distance `shortest(X, Y, min(C1 + C2))`) with guaranteed termination under Tarski's Fixed-Point Theorem.

---

## 3. Compiling & Running `.implog` Programs via CLI

```bash
# 1. Compile .implog rules into human-readable ImpAsm (.impas)
impulse compile authz.implog -o authz.impas

# 2. Inspect intermediate ImpScheme S-Expression IR (.impscm)
impulse compile authz.implog --emit-ir

# 3. Assemble into binary impOps bytecode (.impb) and run against a snapshot
impulse assemble authz.impas -o authz.impb
impulse run --snapshot production.imps --bytecode authz.impb --input-val 1042
```

---

## 4. Executing `.implog` Rules from Host SDKs

You can compile and execute `.implog` programs directly inside your application using the in-kernel compiler C-ABI (`IMPULSE_LANG_IMPLOG`), the C++20 `DatalogParser`, or by loading pre-assembled `.impb` bytecode in Java and polyglot SDKs:

=== "C / C++20 (`impulse_compile_and_execute`)"
    ```c
    #include "impulse_vm.h"

    const char* implog_rules =
        "member(U, G) :- direct_member(U, G).\n"
        "member(U, P) :- member(U, C), group_parent(C, P).\n"
        "?- member(1042, G).\n";

    impulse_vm_state_t state = {0};
    state.query_context = impulse_vm_context_create(snap);

    // Compile .implog -> ImpScheme -> impOps and execute in a single call
    impulse_vm_status_t status = impulse_compile_and_execute(
        snap,
        implog_rules,
        IMPULSE_LANG_IMPLOG,
        &state,
        /*input_seed=*/ 1042
    );

    impulse_vm_context_destroy((impulse_vm_context_t*)state.query_context);
    ```

=== "Java 25 / Polyglot (Pre-Compiled `.impb` Bytecode)"
    ```java
    // Pre-compile via CLI:
    //   impulse compile authz.implog -o authz.impas && impulse assemble authz.impas -o authz.impb
    byte[] bytecodeBytes = Files.readAllBytes(Path.of("authz.impb"));

    try (Arena arena = Arena.ofConfined()) {
        MemorySegment prog = arena.allocateFrom(ValueLayout.JAVA_BYTE, bytecodeBytes);
        int instructionCount = bytecodeBytes.length / VmStateLayout.INSTRUCTION_SIZE_BYTES;

        // Compile to fused MethodHandle chain or execute directly in ImpulseVmInterpreter
        MethodHandle mh = ImpulseMethodHandleCompiler.compile(prog, instructionCount);
        ImpulseBitSet permittedDocs = (ImpulseBitSet) mh.invokeExact(graph, (Object) 1042, arena);
    }
    ```

!!! note
    **Java `@ImpLogRule` Annotation Roadmap**: Direct in-process Java compilation of `.implog` strings and `@ImpLogRule` annotations is scheduled for `v1.0.0` (currently supported natively in the C/C++20 kernel via `IMPULSE_LANG_IMPLOG` and in the `impulse compile` CLI).
