# Impulse Graph Binary Snapshot Specification Hub

Welcome to the **Impulse Graph C-ABI Binary Snapshot Specification** hub.

The specification defines the zero-copy, memory-mapped binary snapshot layout (`*.imps`) used across C++, Java 25, Rust, Python, Go, and C#.

---

## Available Specification Versions

| Version | Status | Highlights | Specification Document |
| :--- | :--- | :--- | :--- |
| **v0.9.0** | 🟢 **Current Baseline** | Section 2 Shared String Table, 128-Byte Hardware Alignment, Single-Pass S3 Cloud Streaming Write, SHA-256 & Ed25519 Cryptographic Signatures | [Read Specification v0.9.0](v0.9.0.md) |

---

## Version Compatibility Policy

- **Patch Version Bumps (e.g. v0.9.0 -> v0.9.1)**: Fully backward-compatible. Additive feature bitmask flags or appended optional sections.
- **Major Version Bumps (e.g. v0.9.0 -> v1.0.0)**: Stable protocol freeze. The C-ABI header and section directory layout will be 100% frozen for long-term backward compatibility.
