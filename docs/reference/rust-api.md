# Rust API Reference (`impulse-rust` / `impulse-graph`)

This reference documents the **Impulse Graph Engine Core Rust Crate** (`impulse-graph`, located in `impulse-graph-core/impulse-rust`).

The Rust crate has zero third-party runtime dependencies (`AGENTS.md §3.2`) and provides memory-mapped `.imps` v0.9.0 binary snapshot reading, Structure-of-Arrays (SoA) attribute slice accessors, fluent multi-hop traversals, single-pass snapshot writing, and C-ABI FFI bindings.

---

## 1. Installation (`Cargo.toml`)

```toml
[dependencies]
impulse-graph = "0.9.0"
```

---

## 2. Public Modules & Re-Exports (`impulse_graph`)

| Module | Exported Types & Functions |
| :--- | :--- |
| **`reader`** | `SnapshotReader`, `DomainInfo`, `RelationInfo`, `AttributeInfo` |
| **`traversal`** | `Traversal`, `TraversalStep`, `StepDirection` |
| **`writer`** | `SnapshotWriter`, `AttributeField` |
| **`spec`** | `SnapshotHeader`, `KeyType`, `BaseDataType`, `EncodingType`, `ImpulseError`, `IMPULSE_MAGIC`, `IMPULSE_VERSION_PACKED` |
| **`simd`** | SIMD dot product, elementwise sum/scale/mul, and sorted `u32` slice intersection |
| **`ffi`** | Raw `extern "C"` bindings to `impulse_graph.h` and `impulse_vm.h` |

---

## 3. Zero-Copy Snapshot Reader (`SnapshotReader`)

`SnapshotReader::open` maps a v0.9.0 `.imps` binary file via OS `mmap`, validating the 4KB Page 0 header, CRC-16-CCITT header checksum, and SHA-256 payload digest:

```rust
use impulse_graph::SnapshotReader;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let reader = SnapshotReader::open("social_graph.imps")?;

    println!("Magic: {:#x}, Version: {}", reader.header().magic(), reader.header().version());
    println!("Domains: {}, Relations: {}", reader.domain_count(), reader.relation_count());

    // Direct adjacency check on relation 0 (0 -> 1)
    let connected = reader.is_adjacent(0, 0, 1)?;

    // Zero-copy slice of outgoing neighbor dense IDs (&[u32])
    let neighbors: &[u32] = reader.get_neighbors(0, 0)?;

    // Zero-copy typed SoA attribute slice (&[f32])
    let weights: &[f32] = reader.get_attribute_slice_f32(0, "weight")?;
    Ok(())
}
```

### `SnapshotReader` Methods

* `SnapshotReader::open<P: AsRef<Path>>(path: P) -> Result<Self, ImpulseError>`: Open and validate `.imps` file via `mmap`.
* `header(&self) -> &SnapshotHeader`: Access 4KB Page 0 header metadata.
* `domain_count(&self) -> usize` / `relation_count(&self) -> usize`: Catalog counts.
* `is_adjacent(&self, relation_idx: usize, src_id: u32, tgt_id: u32) -> Result<bool, ImpulseError>`: Binary search adjacency check over CSR target slice.
* `get_neighbors(&self, relation_idx: usize, src_id: u32) -> Result<&[u32], ImpulseError>`: Return zero-copy `&[u32]` slice of outgoing neighbors for `src_id`.
* `get_attribute_slice_f32(&self, relation_idx: usize, attr_name: &str) -> Result<&[f32], ImpulseError>`: Return zero-copy `&[f32]` slice over a 128-byte-aligned SoA attribute column.
* `get_metadata(&self, key: &str) -> Option<&str>`: Lookup custom key-value pair from the Footer Metadata section.
* `traverse(&self, start_node: u64) -> Traversal<'_>`: Anchor a fluent multi-hop traversal pipeline.

---

## 4. Fluent Multi-Hop Traversal (`Traversal`)

```rust
use impulse_graph::SnapshotReader;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let reader = SnapshotReader::open("social_graph.imps")?;

    // 2-Hop Traversal: Seed(0) -> follows -> follows
    let reachable_users: Vec<u64> = reader
        .traverse(0)
        .out("follows")
        .out("follows")
        .to_vec();

    println!("2-Hop Reachable Users: {:?}", reachable_users);
    Ok(())
}
```

---

## 5. Single-Pass Streaming Writer (`SnapshotWriter`)

Constructs page-aligned and 128-byte-section-aligned Spec v0.9.0 `.imps` snapshots with automatic CRC-16 header and SHA-256 payload checksum computation:

```rust
use std::collections::HashMap;
use impulse_graph::{SnapshotWriter, KeyType, BaseDataType};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut writer = SnapshotWriter::new("graph.imps");
    writer.add_domain(0, KeyType::Int64, "User");

    let row_offsets = vec![0u32, 2, 4, 5, 5];
    let col_indices = vec![1u32, 2, 2, 3, 3];
    writer.add_relation(0, 0, 4, 5, row_offsets, col_indices);

    // Optional SoA edge attribute column
    let mut weight_bytes = Vec::new();
    for w in [1.0f32, 2.0, 3.0, 4.0, 5.0] {
        weight_bytes.extend_from_slice(&w.to_ne_bytes());
    }
    writer.add_attribute_to_relation(0, "weight", BaseDataType::Float32 as u8, 1, weight_bytes, None);

    let mut meta = HashMap::new();
    meta.insert("environment".to_string(), "production".to_string());
    writer.set_metadata(meta);

    writer.finalize()?;
    Ok(())
}
```
