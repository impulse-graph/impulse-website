# Showcase: PyTorch & Graph Neural Networks (`impulse-gnn`)

Using `.imps` as a storage format for PyTorch removes the decompression, ID-hashing, and multi-worker copy-on-write overhead of loading graphs from Parquet—and exposes native C-ABI neighborhood sampling directly inside Python.

---

## 1. `.imps` vs. `Parquet -> PyTorch`

| Capability | `Parquet -> PyTorch` | `Impulse (.imps) -> PyTorch` |
| :--- | :--- | :--- |
| **Startup** | Seconds to minutes (decompress, hash string keys, sort edges) | Direct `mmap` (`< 1 ms`); dense IDs and CSR/CSC are pre-compiled by `impulse build` |
| **Topology Footprint** | `16 bytes/edge` (`[2, E]` `int64` PyG `edge_index`) | `~4 bytes/edge` (`uint32` CSR `col_indices` + `row_offsets`) |
| **Multi-Worker `DataLoader`** | Forked workers trigger Python CoW page duplication | Workers share the same read-only OS page cache (`0 bytes` duplicated) |
| **Larger-Than-RAM Graphs** | Requires manual chunking (compressed pages cannot be pointer-indexed) | OS demand-pages 4KB blocks from NVMe automatically |

!!! note "Showcase Package (`impulse-gnn`)"
    `impulse_gnn` lives in the [impulse-gnn](https://github.com/impulse-graph/impulse-gnn) showcase repository (not published on PyPI). Install it from a local clone with `pip install -e .`.

```python
from impulse_gnn import ImpulseGnnDataset

# Compile once via CLI: impulse build --manifest manifest.json -o graph.imps
with ImpulseGnnDataset("graph.imps", relation_index=0) as dataset:
    row_offsets = dataset.row_offsets  # torch.Tensor backed by mmap
    col_indices = dataset.col_indices  # torch.Tensor backed by mmap
```

---

## 2. Native Sampling & Sparse Ops

With the snapshot mapped, `impulse-gnn` delegates sampling and sparse exports to the C-ABI kernel:

* **$k$-Hop Neighborhood Sampling (`ImpulseNeighborSampler`)**: Calls `snapshot.sample_neighbors` in C++ over the CSR arrays rather than Python loops.
* **Subgraph Filtering (Planned)**: `OP_CSR_WALK_STREAM` supports CEL edge/node predicates in `ImpulseVM`; exposing it directly on `ImpulseNeighborSampler` is planned.
* **Structural Features**: Compute reachability, degrees, connected components, or `ImpK` features in `ImpulseVM` and pass the result straight into PyTorch.
* **GPU Sliced ELLPACK (`0x05`)**: `create_sliced_ellpack_matrix` packs CSR into 2D tiles for coalesced GPU reads on power-law graphs.

```python
from impulse_gnn import ImpulseGnnDataset, ImpulseNeighborSampler

with ImpulseGnnDataset("graph.imps", relation_index=0) as dataset:
    sampler = ImpulseNeighborSampler(dataset, sizes=[25, 10])
    subgraphs = sampler.sample(target_nodes=[42, 100, 256])

    csr_mat = dataset.to_scipy_csr()
```

---

## 3. Empirical Benchmarks (Apple M5 GPU / Metal)

### Sparse Matrix Multiplication (`SpMM` — 100K Nodes, 1M Edges, 128-Dim Features)

| Implementation & Format | Layout & Device | Open Latency | `SpMM` Latency (p50) | Speedup |
| :--- | :--- | :--- | :--- | :--- |
| **SciPy Baseline (`csr_matrix`)** | In-RAM CSR (CPU) | `0.327 ms` | `40.860 ms` | `1.0x` |
| **PyTorch CPU CSR** | PyTorch CSR (CPU) | `0.571 ms` | `16.515 ms` | `2.5x` |
| **Impulse CSR (`RAW_UINT32`)** | Mapped CSR (GPU) | **`0.224 ms`** | **`4.435 ms`** | **9.2x** |
| **Impulse Sliced ELLPACK (`0x05`)** | 2D Slice Tiles (GPU) | **`0.247 ms`** | **`0.005 ms` (5 µs)\*** | **8,417x (Launch)\*** |

*\*The 5 µs figure reflects CPU command-buffer dispatch on Apple MPS without synchronization. With `torch.mps.synchronize()`, full GPU completion takes ~0.8–1.2 ms (~35x–50x faster than SciPy CPU).*

### Routing Topology Mounting (Qwen 1.5 MoE Router Index)

| Engine | Disk Size | Open Latency | Router Evaluation (TTFT) | Heap Copy |
| :--- | :--- | :--- | :--- | :--- |
| **Standard `safetensors`** | `3.72 GB` | `16.433 ms` | `305.788 ms` | `~3.72 GB` |
| **Impulse (`.imps`)** | **`0.01 MB (Topology Index)`** | **`0.400 ms`** | **`0.402 ms`** | **`0 Bytes`** |

---

## 4. Reproducing Locally

```bash
git clone https://github.com/impulse-graph/impulse-gnn.git
cd impulse-gnn
python3 -m venv venv && source venv/bin/activate
pip install pybind11 pytest numpy scipy torch
pip install --no-build-isolation -e ../impulse-graph-core/impulse-python
pip install --no-build-isolation -e .

python examples/qwen_moe_real_ttft_benchmark.py
```
