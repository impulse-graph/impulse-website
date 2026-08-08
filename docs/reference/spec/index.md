# Impulse Graph Binary Snapshot Specification Hub

Welcome to the **Impulse Graph C-ABI Binary Snapshot Specification** hub.

The specification defines the zero-copy, memory-mapped binary snapshot layout (`*.imps`) used across C++, Java 25, Rust, Python, Go, and C#.

---

## Available Specification Versions

| Version | Status | Highlights | Specification Document |
| :--- | :--- | :--- | :--- |
| **v0.9.0** | 🟢 **Current Baseline** | 4KB Page 0 Header Baseline, Shared String Table, 128-Byte Alignment, Single-Pass Cloud S3 Writer | [Read Specification v0.9.0](v0.9.0.md) |

---

## Version Compatibility Policy

- **Minor Version Bumps (e.g. v0.9 -> v0.10)**: Fully backward-compatible. Additive feature bitmask flags or appended optional sections.
- **Major Version Bumps (e.g. v0.9 -> v1.0)**: May change structural header layouts or binary alignment bounds.
