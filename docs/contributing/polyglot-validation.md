# Polyglot Validation & Testing

This page covers how Impulse Graph verifies correctness across its specification, VM engines, compilers, and language bindings (`impulse-graph-spec`, `impulse-graph-core`, `impulse-graph-java`, `impulse-ocaml`, and `impulse-verification`).

For workspace setup and building individual repositories, see the [Contributing Guide](index.md). For design rationale, see [Why Impulse Graph?](../concepts/why-impulse.md).

---

## 1. Verification Layers

| Layer | Location | What It Tests |
| :--- | :--- | :--- |
| **Binary Snapshot Vectors** | `impulse-graph-spec/test-vectors/tc01`–`tc38` | Positive layout, alignment, CSR/CSC, key catalog, and attribute vectors; negative SHA-256 corruption, bad flag, out-of-bounds offset, and truncation traps. |
| **VM Assembly Suite** | `impulse-graph-spec/test-vectors/vm-impas/` | 531 self-contained `.impas` scripts with `{EXPECT: ...}` headers. `run_vm_asm_suite.py` enforces 100% coverage of all 166 opcodes (`0x00`..`0xCB`) and requires every opcode to appear in at least 2 test files. |
| **Four-Way VM Parity** | `impulse-verification/tools/four_way_validation.py` | Runs every `.impas` vector across C++ (`-O3`), C++ (`-O0`), Java 25, and OCaml (`impulse-ocaml`), requiring identical registers (`R0`..`R63`), PC, flags, status codes, and `ICTX` v1 SHA-256 state hashes. |
| **Contract & Differential Fuzzing** | `impulse-verification/tools/fuzz_vm_contracts.py` & `test_opcode_contracts.cpp` | Validates all 188 opcode contract variants (`contracts.json`) for register type checks, bounds (`r >= 64`), in-place aliasing, and null-context safety. |
| **Cross-Compiler Parity** | `impulse-verification/tools/cross_compiler_parity.py` | Verifies consistent lowering and execution across frontends (ImpK, ImpLog, openCypher). |
| **Engine vs. FFI Boundaries** | `impulse-graph-core` / `impulse-graph-java` | Engine kernels run the full ISA suite; FFI bindings (Python, Go, Node.js, .NET) run focused boundary tests covering C-ABI signatures, struct layout, memory lifecycle, and error propagation. |

### Test-First ISA Rule
New `impOps` opcodes or ISA behavior changes must add positive and negative `.impas` test vectors in `impulse-graph-spec/test-vectors/vm-impas/` alongside the spec change. Each `.impas` file embeds its assertions in comment headers:

```asm
; {EXPECT: STATUS = IMPULSE_VM_OK}
; {EXPECT: R0 = 42}
; {EXPECT: R1 = 100}
; {EXPECT: FLAG = !ZF}

.text
0x00: OP_LOAD_CONST_INT R0, 42
0x01: OP_LOAD_CONST_INT R1, 100
0x04: OP_MOV R7, R0
0x09: OP_HALT
```

For the `ICTX` v1 hash wire format and opcode contract definitions, see [VM Specification §9–§10](../reference/spec/vm-specification.md) and [C-ABI Reference §7](../reference/c-abi.md).

---

## 2. Engine Logic vs. FFI Binding Scope

| Concern | Targets | Scope |
| :--- | :--- | :--- |
| **Engine Logic** | `impulse-cpp`, `impulse-rust`, `impulse-graph-java`, `impulse-ocaml` | Opcode execution, bitsets, SIMD kernels, memory mapping, and compiler passes. |
| **FFI Boundaries** | `impulse-python`, `impulse-go`, `impulse-node`, `impulse-dotnet` | C-ABI signatures, struct padding, string/array marshaling, pointer lifecycle, and exception mapping. |

Running all 531 VM vectors through every FFI wrapper on every PR adds build time without finding engine bugs already caught by the native kernel and four-way suites. PRs run focused FFI contract suites, while release validation exercises the full matrix.

---

## 3. CI Gates

* **`impulse-graph-core` PR CI**: C++20 build & `ctest` matrix (Linux, macOS, Windows), Rust crate (`rustfmt`, `clippy`, `cargo test`), CLI matrix, Multi-Language FFI bindings (Python, Go, Node.js), ASan/UBSan, TSan, and libFuzzer smoke tests.
* **`impulse-graph-java` PR CI**: Dual-target JDK 21 LTS and JDK 22+/25 LTS builds, `spotless:check`, unit/integration suites, and Jazzer fuzzing.
* **Release Pipelines**: Artifact builds, signing, and provenance attestations are documented in [Packages & Distribution](../reference/packages.md).

---

## 4. Running Verification Suites Locally

First build the C++ kernels (`build_on` and `build_off`) and Java classes as described in the [Contributing Guide](index.md), then run:

```bash
# 1. Spec VM assembly suite & 100% opcode coverage check
cd impulse-graph-spec
python3 tools/run_vm_asm_suite.py

# 2. Four-way VM parity (C++ -O3, C++ -O0, Java 25, OCaml)
cd ../impulse-verification
python3 tools/four_way_validation.py

# 3. Contract-guided differential fuzzer
python3 tools/fuzz_vm_contracts.py --iterations 1000

# 4. Cross-compiler parity (ImpK / ImpLog / openCypher)
python3 tools/cross_compiler_parity.py
```
