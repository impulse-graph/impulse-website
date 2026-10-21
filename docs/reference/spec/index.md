# Impulse Graph Engine Normative Specifications

This section hosts the canonical **Normative Specifications** for the Impulse Binary Snapshot Format (`.imps`), the `ImpulseVM` Virtual Machine ISA (`impOps`), the `ImpAs` assembly text format (`.impas`), and the declarative schema catalog (`.imps.schema.yaml`).

Both primary execution engines—the **Pure Java 25 Engine (`impulse-graph-java`)** and the **Native C++20 / C-ABI Engine (`impulse-graph-core`)**—conform to these specifications with 100% bitwise and state parity.

---

## Normative Specification Suite

| Document | Scope & Contents | Link |
| :--- | :--- | :--- |
| **Binary Snapshot Format Specification (`.imps`)** | 4KB Page 0 baseline header, Section 2 Shared String Table, Domain Catalog, 128-byte-aligned CSR/CSC/Attribute sections, Secondary Indices, Ed25519 Signature Block, and single-pass S3 streaming layout. | [Read Format Specification](format-specification.md) |
| **ImpulseVM & `impOps` Instruction Set Specification** | 64-bit register machine (`R0`..`R63`), 640-byte cache-aligned state frame (`impulse_vm_state_t`), register type system, status flags (`ZF`, `LT`, `GT`, `EQ`, `ST`), and formal semantics for all `impOps` opcodes (`0x00`..`0x95`). | [Read VM & ISA Specification](vm-specification.md) |
| **ImpAs (`.impas`) Assembly Format Specification** | Line-oriented `.data` and `.text` assembly grammar, register operands, immediate constants, and `{{EXPECT: ...}}` polyglot test-vector assertion directives. | [Read ImpAs Specification](impas-specification.md) |
| **Snapshot Schema Specification (`.imps.schema.yaml`)** | Declarative YAML/JSON schema specification for node domains, attribute types, relation cardinalities, and multi-language DTO code generation. | [Read Schema Specification](schema-specification.md) |
| **Generated C-ABI Protocol Tables** | Auto-generated enum and struct offset tables from the normative schema definition. | [Read Generated Tables](protocol-tables.md) |
| **Specification Overview** | Architectural summary of the Impulse Binary Snapshot Format. | [Read Overview](overview.md) |
