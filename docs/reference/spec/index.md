# Impulse Graph Binary Snapshot Specification Hub

Welcome to the **Impulse Graph C-ABI Binary Snapshot Specification** hub.

The specification defines the zero-copy, memory-mapped binary snapshot layout (`*.imps`) used across C++, Java 25, Rust, Python, Go, and C#.

---

## Available Specification Versions

| Version | Status | Highlights | Specification Document |
| :--- | :--- | :--- | :--- |
| **v2.4.0** | 🟢 **Current Baseline** | Ed25519 Cryptographic Signatures, SHA-256 Integrity, 4KB Page Alignment, SIMDCOMP & Sliced ELLPACK Encodings | [Read Specification v2.4](v2.4.md) |
| **v2.3.0** | 🟡 **Legacy Supported** | 64-bit Node/Edge Counters, CSR Topology, Domain Catalog | [Read Specification v2.3](v2.3.md) |

---

## Version Compatibility Policy

- **Minor Version Bumps (e.g. v2.4 -> v2.5)**: Fully backward-compatible. Additive feature bitmask flags or appended optional sections.
- **Major Version Bumps (e.g. v2.0 -> v3.0)**: May change structural header layouts or binary alignment bounds.
