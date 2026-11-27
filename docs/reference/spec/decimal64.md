# Fixed-Point Decimal Specification (`DECIMAL64` / `DECIMAL(P, S)`)

* **Specification Version**: `0.11.0` (`.imps` `0x000B`, `impOps` v0.11)
* **Physical Representation**: Signed 64-bit scaled integer (`int64_t`), value $= \text{unscaled} \times 10^{-S}$ (Parquet `DECIMAL64` layout)
* **Valid Range**: Precision $P \in [1, 18]$, scale $S \in [0, P]$, unscaled range $[-(10^P - 1), +(10^P - 1)]$

This document specifies the binary `.imps` storage layout, `ImpulseVM` v0.11 ISA instructions and trapping semantics, and `ImpScheme` / `CEL` compiler type coercion and boundary-folding rules for `DECIMAL64`.

---

## 1. `.imps` Binary Snapshot Layout

### 1.1 Attribute Type Codes (`0x0F` – `0x16`)

`DECIMAL64` extends the Section 2 `AttributeDescriptor.TypeCode` table (bits `0..6` = base type, bit `7` = `0x80` nullability flag):

| Base Code (`0x7F`) | Base Type Name | Non-Null Code | Nullable Code (`0x80`) | Dimension (`dim`) | Memory Layout |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `0x0F` | `BOOL` | `0x0F` | `0x8F` | $\ge 1$ | 1-bit packed `uint64_t[(K * dim + 63) / 64]` (128B-padded) |
| `0x10` | *(Reserved)* | — | — | — | Reserved to preserve `UINT* = INT* \| 0x10` bit symmetry |
| `0x11` | `UINT8` | `0x11` | `0x91` | $\ge 1$ | $1 \times \text{dim}$ bytes (`uint8_t`) |
| `0x12` | `UINT16` | `0x12` | `0x92` | $\ge 1$ | $2 \times \text{dim}$ bytes (`uint16_t`) |
| `0x13` | `UINT32` | `0x13` | `0x93` | $\ge 1$ | $4 \times \text{dim}$ bytes (`uint32_t`) |
| `0x14` | `UINT64` | `0x14` | `0x94` | $\ge 1$ | $8 \times \text{dim}$ bytes (`uint64_t`) |
| `0x15` | `DECIMAL64` | `0x15` | `0x95` | $\ge 1$ | $8 \times \text{dim}$ bytes (`int64_t` scaled by $10^S$) |
| `0x16` | `DECIMAL128` *(Reserved)* | `0x16` | `0x96` | $\ge 1$ | Reserved for future 16-byte signed `int128_t` ($19 \le P \le 38$) |

For nullable `DECIMAL64` (`0x95`), a 128-byte-padded validity bitmap (`uint64_t[(K + 63) / 64]`, `1` = valid, `0` = null) precedes the 128-byte-aligned `int64_t` payload array at `DataOffset`.

### 1.2 44-Byte `AttributeDescriptor` Encoding

`DECIMAL64` stores `(scale, precision)` inline in the existing fixed 44-byte `AttributeDescriptor` (`impulse_attribute_descriptor_v0_10_t`) with zero struct size change:

| Byte Offset | Field Name | C-ABI Type | Size | `DECIMAL64` (`0x15` / `0x95`) Semantics |
| :--- | :--- | :--- | :--- | :--- |
| `0x0004` | `TypeCode` | `uint8_t` | 1 Byte | `0x15` (non-null) or `0x95` (nullable) |
| `0x0005` | `Reserved1` | `uint8_t` | 1 Byte | `scale` $S \in [0, 18]$ ($S \le P$) |
| `0x0006` – `0x0007` | `Reserved2` | `uint16_t` | 2 Bytes | `precision` $P \in [1, 18]$ |

### 1.3 Lifecycle 1 Upfront Validation

When opening an `.imps` snapshot (Lifecycle 1), readers MUST validate every `DECIMAL64` attribute descriptor upfront before returning a snapshot handle:

* `1 <= precision <= 18`
* `0 <= scale <= precision`
* `data_bytes >= K * dim * 8` (plus 128B-aligned validity bitmap bytes when `0x95` is set)

Any violation fails fast at open time with `IMPULSE_ERR_INVALID_ARGUMENT`.

---

## 2. `ImpulseVM` v0.11 ISA (`DECIMAL64` Opcodes & Semantics)

With `DECIMAL64` enabled, the `impOps` v0.11 catalog comprises **80 active opcodes + `0xFF` (`OP_EXTENSION_PAYLOAD`)** and **486 active subops (487 total)**.

### 2.1 `0x15 OP_SCALAR_DECIMAL_ALU` (Pillar 1, 16 Subops)

* **Metadata**: `allowed_flags: 0x0`, `morsel_role: forbidden`, `banks: { dst: R, s1: R, s2: OPT_R, s3: OPT_R }`, `imm_layout: OPT_U16_PAIR`, `sets_vm_flags: [ZF, NF]`.

| Subop | Name | Semantics |
| :---: | :--- | :--- |
| `0` | `add_chk` | Checked 64-bit signed addition (`s1 + s2`); traps on overflow. |
| `1` | `sub_chk` | Checked 64-bit signed subtraction (`s1 - s2`); traps on overflow. |
| `2` | `mul_chk` | Checked 64-bit signed multiplication (`s1 * s2`); traps on overflow. |
| `3` | `mul_div_round` | Exact 128-bit intermediate `(s1 * s2) / s3` with `ROUND_HALF_UP`; traps on zero divisor or 64-bit overflow. |
| `4` | `div_round` | Signed division `s1 / s2` with `ROUND_HALF_UP`; traps on zero divisor or `INT64_MIN / -1`. |
| `5` | `rescale` | Scale adjustment by `10^delta` (`imm16_lo = delta`, `imm16_hi = dir`: `0` = multiply/up, `1` = divide/down with `ROUND_HALF_UP`). |
| `6` | `bound_chk` | Verify `|s1| <= 10^P - 1` (`imm16_lo = P`); traps on out-of-range. |
| `7` | `abs_chk` | Checked absolute value (`INT64_MIN` traps). |
| `8` | `neg_chk` | Checked negation (`INT64_MIN` traps). |
| `9` | `f64_to_dec` | Convert IEEE-754 `f64` to scaled `DECIMAL(P, S)` (`imm16_lo = S`, `imm16_hi = P`) with `ROUND_HALF_UP`; `NaN` $\to$ `NULL`, non-finite/out-of-range traps. |
| `10` | `dec_to_f64` | Convert scaled `DECIMAL64` (`imm16_lo = S`) to IEEE-754 `f64`. |
| `11` | `round_scale` | Round to target digit offset (`imm16_lo = drop_digits`) using `ROUND_HALF_UP`. |
| `12` | `trunc_scale` | Truncate toward zero by `imm16_lo = drop_digits`. |
| `13` | `floor_scale` | Floor toward $-\infty$ by `imm16_lo = drop_digits`. |
| `14` | `ceil_scale` | Ceiling toward $+\infty$ by `imm16_lo = drop_digits`. |
| `15` | `div_safe` | Signed division `s1 / s2` with `ROUND_HALF_UP`; returns `NULL` when `s2 == 0` instead of trapping. |

### 2.2 `0x58 OP_VEC_DECIMAL_ALU` (Pillar 4, 16 Subops)

* **Metadata**: `allowed_flags: 0x3` (`.scalar` = `0x2`, `.mask` = `0x1`), `morsel_role: body_ok`, `banks: { dst: V, s1: V, s2: OPT_V_OR_R, s3: SUBOP_DEP }`, `imm_layout: OPT_U16_PAIR`, `sets_vm_flags: []`.

| Subop | Name | Semantics |
| :---: | :--- | :--- |
| `0` | `add_chk` | Lane-wise checked addition (`V[s1] + V/R[s2]`). |
| `1` | `sub_chk` | Lane-wise checked subtraction (`V[s1] - V/R[s2]`). |
| `2` | `mul_chk` | Lane-wise checked multiplication (`V[s1] * V/R[s2]`). |
| `3` | `mul_div_r` | Lane-wise 128-bit `(V[s1] * V/R[s2]) / R[s3]` with `ROUND_HALF_UP` (scalar divisor). |
| `4` | `mul_div_v` | Lane-wise 128-bit `(V[s1] * R[s2]) / V[s3]` with `ROUND_HALF_UP` (vector divisor). |
| `5` | `div_round` | Lane-wise `V[s1] / V/R[s2]` with `ROUND_HALF_UP`; traps on zero divisor. |
| `6` | `div_safe` | Lane-wise `V[s1] / V/R[s2]` with `ROUND_HALF_UP`; zero divisor yields `NULL`. |
| `7` | `rescale` | Lane-wise scale adjustment by `10^delta` (`imm16_lo = delta`, `imm16_hi = dir`). |
| `8` | `bound_chk` | Lane-wise precision check `|V[s1]| <= 10^P - 1` (`imm16_lo = P`). |
| `9` | `abs_chk` | Lane-wise checked absolute value. |
| `10` | `neg_chk` | Lane-wise checked negation. |
| `11` | `f64_to_dec` | Lane-wise `f64` $\to$ `DECIMAL(P, S)` with `ROUND_HALF_UP`. |
| `12` | `dec_to_f64` | Lane-wise `DECIMAL64` $\to$ `f64`. |
| `13` | `round_scale` | Lane-wise `ROUND_HALF_UP` by `imm16_lo = drop_digits`. |
| `14` | `trunc_scale` | Lane-wise truncation toward zero by `imm16_lo = drop_digits`. |
| `15` | `mul_div_safe_r` | Lane-wise 128-bit `(V[s1] * V/R[s2]) / R[s3]` with `ROUND_HALF_UP`; `R[s3] == 0` yields `NULL`. |

### 2.3 Checked Aggregation Subops

* **`0x52 OP_VEC_REDUCE.sum_i64_chk` (subop `11`)**: Deterministic checked 64-bit signed sum over active, non-null lanes of `V[s1]` into `R[dst]`. Traps with `IMPULSE_VM_ERR_ARITHMETIC_OVERFLOW` (`16`) if the running sum overflows `int64_t`.
* **`0x37 OP_MORSEL_COMMIT.scatter_add_chk` (subop `9`)**: Checked morsel scatter-add into an outer `I64` / `DECIMAL64` accumulator vector (`V0..V7`). Traps with `IMPULSE_VM_ERR_ARITHMETIC_OVERFLOW` (`16`) if any target lane overflows `int64_t`.

### 2.4 Status Codes, Rounding & Non-Trapping Invariants

* **Status Codes**:
    * `16` — `IMPULSE_VM_ERR_ARITHMETIC_OVERFLOW`: Signed 64-bit overflow or `bound_chk` precision violation (`|x| > 10^P - 1`).
    * `17` — `IMPULSE_VM_ERR_DIV_BY_ZERO`: Zero divisor in trapping division (`div_round`, `mul_div_round`, `mul_div_r`, `mul_div_v`).
* **Rounding Mode**: All rounding decimal operations use **half-away-from-zero (`ROUND_HALF_UP`)**, where $|r| \times 2 \ge |d|$ rounds away from zero.
* **Masked / `NULL` Non-Trapping Invariant**:
    * When `.mask` (`FLAG_MASKED_S3`) is set, inactive lanes (`F[s3]` bit $= 0$) MUST NOT be evaluated for overflow or division by zero.
    * When any input lane is `NULL` (Kleene 3VL validity bit $= 0$), the output lane is `NULL` and MUST NOT trap, even if the other operand is `0` (division) or `INT64_MIN` / `INT64_MAX` (overflow).
    * `div_safe` and `mul_div_safe_r` emit `NULL` on a zero divisor rather than trapping with status `17`.

---

## 3. Compiler Coercion, Casts & Boundary Folding (`ImpScheme` & `CEL`)

### 3.1 Binary Operator Scale & Precision Derivation

For operands $A : \text{DECIMAL}(P_1, S_1)$ and $B : \text{DECIMAL}(P_2, S_2)$:

| Operation | Output Scale $S$ | Output Precision $P$ | Lowering |
| :--- | :--- | :--- | :--- |
| `A + B`, `A - B` | $\max(S_1, S_2)$ | $\min(18, \max(P_1 - S_1, P_2 - S_2) + S + 1)$ | Rescale lower-scale operand up by $S - S_i$, then emit `add_chk` / `sub_chk`. |
| `A * B` | $\min(18, S_1 + S_2)$ | $\min(18, P_1 + P_2)$ | If $S_1 + S_2 \le 18$: emit `mul_chk`. Else: emit 128-bit `mul_div_round` / `mul_div_r` dividing by $10^{(S_1 + S_2) - 18}$. |
| `A / B`, `safe-div(A, B)` | $\min(18, \max(6, S_1))$ | $18$ | Scale numerator by $10^{S - S_1 + S_2}$ via 128-bit `mul_div_round` / `mul_div_v` (`safe-div` checks `B == 0` $\to$ `NULL` prior to scaling). |

### 3.2 Implicit Promotion & Explicit Casts

* **`DECIMAL` $\oplus$ `INT` (Exact Promotion)**: Integer operands (`i64` / `i32` / etc.) mixed with `DECIMAL` in arithmetic or comparisons are implicitly promoted to `DECIMAL(18, 0)` with zero precision loss.
* **`DECIMAL` $\leftrightarrow$ `FLOAT` (Forbidden Implicitly)**: Mixing `DECIMAL` with `f32` / `f64` (or passing `DECIMAL` to transcendental math functions such as `sqrt`, `exp`, `log`, `sin`) fails compilation with `TYPE_MISMATCH`. Conversions MUST be explicit via `CAST` / `(cast ...)`.
* **Explicit `CAST` Lowering**:
    * `DECIMAL(P1, S1) -> DECIMAL(P2, S2)`: `rescale` (when $S_1 \ne S_2$) + `bound_chk(P2)`.
    * `INT -> DECIMAL(P, S)`: `rescale(x, S, up)` + `bound_chk(P)`.
    * `FLOAT64 -> DECIMAL(P, S)`: `f64_to_dec(x, S, P)`.
    * `DECIMAL(P, S) -> FLOAT64`: `dec_to_f64(x, S)`.
    * `DECIMAL(P, S) -> INT`: `trunc_scale(x, S)`.

### 3.3 Compile-Time Literal Comparison Boundary Folding

When comparing a `DECIMAL(colP, colS)` column against a constant decimal literal $L = u \times 10^{-S_{\text{lit}}}$, `DecimalBoundaryFolder` folds the predicate at compile time against the column bounds $[-\text{colMax}, +\text{colMax}]$ where $\text{colMax} = 10^{\text{colP}} - 1$:

* **Exact at column scale** ($S_{\text{lit}} \le \text{colS}$, or $S_{\text{lit}} > \text{colS}$ with $u \bmod 10^{S_{\text{lit}} - \text{colS}} = 0$): rewrites to a single `int64_t` comparison at `colS` with zero runtime rescaling (directly eligible for `OP_NODE_FILTER` and `OP_INDEX_SCAN`), or folds to `ALWAYS_TRUE` / `ALWAYS_FALSE` when outside $[-\text{colMax}, +\text{colMax}]$.
* **Between adjacent column ticks** ($S_{\text{lit}} > \text{colS}$ and $r = \text{floorMod}(u, d) \ne 0$, with $d = 10^{S_{\text{lit}} - \text{colS}}$ and $q = \text{floorDiv}(u, d)$):
    * `==` $\to$ `ALWAYS_FALSE`
    * `!=` $\to$ `ALWAYS_TRUE`
    * `>`, `>=` $\to$ `col >= q + 1` (or `ALWAYS_FALSE` / `ALWAYS_TRUE` at domain bounds)
    * `<`, `<=` $\to$ `col <= q` (or `ALWAYS_FALSE` / `ALWAYS_TRUE` at domain bounds)

### 3.4 `CEL` & `ImpScheme` Syntax

| Frontend | Form | Example | Notes |
| :--- | :--- | :--- | :--- |
| **CEL** | Decimal literal suffix | `19.99d`, `-0.005d` | Scientific notation (`1e2d`) is rejected at lex time. |
| **CEL** | String constructor | `decimal("19.99")` | Infers minimal `(P, S)` from the literal string. |
| **CEL** | Explicit `(P, S)` constructor | `decimal("19.99", 10, 2)` | Validates `1 <= P <= 18`, `0 <= S <= P`, and exact fit. |
| **CEL** | SQL/Cypher-style cast | `CAST(edge.amount AS DECIMAL(10, 2))` | Lowers to `(cast expr (decimal 10 2))`. |
| **ImpScheme** | Type & cast form | `(cast x (decimal 10 2))` | Scalar bank `R` or vector bank `V` (`(vec "Dom" (decimal 10 2))`). |
