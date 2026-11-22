# PyTorch GNN Sampling, Embeddings & Vamana Vector Search

Impulse Graph pairs 128-byte-aligned CSR/CSC graph topology with contiguous `[N, D]` `float32` embedding columns and embedded **Section 2.6 Vamana (DiskANN) proximity graphs (`IMP_INDEX_VAMANA_ANN = 0x08`, `v0.10.0`)** inside a single `.imps` file. PyTorch, `impulse-gnn`, and `ImpulseVM` read both graph structure and embeddings directly from the OS page cache without heap deserialization.

---

## 1. Zero-Copy CSR Topology & `[N, D]` Feature Tensors

When `impulse build` compiles a Parquet `FixedSizeListArray` column (or attaches an external `.npy` / `.safetensors` matrix), the resulting `.imps` file stores node features as a contiguous, 128-byte-aligned `[N, D]` array alongside `uint32` CSR `row_offsets` and `col_indices`.

In Python, `np.frombuffer` and `torch.from_numpy` wrap those mapped pages directly—avoiding the `16 bytes/edge` `[2, E]` `int64` `edge_index` expansion and decompression overhead of loading raw Parquet files on startup:

| Capability | `Parquet -> PyTorch` | `Impulse (.imps) -> PyTorch` |
| :--- | :--- | :--- |
| **Cold Open Latency** | Seconds to minutes (decompress, hash string keys, sort edges) | Direct `mmap` (`< 1 ms`; `0.224 ms`–`0.400 ms`) |
| **Topology Footprint** | `16 bytes/edge` (`[2, E]` `int64` PyG `edge_index`) | `~4 bytes/edge` (`uint32` CSR `col_indices` + `row_offsets`) |
| **Multi-Worker `DataLoader`** | Forked workers trigger Python CoW page duplication | Workers share read-only OS page-cache frames (`0 bytes` duplicated) |
| **Larger-Than-RAM Graphs** | Manual shard orchestration | OS demand-pages 4KB blocks from NVMe automatically |

```python
import numpy as np
import torch
from impulse_graph import Snapshot

with Snapshot("citations.imps") as snap:
    # 1. Zero-copy CSR topology tensors (uint32 views over mmap)
    row_offsets = torch.from_numpy(snap.get_row_offsets_array(relation_index=0))
    col_indices = torch.from_numpy(snap.get_col_indices_array(relation_index=0))

    # 2. Convert directly to torch.sparse_csr_tensor for sparse linear algebra
    adj_csr: torch.Tensor = snap.to_torch_csr(relation_index=0)

    # 3. Zero-copy edge weight or feature tensor view
    edge_count = snap.get_relation(0)["edge_count"]
    edge_weights = torch.from_numpy(
        snap.get_attribute_array(0, 0, dtype=np.float32, shape=(edge_count,))
    )
```

---

## 2. Disk-Backed Neighborhood Sampling (`impulse-gnn` & C-ABI)

For multi-hundred-gigabyte graphs on developer laptops or single-GPU training nodes, `Snapshot.sample_neighbors` (delegating to the C-ABI `impulse_snapshot_sample_neighbors` kernel with deterministic PCG32 seeding) and the [`impulse-gnn`](https://github.com/impulse-graph/impulse-gnn) showcase package sample $k$-hop mini-batches directly over memory-mapped CSR arrays without materializing the full graph in Python RAM.

!!! note "Installing `impulse-gnn`"
    `impulse_gnn` is maintained in the [impulse-graph/impulse-gnn](https://github.com/impulse-graph/impulse-gnn) showcase repository (see [PyTorch & GNN Showcase](../../showcase/gnn.md)). Clone it locally and install with `pip install -e .`.

```python
import torch
from impulse_gnn import ImpulseGnnDataset, ImpulseNeighborSampler

# Open citations.imps directly from NVMe via mmap
with ImpulseGnnDataset("citations.imps", relation_index=0) as dataset:
    # Expose mmap-backed CSR tensors
    row_offsets: torch.Tensor = dataset.row_offsets
    col_indices: torch.Tensor = dataset.col_indices

    # Multi-hop GraphSAGE fanout sampler (25 neighbors at hop 1, 10 at hop 2)
    # Delegates each hop to C++ snapshot.sample_neighbors with deterministic per-hop seeds
    sampler = ImpulseNeighborSampler(dataset, sizes=[25, 10], seed=42)

    batch_seeds = torch.arange(0, 1024, dtype=torch.int32)
    hop_edge_indices: list[torch.Tensor] = sampler.sample(batch_seeds)
    print(f"Sampled {len(hop_edge_indices)} hops; hop-0 shape: {hop_edge_indices[0].shape}")
```

### GPU Sliced ELLPACK (`0x05`) & Empirical SpMM Benchmarks

Standard CSR (`RAW_UINT32 = 0x00`) has variable row lengths that can cause warp divergence on power-law graphs. Optimizing a snapshot with `--encoding sliced_ellpack` (`0x05`) packs rows into 2D slice tiles for coalesced GPU reads.

On Apple M5 GPU (Metal) over a `100K`-node, `1M`-edge graph with `128`-dimensional `float32` features (see [PyTorch & GNN Showcase](../../showcase/gnn.md#3-empirical-benchmarks-apple-m5-gpu-metal)):

* **SciPy CPU `csr_matrix`**: `0.327 ms` open, `40.860 ms` SpMM (`1.0x` baseline).
* **PyTorch CPU CSR**: `0.571 ms` open, `16.515 ms` SpMM (`2.5x`).
* **Impulse Mapped CSR (`RAW_UINT32`, GPU)**: `0.224 ms` open, `4.435 ms` SpMM (`9.2x`).
* **Impulse Sliced ELLPACK (`0x05`, GPU)**: `0.247 ms` open, `0.005 ms` (`5 µs`) asynchronous command-buffer dispatch (`~0.8–1.2 ms` with `torch.mps.synchronize()`, `~35x–50x` faster than SciPy CPU).
* **Qwen 1.5 MoE Router Index (`3.72 GB` weights)**: `.imps` mounts in `0.400 ms` and evaluates first-token routing in `0.402 ms` with `0 Bytes` heap copy, compared to `16.433 ms` open and `305.788 ms` TTFT (`~3.72 GB` heap copy) for raw `safetensors`.

---

## 3. Embedding Ingestion & Embedded Vamana ANN (`v0.10.0`, Section 2.6 `0x08`)

Starting in `v0.10.0`, `.imps` natively embeds single-layer **DiskANN / Vamana proximity graphs** (`IMP_INDEX_VAMANA_ANN = 0x08`, magic `0x56414D41` `"VAMA"`) in Section 2.6 alongside `[N, D]` `float32` node attributes (see [Format Specification §3.5.2](../../reference/spec/format-specification.md)).

Each Vamana index stores:

1. **64-Byte `VamanaHeader`**: Metric (`l2`, `cosine`, `dot`, `hamming`), quantization mode (`none`, `bq1`, `sq8`, `fp16`), `max_degree_r` ($R$), `medoid_node_id` ($m^*$), diversity `alpha` ($\alpha$), and `ef_construction` ($L_{\text{build}}$).
2. **128-Byte-Aligned Fixed-Degree Adjacency Slab**: $N \times (R + 1) \times 4$ bytes (`[deg, nb_0, ..., nb_{deg-1}, 0xFFFFFFFF, ...]`) for branch-predictable fixed-stride neighbor fetches.
3. **128-Byte-Aligned Quantized Routing Slab**: Compact vector codes (`BQ1` 1-bit binary, `SQ8` 8-bit scalar, or `FP16` half-precision) scanned during beam search to cut DRAM bandwidth before exact `float32` reranking.

### 3.1 Building Snapshots with Embeddings & Vamana Indices

You can embed vectors and construct Section 2.6 Vamana indices in three ways via the `impulse` CLI (see [CLI Reference](../../reference/cli.md)):

=== "1. Build from `manifest.json` + `.npy` / `.parquet`"

    ```bash
    # Compile topology from manifest.json, attach L2-normalized 768-D NumPy embeddings,
    # and build an SQ8-quantized Vamana index (R=32, L=64, alpha=1.2) in a single pass:
    impulse build --manifest citation_manifest.json -o citations_vec.imps \
      --embeddings "Paper.embedding=paper_vecs.npy:format=npy:dim=768:norm=l2" \
      --vector-index "Paper.embedding:R=32:L=64:alpha=1.2:metric=cosine:quant=sq8"
    ```

=== "2. Attach Embeddings to an Existing `.imps`"

    ```bash
    # Attach .npy, .fvecs, .bvecs, .safetensors, .parquet, .jsonl, or .csv embeddings
    # to an already-compiled .imps snapshot without re-ingesting edge CSVs:
    impulse snapshot attach-embeddings \
      -i citations_base.imps \
      -o citations_vec.imps \
      --embeddings "Paper.embedding=paper_vecs.npy:dim=768:norm=l2" \
      --vector-index "Paper.embedding:R=32:L=64:alpha=1.2:metric=cosine:quant=sq8"
    ```

=== "3. Convert HuggingFace `.safetensors`"

    ```bash
    # Convert a .safetensors checkpoint directly into a domain with an embedded Vamana index:
    impulse snapshot convert-tensors \
      -i embeddings.safetensors \
      -o weights_vec.imps \
      --domain Paper \
      --vector-index "R=32:L=64:metric=cosine:quant=sq8"
    ```

### 3.2 Medoid BFS Cache-Locality Optimization (`--vamana-locality`)

During greedy beam search from `medoid_node_id`, consecutively visited proximity neighbors may have arbitrary original node IDs. Reordering domain dense IDs by BFS distance from the Vamana medoid co-locates early-beam neighbors onto shared CPU cache lines and remaps the Vamana graph in $O(N \cdot R + N \cdot D)$ without re-running $\alpha$-RNG construction:

```bash
impulse snapshot optimize \
  -i citations_vec.imps \
  -o citations_vec_opt.imps \
  --vamana-locality \
  --csc
```

---

## 4. Two-Stage Quantized Routing, Reranking & Hybrid Graph Search

Rather than maintaining a separate vector database and joining IDs over the network against a graph database, `ImpulseVM` executes **Hybrid Vector + Graph Traversals** inside one register pipeline using opcodes `0xCA` and `0xCB` (see [VM Specification §6.11.2](../../reference/spec/vm-specification.md)):

```mermaid
flowchart LR
    Q["Query Vector q (Float32[D])"] --> S1["Stage 1: OP_VECTOR_ANN_SEARCH (0xCA)\nGreedy beam walk over Vamana adj_slab\nusing BQ1 / SQ8 / FP16 routing codes"]
    S1 --> G["Multi-Hop Graph Walk & Filtering\nOP_CSR_WALK / OP_CSC_WALK / OP_LANE_CSR_WALK\n+ CEL Domain Attribute Predicates"]
    G --> S2["Stage 2: OP_VECTOR_RERANK_DOT (0xCB)\nExact SIMD Float32 dot-product reranking\non surviving candidate BitSet / Lanes only"]
    S2 --> OUT["Top-K Ranked Candidates"]
```

1. **Stage 1 — Compact Quantized Beam Routing (`OP_VECTOR_ANN_SEARCH` `0xCA`)**: Starts at `medoid_node_id` and traverses the Vamana `adj_slab` using compact `BQ1` ($32\times$ smaller than `float32`), `SQ8` ($4\times$ smaller), or `FP16` ($2\times$ smaller) routing codes, writing the top-$k$ seed candidates directly into a `TYPE_BITSET_HANDLE` (`0x04`) or bit-sliced `TYPE_LANE_FRONTIER` (`0x10`, when `flags & 1 != 0`).
2. **Multi-Hop Graph Expansion & Constraints**: Walks CSR/CSC relations (e.g., `Paper -[:CITES]-> Paper`, `Compound -[:BINDS]-> Gene`, or ReBAC authorization checks) and applies in-domain CEL filters (`year >= 2022`) to prune unauthorized or structurally irrelevant candidates.
3. **Stage 2 — Exact SIMD `Float32` Reranking (`OP_VECTOR_RERANK_DOT` `0xCB`)**: Reads full-precision `[N, D]` `float32` vectors *only* for surviving candidate nodes in the bitset/lane frontier and computes exact SIMD dot-product scores (`TYPE_FLOAT_VECTOR`).

!!! note "SDK Support for `0xCA` / `0xCB`"
    In `v0.10.0`, embedded Vamana search and two-stage reranking are exposed natively in C++20 (`DomainView::vectorSearch`, `MultiLaneBuilder::fromConceptVectors`, `QueryBuilder::vectorAnnSearch` / `vectorRerankDot` — see [C-ABI & C++20 Reference](../../reference/c-abi.md#51-multi-lane-bit-sliced-hybrid-vector-fluent-apis-v0100)) and Rust (`SnapshotReader::vamana_ann_search` — see [Rust Crate Reference](../../reference/rust-api.md#41-vamana-ann-graph-index-construction-permutation-two-stage-search-vamana-module-v0100)), as well as via `.impas` / `.impb` bytecode in `impulse run`. High-level Python wrapper methods on `impulse_graph.DomainView` for `0xCA`/`0xCB` are planned; Python workflows today build and benchmark Vamana snapshots via `impulse` CLI and access `[N, D]` embedding columns zero-copy via `Snapshot.get_attribute_array`.

### Benchmarking Recall, Quantization Tiers & Latency (`impulse bench-vector`)

Use `impulse bench-vector` (`impulse snapshot bench-vector`) to measure `Recall@1`, `Recall@K`, `nDCG@K`, `MRR`, and `p50`/`p95`/`p99` microsecond latency across all four quantization tiers (`NONE`, `FP16`, `SQ8`, `BQ1`) and compare pre- vs. post-`optimize` (`--vamana-locality` / `--rcm`) cache behavior against an exact brute-force oracle:

```bash
# 1. Synthetic community-manifold + homophily graph sweep across ef_search = 16, 32, 64
impulse bench-vector \
  -n 10000 -d 128 -c 24 -q 200 -k 10 \
  --max-degree 24 --ef-construction 64 --alpha 1.2 --metric cosine \
  --ef-search 16,32,64 --compare-optimize --format text

# 2. Benchmark an existing .imps snapshot and export structured JSON metrics
impulse snapshot bench-vector \
  --snapshot citations_vec_opt.imps \
  --embeddings paper_vecs.npy \
  -q 200 -k 10 \
  --ef-search 32,64,128 \
  --format json
```

---

## Next Steps

* **[Snapshots from Parquet & CSV](snapshots-from-parquet-csv.md)** — Full `manifest.json` specification for scalar and vector columns.
* **[Native CLI Optimization, Deep Audits & Signing](../native/cli-reference.md)** — Deep dive into `--rcm`, `--vamana-locality`, and `--deep-audit` Vamana invariant checks.
* **[PyTorch & GNN Showcase](../../showcase/gnn.md)** — Reproducing the Apple M5 GPU SpMM and Qwen 1.5 MoE router benchmarks.
* **[Python & PyTorch SDK Reference](../../reference/python-api.md)** — Complete Python API reference.
