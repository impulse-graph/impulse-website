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
| **`reader`** | `SnapshotReader` (`open`, `domain_count`, `relation_count`, `is_reachable`, `get_row_offsets`, `get_col_indices`, `get_neighbors`, `get_attribute_data`) |
| **`traversal`** | `Traversal`, `TraversalStep`, `StepDirection` |
| **`writer`** | `SnapshotWriter` (`new`, `add_domain`, `add_relation`, `add_attribute_to_relation`, `add_index`, `finalize`) |
| **`spec`** | `SnapshotHeader`, `KeyType`, `BaseDataType`, `EncodingType`, `ImpulseError`, `IMPULSE_MAGIC` |
| **`simd`** | SIMD dot product, elementwise sum/scale/mul, and sorted `u32` slice intersection |
| **`ffi`** | Raw `extern "C"` bindings to `impulse_graph.h` and `impulse_vm.h` |

---

## 2. Zero-Copy Snapshot Reader (`SnapshotReader`)

`SnapshotReader::open` maps an `.imps` file via OS `mmap`, validating the 4KB Page 0 header, CRC-16-CCITT header checksum, and SHA-256 payload digest:

```rust
use impulse_graph::reader::SnapshotReader;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let reader = SnapshotReader::open("social_graph.imps")?;

    println!("Domains: {}, Relations: {}", reader.domain_count(), reader.relation_count());

    // Direct O(log d) adjacency check on relation 0 (0 -> 1)
    let connected: bool = reader.is_reachable(0, 0, 1);

    // Outgoing neighbor dense IDs (Vec<u64>)
    let neighbors: Vec<u64> = reader.get_neighbors(0, 0)?;

    // Zero-copy CSR row_offsets and col_indices slices (&[u32], 128-byte aligned)
    let row_offsets: &[u32] = reader.get_row_offsets(0)?;
    let col_indices: &[u32] = reader.get_col_indices(0)?;

    // Zero-copy SoA attribute byte slice (&[u8], 128-byte aligned)
    let attr_bytes: &[u8] = reader.get_attribute_data(0, 0)?;
    Ok(())
}
```

---

## 3. Fluent Multi-Hop Traversal (`Traversal`)

```rust
use impulse_graph::reader::SnapshotReader;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let reader = SnapshotReader::open("social_graph.imps")?;

    // Multi-hop fluent traversal with inline CEL filtering
    let reachable_nodes: Vec<u64> = reader
        .traverse(0)
        .out("MEMBER_OF")
        .in_step("MANAGES")
        .out_filtered("HAS_PERMISSION", "edge.port >= $min_port")
        .with_param("min_port", 22.0)
        .to_vec()?;

    println!("Reachable Nodes: {:?}", reachable_nodes);
    Ok(())
}
```

---

## 4. Single-Pass Streaming Writer (`SnapshotWriter`)

Constructs 4KB-page-aligned and 128-byte-section-aligned `.imps` snapshots with automatic CRC-16 header and SHA-256 payload checksum computation:

```rust
use impulse_graph::writer::SnapshotWriter;
use impulse_graph::spec::KeyType;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut writer = SnapshotWriter::new("graph.imps");
    writer.add_domain(0, KeyType::Int64, "User");
    writer.add_relation(
        0, 0,
        4, 4,
        vec![0u32, 2, 3, 4, 4],
        vec![1u32, 2, 3, 0],
    );
    writer.finalize()?;
    Ok(())
}
```
