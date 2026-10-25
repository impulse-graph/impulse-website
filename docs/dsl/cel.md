# Google CEL (Filters, Projections & SIMD Math)

**Impulse Graph Engine** embeds a zero-dependency **Google Common Expression Language (CEL)** compiler across all query frontends (Fluent API, openCypher, ImpLog, and ImpK), powering both **boolean predicate filtering (`WHERE` / `.filter`)** and **state / column projections (`.outWithState` / `.project` / `RETURN`)**.

---

## 1. Two Roles: Predicate Filters vs. Column Projections

1. **Predicate Mode (`.filter(...)`, `.out(rel, cel)`, `WHERE`)**:
   * Evaluates boolean expressions into off-heap bitmasks (`TYPE_BITSET_HANDLE`), driving SIMD frontier pruning (`OP_NODE_FILTER`, `OP_CSR_WALK_FILTERED`).
   * Example: `.out("TRANSFERRED_TO", "edge.amount >= 1000.0 && !tgt.is_frozen")`
2. **Projection Mode (`.outWithState(...)`, `.project(...)`, `RETURN`)**:
   * Evaluates numeric, temporal, or conditional expressions over active nodes/edges into 128-byte-aligned off-heap state vectors and Apache Arrow-compatible result columns.
   * Example: `.outWithState("FLIGHT", "state.min_cost:MIN = src.airport_fee + edge.price * 1.08")`

### Context Identifiers
* **`node.<attr>`**: Attribute on the active domain during an in-domain `.filter(...)` or `.project(...)`.
* **`src.<attr>`**: Source node attribute during an edge walk.
* **`edge.<attr>`**: Edge attribute on the traversed relation.
* **`tgt.<attr>` / `dest.<attr>`**: Target node attribute during an edge walk.
* **`state.<field>`**: Attached state vector field carried along the traversal.
* **`$param` / `@param`**: Bound runtime parameter.

---

## 2. Operators & Built-In SIMD Math Library

### 2.1 Operators
| Category | Operators | Examples |
| :--- | :--- | :--- |
| **Arithmetic** | `+`, `-`, `*`, `/`, `%` | `edge.weight * 100.0 + tgt.priority` |
| **Comparison** | `==`, `!=`, `<`, `<=`, `>`, `>=` | `tgt.region == "us-east" && edge.miles < 500.0` |
| **Logical** | `&&`, `\|\|`, `!` | `!tgt.is_locked && (src.is_admin \|\| src.level > 5)` |
| **Conditional** | `? :` (Ternary) | `edge.active ? tgt.score * 1.5 : 0.0` |
| **Membership** | `in`, `[a, b, c]` | `tgt.tier in [1, 2, 3]` |

### 2.2 Built-in Vector Math Functions
All math functions compile directly to hardware SIMD instructions (`impOps` vector math kernels):

* **Algebraic & Clamping**: `abs`, `min`, `max`, `sqrt`, `rsqrt`, `cbrt`, `pow(x, y)`, `hypot(x, y)`, `lerp(a, b, t)`, `clamp(x, min, max)`, `copysign`, `fmod`.
* **Exponential & Logarithmic**: `exp`, `exp2`, `exp10`, `expm1`, `log`, `log2`, `log10`, `log1p`.
* **Trigonometric & Hyperbolic**: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sinc`, `sinh`, `cosh`, `tanh`, `asinh`, `acosh`, `atanh`.
* **Neural Activations**: `relu`, `leaky_relu`, `sigmoid`, `gelu`, `silu`, `softplus`.
* **Rounding & Special**: `floor`, `ceil`, `trunc`, `round`, `erf`, `erfc`, `lgamma`.
* **Bitwise**: `popcount`, `clz`, `ctz`, `rotl`, `rotr`.
* **Safe Floating-Point Guards**:
  * `safeDiv(num, den, fallback)`: Returns `fallback` when `den == 0.0` or non-finite, preventing `NaN` propagation.
  * `isNan(x)`, `isInf(x)`, `isFinite(x)`: IEEE-754 classification predicates (backed by `OP_ASSERT_FINITE`).

---

## 3. Compile-Time Algebraic Optimization (`CelAstOptimizer`)

Before bytecode emission, CEL expressions are simplified by the Stage 1 optimizer in `< 10 µs`:

| Input CEL Expression | Simplified AST / `ImpScheme` Output | Optimization Applied |
| :--- | :--- | :--- |
| `2 + 3 * 4` | `14` | Constant folding |
| `x * 1 + 0` / `!(!edge.valid)` | `x` / `(get-attr edge "valid")` | Identity & double-negation elimination |
| `true ? src.score : tgt.score` | `(get-attr src "score")` | Dead branch elimination |
| `sqrt(edge.distance) < 10.0` | `edge.distance < 100.0` | Monotonic function inversion (eliminates `sqrt` in inner loop) |
| `node.age > 250` *(when Zone Map `age.max == 114`)* | `false` *(prunes entire walk)* | Stage 2 Zone Map contradiction pruning |
