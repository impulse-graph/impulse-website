# Impulse Graph Engine Normative Specifications (v0.9.0)

This section hosts the canonical **Normative Specifications (Version 0.9.0)** for the Impulse Graph Engine binary format, Virtual Machine ISA, assembly text representation, and declarative schema catalog.

---

## v0.9.0 Normative Specification Suite

| Document | Scope & Contents | Link |
| :--- | :--- | :--- |
| **Binary Snapshot Format Specification (`v0.9.0`)** | 4KB Page 0 baseline header, Section 2 Shared String Table, Domain Catalog, 128-byte-aligned CSR/CSC/Attribute sections, Section 2.6 Secondary Indices, Ed25519 Signature Block, and single-pass S3 streaming layout. | [Read Format Specification](format-specification.md) |
| **ImpulseVM & `impOps` Instruction Set Specification** | 64-bit register machine (`R0`..`R63`), 640-byte cache-aligned state frame (`impulse_vm_state_t`), register type system, status flags (`ZF`, `LT`, `GT`, `EQ`, `ST`), and formal semantics for all `impOps` opcodes (`0x00`..`0x95`). | [Read VM & ISA Specification](vm-specification.md) |
| **ImpAs (`.impas`) Assembly Format Specification** | Line-oriented `.data` and `.text` assembly grammar, register operands, immediate constants, and `{{EXPECT: ...}}` polyglot test-vector assertion directives. | [Read ImpAs Specification](impas-specification.md) |
| **Snapshot Schema Specification (`.imps.schema.yaml`)** | Declarative YAML/JSON schema specification for node domains, attribute types, relation cardinalities, and multi-language DTO code generation. | [Read Schema Specification](schema-specification.md) |
| **Generated C-ABI Protocol Tables (`v0.9.0`)** | Auto-generated enum and struct offset tables from `v0.9.yaml`. | [Read Generated Tables](v0.9.md) |
| **Specification Overview (`v0.9.0`)** | Concise architectural summary of Binary Snapshot Format v0.9.0. | [Read Overview](v0.9.0.md) |

---

## Version Compatibility Policy

* **Minor Version Bumps (`v0.9` $\to$ `v0.10`)**: Backward-compatible additive feature bitmask flags or appended optional sections.
* **Major Version Bumps (`v0.9` $\to$ `v1.0`)**: Structural header layout or alignment changes.
