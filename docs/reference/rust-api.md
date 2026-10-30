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
| **`reader`** | `SnapshotReader` (`open`, `domain_count`, `relation_count`, `is_reachable`, `get_row_offsets`, `get_col_indices`, `get_neighbors`, `get_attribute_data`, `index_entries`, `parse_vamana_header`, `vamana_ann_search`) |
| **`traversal`** | `Traversal`, `TraversalStep`, `StepDirection` |
| **`writer`** | `SnapshotWriter` (`new`, `add_domain`, `add_relation`, `add_attribute_to_relation`, `add_attribute_to_domain`, `add_index`, `add_vamana_index`, `add_built_vamana_index`, `finalize`) |
| **`vamana`** | `VamanaBuildConfig`, `BuiltVamanaIndex` (`VamanaArtifact`), `build_vamana_index`, `permute_vamana_index`, `compute_vamana_bfs_order`, `vamana_ann_search`, `brute_force_ann_search`, `evaluate_ann_quality` (`v0.9.1`) |
| **`spec`** | `SnapshotHeader`, `KeyType`, `BaseDataType`, `EncodingType`, `ImpulseError`, `IMPULSE_MAGIC`, `IMP_INDEX_VAMANA_ANN` (`0x08`), `VamanaHeader`, `VamanaMetric`, `VamanaQuantType`, `VAMANA_MAGIC` |
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

### 4.1 Vamana ANN Graph Index Construction, Permutation & Two-Stage Search (`vamana` Module, Planned `v0.9.1`)

The zero-dependency `impulse_graph::vamana` module implements Section 2.6 **`IMP_INDEX_VAMANA_ANN` (`0x08`)** single-layer DiskANN/Vamana proximity graph construction, medoid-seeded BFS node permutation, and two-stage quantized beam search (`BQ1` / `SQ8` / `FP16` routing codes followed by exact `Float32` reranking):

| Type / Function | Description |
| :--- | :--- |
| **`IMP_INDEX_VAMANA_ANN` (`0x08`)** | Section 2.6 secondary index type constant for 128-byte-aligned Vamana proximity graphs (`VAMANA_MAGIC = 0x56414D41`). |
| **`VamanaBuildConfig`** | Build parameters (`max_degree_r`, `ef_construction`, `alpha`, `metric: VamanaMetric`, `quant_type: VamanaQuantType`, `seed`) and `VamanaBuildConfig::parse_params("r=32,l=100,alpha=1.2,metric=cosine,quant=sq8")`. |
| **`BuiltVamanaIndex` (`VamanaArtifact`)** | Serialized Vamana index artifact containing the 64-byte `VamanaHeader`, 128-byte-aligned fixed-stride `adj_slab` (`N * (R + 1) * 4` bytes), and quantized `quant_slab`. |
| **`build_vamana_index(...)`** | Constructs a two-pass $\alpha$-RNG pruned Vamana index ($\alpha = 1.0$ then $\alpha = \text{cfg.alpha}$) over `[node_count, dimension]` `f32` vectors. |
| **`compute_vamana_bfs_order(hdr, adj_slab)`** | Computes a medoid-rooted BFS node ordering `(old_to_new, new_to_old)` so neighbors visited consecutively during beam search are co-located in memory. |
| **`permute_vamana_index(...)`** | Relabels an existing Vamana index in $O(N \cdot R + N \cdot D)$ time under a node ID bijection `(old_to_new, new_to_old)` without rebuilding the graph. |
| **`vamana_ann_search(...)`** | Executes greedy beam search using quantized routing codes (`BQ1`, `SQ8`, `FP16`) and reranks the `ef_search` beam survivors using exact `Float32` vectors. |
| **`brute_force_ann_search(...)` & `evaluate_ann_quality(...)`** | Exact nearest-neighbor oracle and `(recall_at_1, recall_at_k, ndcg_at_k, mrr)` quality evaluator. |

```rust
use impulse_graph::reader::SnapshotReader;
use impulse_graph::spec::{BaseDataType, KeyType, VamanaMetric, VamanaQuantType, IMP_INDEX_VAMANA_ANN};
use impulse_graph::vamana::{brute_force_ann_search, evaluate_ann_quality, VamanaBuildConfig};
use impulse_graph::writer::SnapshotWriter;

fn build_and_search_vamana(vectors: &[f32], n: usize, dim: usize) -> Result<(), Box<dyn std::error::Error>> {
    let mut vec_bytes = Vec::with_capacity(vectors.len() * 4);
    for &f in vectors {
        vec_bytes.extend_from_slice(&f.to_le_bytes());
    }

    let mut writer = SnapshotWriter::new("entities_vamana.imps");
    writer.add_domain(0, KeyType::Int64, "Entity");
    writer.set_domain_node_count(0, n as u64);
    writer.add_attribute_to_domain(0, "embedding", BaseDataType::Float32 as u8, dim as u32, vec_bytes, None);

    let cfg = VamanaBuildConfig::parse_params("r=32,l=100,alpha=1.2,metric=cosine,quant=sq8")?;
    writer.add_vamana_index(0, "embedding", "Entity_embedding_vamana", &cfg)?;
    writer.finalize()?;

    let reader = SnapshotReader::open("entities_vamana.imps")?;
    let entry = &reader.index_entries()[0];
    assert_eq!(entry.index_type, IMP_INDEX_VAMANA_ANN);

    let query = &vectors[0..dim];
    let approx = reader.vamana_ann_search(entry, query, /*top_k=*/ 10, /*ef_search=*/ 64)?;
    let exact  = brute_force_ann_search(VamanaMetric::Cosine, vectors, n, dim, query, 10);
    let (_r1, recall_at_10, ndcg_at_10, _mrr) = evaluate_ann_quality(&approx, &exact, 10);
    println!("Recall@10: {:.3}, nDCG@10: {:.3}", recall_at_10, ndcg_at_10);
    Ok(())
}
```
