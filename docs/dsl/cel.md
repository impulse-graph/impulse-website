# Google CEL for Filters & Projections

The **Impulse Graph Engine** incorporates an embedded, zero-dependency **Google Common Expression Language (CEL)** compiler. CEL serves as the universal expression engine across all query frontends (Cypher, ImpK, ImpLog, and Fluent Builder APIs), seamlessly powering both **predicate filtering (`WHERE`)** and **columnar transformations / projections (`RETURN` / `SELECT` / `YIELD`)**.

---

## 1. Architectural Role: Unified Filter & Projection Engine

CEL decouples complex boolean logic, transcendental math, and attribute transformations from traversal topology.

```
                       ┌───────────────────────────────────────────────┐
                       │ Google CEL Expression Engine         │
                       └───────────────────────┬───────────────────────┘
                                               │
                      ┌────────────────────────┴────────────────────────┐
                      ▼                                                 ▼
        ┌───────────────────────────┐                     ┌───────────────────────────┐
        │ PREDICATE ROLE (Filter)  │                     │ PROJECTION ROLE (Return)  │
        │ • Return Type: Boolean    │                     │ • Return Type: Scalar/Vec │
        │ • Target: TYPE_BITSET     │                     │ • Target: Vector Buffers  │
        │ • Vectorized bitmasking   │                     │ • Direct Apache Arrow map │
        └─────────────┬─────────────┘                     └─────────────┬─────────────┘
                      │                                                 │
                      ▼                                                 ▼
        ┌───────────────────────────┐                     ┌───────────────────────────┐
        │ Filters which nodes &   │                     │ Computes calculated       │
        │ edges survive traversal │                     │ columns & transformations │
        │ (e.g., edge.weight > 0) │                     │ (e.g., sqrt(w)*10 + bias) │
        └───────────────────────────┘                     └─────────────┬─────────────┘
                                                                        │
                                                                        ▼
                                                          ┌───────────────────────────┐
                                                          │ Zero-Copy Apache Arrow    │
                                                          │ RecordBatches / C-ABI Vec │
                                                          └───────────────────────────┘
```

* **Predicate Mode (`WHERE`)**: Evaluates boolean expressions into off-heap bitmasks (`TYPE_BITSET_HANDLE`), driving SIMD frontier pruning (`OP_NODE_FILTER`, `OP_CSR_WALK_FILTERED`).
* **Projection Mode (`RETURN`)**: Evaluates numeric, string, temporal, and list expressions over traversed nodes/edges, producing 128-byte hardware-aligned contiguous off-heap vector buffers that map 1-to-1 to Apache Arrow RecordBatches.

---

## 2. Language Features & Standard Library

### 2.1 Operators & Precedence
CEL follows standard C/Java/Python operator precedence, fully implemented via an embedded zero-allocation Pratt parser:

| Category | Operators | Examples |
| :--- | :--- | :--- |
| **Arithmetic** | `+`, `-`, `*`, `/`, `%` | `edge.weight * 100.0 + dest.priority` |
| **Comparison** | `==`, `!=`, `<`, `<=`, `>`, `>=` | `dest.region == "us-east" && edge.miles < 500.0` |
| **Logical** | `&&`, `\|\|`, `!` | `!resource.is_locked && (user.is_admin \|\| user.level > 5)` |
| **Conditional** | `? :` (Ternary) | `edge.active ? dest.score * 1.5 : 0.0` |
| **Member Access** | `.field` | `src.latitude`, `dest.metadata.tenant_id` |
| **List Literals** | `[elem1, elem2, ...]` | `[1, 2, 3, 5]` |

### 2.2 Built-in Vector Math Functions (46 Functions)
Impulse Graph exposes a comprehensive analytical math library directly in CEL, compiling down to hardware-accelerated SIMD kernels:

* **Algebraic & Power**: `abs`, `sqrt`, `rsqrt`, `cbrt`, `pow(x, y)`, `hypot(x, y)`, `lerp(a, b, t)`, `clamp(x, min, max)`, `copysign`, `fmod`.
* **Exponential & Logarithmic**: `exp`, `exp2`, `exp10`, `expm1`, `log`, `log2`, `log10`, `log1p`.
* **Trigonometric & Hyperbolic**: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sinc`, `sinh`, `cosh`, `tanh`, `asinh`, `acosh`, `atanh`.
* **Neural Activations**: `relu`, `leaky_relu`, `sigmoid`, `gelu`, `silu`, `softplus`.
* **Rounding & Floating Point**: `floor`, `ceil`, `trunc`, `round`, `erf`, `erfc`, `lgamma`.
* **Bitwise & Binary**: `popcount`, `clz`, `ctz`, `rotl`, `rotr`.

### 2.3 Floating-Point Assertions & Safe Math
To guarantee deterministic traversal without floating-point crashes or unchecked `NaN` propagation:

* `safeDiv(numerator, denominator, fallback)`: Performs zero-division protected division; returns `fallback` if denominator is $0.0$ or non-finite.
* `isNan(x)` / `isInf(x)` / `isFinite(x)`: Boolean predicates for IEEE 754 floating-point validation.
* Compiles to `OP_ASSERT_FINITE` (`0x2A`) in ImpulseVM, trapping illegal calculations with `IMPULSE_VM_ERR_FLOATING_POINT`.

### 2.4 Temporal & DateTime Expressions
Native ISO-8601 timestamps and duration arithmetic:

```cel
now() - edge.created_at > duration("30d") ? 0.0 : edge.weight * exp(-edge.decay_rate)
```

---

## 3. Zero-Dependency AST Optimizer (`AstOptimizer`)

Before bytecode generation, all CEL expressions pass through the **`AstOptimizer`** pass.

```
       CEL Source String
              │
              ▼
   Zero-Allocation Pratt Parser
              │ (AST)
              ▼
    AstOptimizer Pipeline
    ├── Multi-Type Constant Folding (Integer, Float, Math, Logic)
    ├── Algebraic Identity Reduction (x * 1, x + 0, x * 0, !(!x))
    └── Dead Branch Elimination (true ? A : B -> A)
              │ (Optimized AST)
              ▼
      ImpScheme Compiler
              │ (Homoiconic S-Expressions)
              ▼
      ImpulseVM Bytecode (impOps)
```

### Optimization Examples

| Unoptimized CEL Expression | Optimized ImpScheme S-Expression IR | Optimization Applied |
| :--- | :--- | :--- |
| `2 + 3 * 4` | `14` | Integer constant folding |
| `x * 1 + 0` | `x` | Multiplicative & additive identity reduction |
| `!(!edge.valid)` | `(get-attr edge "valid")` | Double negation elimination |
| `true ? src.score : dest.score` | `(get-attr src "score")` | Dead branch pruning |
| `sqrt(64.0) + pow(2.0, 3.0)` | `16.0` | Transcendental math constant folding |
| `(10.0 > 0.0 && !false) ? sqrt(64.0) * edge.weight + (0.0 + edge.bias * 1.0) : -1.0` | `(+ (* 8.0 (get-attr edge "weight")) (get-attr edge "bias"))` | Full multi-pass algebraic simplification |

---

## 4. Query Examples: Filters vs Projections

### Example 1: Cypher Traversal with CEL Filter & Projection
```cypher
MATCH (src:City)-[e:FLIGHT]->(dest:City)
WHERE e.distance_miles < 2000.0 && !isNan(e.friction) && dest.region == "EU"
RETURN 
  dest.name,
  e.distance_miles * 1.60934 AS distance_km,
  safeDiv(e.price, e.distance_miles, 0.0) AS cost_per_mile,
  clamp(1.0 - (dest.congestion / 100.0), 0.0, 1.0) AS efficiency_score
```

### Example 2: ReBAC Fine-Grained Authorization Policy (ImpLog / Datalog)
```implog
allow(User, Action, Resource) :- 
    user_tenant(User, T),
    resource_tenant(Resource, T),
    eval_cel("!resource.is_locked && (user.is_admin || request.action in resource.allowed_actions)").
```

### Example 3: GNN Node Feature Fusion & Decay Scoring (ImpK / Vector)
```cel
(edge.weight > 0.0) ? 
  clamp(
    safeDiv(sqrt(edge.weight * 100.0), hypot(src.x - dest.x, src.y - dest.y) + 0.001, 0.0) * (1.0 + sigmoid(dest.rating - src.rating)),
    0.0, 
    1000.0
  ) : 
  -1.0
```

---

## 5. Empirical Compiler Performance Benchmarks

Below are empirical execution metrics measured on physical hardware via the tight-loop benchmark harness (`bench_cel_compiler.cpp`):

| Scenario | AST Leaves | AST Depth | Parse Latency | Optimizer Latency | IR Lowering | Total Compile Time | Compiles / Sec |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Simple Filter Predicate** | 4 | 4 | **4.26 $\mu\text{s}$** | 3.15 $\mu\text{s}$ | 0.79 $\mu\text{s}$ | **8.34 $\mu\text{s}$** | **119,943 / sec** |
| **ReBAC Security Policy Rule** | 6 | 6 | **8.40 $\mu\text{s}$** | 6.28 $\mu\text{s}$ | 1.31 $\mu\text{s}$ | **16.45 $\mu\text{s}$** | **60,784 / sec** |
| **Analytical Scoring Formula** | 15 | 8 | **19.78 $\mu\text{s}$** | 14.83 $\mu\text{s}$ | 5.07 $\mu\text{s}$ | **41.35 $\mu\text{s}$** | **24,185 / sec** |
| **Pathological 39-Leaf Expression** | 39 | 12 | **56.21 $\mu\text{s}$** | 41.89 $\mu\text{s}$ | 12.96 $\mu\text{s}$ | **116.30 $\mu\text{s}$** | **8,598 / sec** |
| **Extreme 101-Leaf Generated Expression** | 101 | 26 | **142.59 $\mu\text{s}$** | 109.68 $\mu\text{s}$ | 33.55 $\mu\text{s}$ | **287.91 $\mu\text{s}$** | **3,473 / sec** |

* **Zero-Allocation**: Lexing and parsing use zero dynamic allocations for identifiers and operators.
* **L1 Cache Friendly**: Standard expressions compile in under $10\,\mu\text{s}$, producing compact bytecode suited for zero-overhead query compilation.
