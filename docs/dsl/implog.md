# ImpLog Specification (`.implog`)

> **Architectural Role**: **Primary User Frontend DSL (Datalog & Logic)**
>
> **ImpLog** (`.implog`) is the high-level declarative Datalog logic domain-specific language for the **Impulse Graph Engine**, designed for fine-grained Relationship-Based Access Control (ReBAC / Zanzibar), transitive reachability, and security rule reasoning. It compiles down to `ImpScheme` (`.impscm`) intermediate representation before being emitted as `ImpulseVM` bytecode (`impOps`).


---

## 1. Syntax & Core Primitives

ImpLog specifies computation through **Facts** and **Rules** (`head :- body`).

### Language Directives & Clauses

| ImpLog Syntax | Meaning | Compiled `ImpulseVM` Engine Behavior |
| :--- | :--- | :--- |
| `.decl rel_name(Type1, Type2)` | Declaration of relation schema | Verifies target snapshot relation metadata. |
| `head(X, Z) :- rel1(X, Y), rel2(Y, Z)` | Horn Clause Rule | Traverses 2-hop relation path via `OP_CSR_WALK`. |
| `head(X, Y) :- rel(X, Y), !visited(Y)` | Negation Clause | Performs fused `OP_ROARING_BITMAP_AND_NOT` difference. |

---

## 2. Code Example: ReBAC Transitive Group Membership & Authorizations

```prolog
// ReBAC Authorization Policy in ImpLog (.implog)
.decl member(User, Group)
.decl group_parent(Group, ParentGroup)
.decl can_view(User, Document)

// Base Case: Direct Group Membership
member(U, G) :- direct_member(U, G).

// Transitive Membership: User is in G2 if member of G1 and G1 is parent of G2
member(U, G2) :- member(U, G1), group_parent(G1, G2).

// Authorization Rule: User can view Document if member of a group with viewer rights
can_view(U, D) :- member(U, G), doc_viewer(G, D), !revoked(U).
```

---

## 3. Semi-Naive Fixpoint Evaluation & Roaring Bitsets

When the `ImpLog` compiler processes recursive Datalog rules, it translates them into **Semi-Naive Fixpoint Iteration loops** backed by off-heap Roaring Bitsets:

1. **Delta Set Expansion**: `OP_CSR_WALK` advances the new delta set.
2. **Set Difference**: `OP_ROARING_BITMAP_AND_NOT` removes previously visited nodes ($\Delta_{k+1} = \text{Expanded} \setminus \text{Visited}$).
3. **Set Union**: `OP_ROARING_BITMAP_OR` updates the total visited set ($\text{Visited} = \text{Visited} \cup \Delta_{k+1}$).
4. **Termination Check**: `OP_BITSET_COUNT` checks if $\Delta_{k+1}$ is empty to exit loop.

---

## 4. Compiling ImpLog

Using the `impulse-graph` CLI toolchain:

```bash
# 1. Compile .implog source directly into canonical .impas assembly text
impulse compiler compile authz.implog -o authz.impas

# 2. Inspect intermediate ImpScheme AST S-Expressions
impulse compiler compile authz.implog --emit-ir

# 3. Assemble text assembly into binary bytecode (.impb)
impulse compiler assemble authz.impas -o authz.impb

# 4. Execute query program against snapshot
impulse run --snapshot production.imps --bytecode authz.impb --input-val 1042
```
