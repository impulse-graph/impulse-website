# Rust Crate Reference (`impulse-graph`)

The **Impulse Graph Engine Rust Crate** (`impulse-graph`, located in `impulse-graph-core/impulse-rust`) has **zero third-party runtime dependencies** and provides memory-mapped `.imps` snapshot reading, zero-copy Structure-of-Arrays (SoA) slice accessors, domain-bound fluent traversals, and single-pass snapshot writing.

---

## 1. Installation (`Cargo.toml`)

```toml
[dependencies]
impulse-graph = "0.9"
```

| Module | Exported Types & Functions |
| :--- | :--- |
| **`reader`** | `SnapshotReader`, `DomainInfo`, `RelationInfo`, `AttributeInfo` |
| **`traversal`** | `Traversal`, `TraversalStep`, `StepDirection` |
| **`writer`** | `SnapshotWriter`, `AttributeField` |
| **`spec`** | `SnapshotHeader`, `KeyType`, `BaseDataType`, `EncodingType`, `ImpulseError`, `IMPULSE_MAGIC` |
| **`simd`** | SIMD dot product, elementwise sum/scale/mul, and sorted `u32` slice intersection |
| **`ffi`** | Raw `extern "C"` bindings to `impulse_graph.h` and `impulse_vm.h` |

---

## 2. Zero-Copy Snapshot Reader (`SnapshotReader`)

`SnapshotReader::open` maps an `.imps` file via OS `mmap`, validating the 4KB Page 0 header, CRC-16-CCITT header checksum, and SHA-256 payload digest:

```rust
use impulse_graph::SnapshotReader;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let reader = SnapshotReader::open("social_graph.imps")?;

    println!("Domains: {}, Relations: {}", reader.domain_count(), reader.relation_count());

    // Direct O(log d) adjacency check on relation 0 (0 -> 1)
    let connected: bool = reader.is_adjacent(0, 0, 1)?;

    // Zero-copy slice of outgoing neighbor dense IDs (&[u32])
    let neighbors: &[u32] = reader.get_neighbors(0, 0)?;

    // Zero-copy typed SoA attribute slice (&[f32], 128-byte aligned)
    let weights: &[f32] = reader.get_attribute_slice_f32(0, "weight")?;
    Ok(())
}
```

---

## 3. Fluent Multi-Hop Traversal (`Traversal`)

```rust
use impulse_graph::SnapshotReader;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let reader = SnapshotReader::open("social_graph.imps")?;

    // Domain-anchored traversal with transitive closure
    let reachable_groups: Vec<u64> = reader
        .domain("User")
        .from(0)
        .out("MEMBER_OF")
        .repeat_until_stable("PARENT_GROUP")
        .to_vec();

    println!("Reachable Groups: {:?}", reachable_groups);
    Ok(())
}
```

---

## 4. Single-Pass Streaming Writer (`SnapshotWriter`)

Constructs 4KB-page-aligned and 128-byte-section-aligned `.imps` snapshots with automatic CRC-16 header and SHA-256 payload checksum computation:

```rust
use std::collections::HashMap;
use impulse_graph::{SnapshotWriter, KeyType, BaseDataType};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut writer = SnapshotWriter::new("graph.imps");
    writer.add_domain(0, KeyType::Int64, "User", 4);
    writer.add_relation(
        "FOLLOWS",
        0, 0,
        &[0u32, 2, 3, 4, 4],
        &[1u32, 2, 3, 0],
        None,
        Vec::new(),
    );
    writer.write(&HashMap::new())?;
    Ok(())
}
```
