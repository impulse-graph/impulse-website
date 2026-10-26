# Python & PyTorch SDK Reference (`impulse-graph`)

The `impulse-graph` Python SDK embeds the native C++20 `ImpulseVM` kernel via `pybind11` and exposes zero-copy `mmap` access to `.imps` binary snapshots, NumPy array views, and PyTorch `torch.from_dlpack` tensor descriptors.

---

## 1. Installation

```bash
pip install impulse-graph
```

Pre-built wheels (`manylinux_2_28_x86_64`, `manylinux_2_28_aarch64`, `macosx_11_0_arm64`) statically embed `libimpulse_graph_static.a` with zero external runtime dependencies.

---

## 2. Opening Snapshots & Fluent Traversals

```python
from impulse_graph import Snapshot

with Snapshot("commerce.imps") as snap:
    print("Domains:", snap.domain_count(), "Relations:", snap.relation_count())

    # 1. Fluent multi-hop traversal (User 0 -> PURCHASED -> <-PURCHASED -> PURCHASED)
    recommended_items = (
        snap.traverse(start_node=0, catalog={"PURCHASED": 0})
            .out("PURCHASED")
            .in_("PURCHASED")
            .out("PURCHASED")
            .to_list()
    )

    # 2. Declarative openCypher query execution
    buyers = snap.cypher(
        "MATCH (u:User)-[:PURCHASED]->(p:Product) WHERE u.id = $uid RETURN p",
        params={"uid": 0},
        catalog={"PURCHASED": 0},
    )
```

### `Snapshot` Methods

| Method | Description |
| :--- | :--- |
| **`Snapshot(path: str)`** | Memory-map `.imps` file read-only (`MAP_SHARED`). Supports `with` context manager. |
| **`domain_count() -> int`** | Total node domains in Section 2 catalog. |
| **`relation_count() -> int`** | Total edge relations in Section 2 directory. |
| **`max_node_count() -> int`** | Maximum node count across all domains in the snapshot. |
| **`is_reachable(rel_idx: int, src_id: int, tgt_id: int) -> bool`** | Direct $O(\log d)$ / $O(1)$ CSR adjacency check. |
| **`traverse(start_node: int, catalog=None) -> Traversal`** | Start a fluent multi-hop traversal from `start_node` (`.out(rel)`, `.in_(rel)`, `.filter(...)`, `.to_list()`, `.to_set()`, `.count()`, `.contains(id)`, `.to_impas()`). |
| **`cypher(query: str, params=None, catalog=None) -> List[int]`** | Compile and execute a read-only `openCypher` query, returning surviving target node IDs. |
| **`get_row_offsets_array(rel_idx: int) -> np.ndarray`** | Zero-copy NumPy view (`uint32`) over 128-byte-aligned CSR `row_offsets`. |
| **`get_col_indices_array(rel_idx: int) -> np.ndarray`** | Zero-copy NumPy view (`uint32`) over 128-byte-aligned CSR `col_indices`. |
| **`get_attribute_array(rel_idx: int, attr_idx: int, dtype=np.float32, shape=None) -> np.ndarray`** | Zero-copy NumPy view over 128-byte-aligned SoA attribute or `[N, D]` vector column. |
| **`sample_neighbors(rel_idx: int, src_nodes, k: int, seed: int = 42)`** | Native SIMD $K$-hop neighborhood sampler returning `(sampled_src, sampled_tgt)` NumPy arrays. |
| **`to_torch_csr(rel_idx: int)` / `to_torch_edge_index(rel_idx: int)`** | Export relation directly to PyTorch `sparse_csr_tensor` or `[2, E]` `edge_index` tensor. |
| **`to_scipy_csr(rel_idx: int)` / `to_networkx(rel_idx: int)`** | Export relation to `scipy.sparse.csr_matrix` or `networkx.DiGraph`. |
| **`to_arrow_table(rel_idx: int)` / `to_polars(rel_idx: int)` / `to_pandas(rel_idx: int)`** | Export relation edge list to PyArrow Table, Polars DataFrame, or Pandas DataFrame. |

---

## 3. Zero-Copy PyTorch & NumPy Integration

Because `.imps` aligns all CSR topology arrays and Structure-of-Arrays (SoA) attribute columns to **128-byte boundaries**, PyTorch and NumPy read them directly from the OS page cache with **0 bytes of heap serialization**:

```python
import numpy as np
import torch
from impulse_graph import Snapshot

with Snapshot("ogbn_papers100M.imps") as snap:
    # 1. Zero-copy 128-D float32 node embeddings (N x 128) via NumPy buffer protocol
    num_nodes = snap.max_node_count()
    feat_np = snap.get_attribute_array(0, 0, dtype=np.float32, shape=(num_nodes, 128))
    x_embeddings = torch.from_numpy(feat_np)

    # 2. Zero-copy CSR topology tensors
    csr_tensor = snap.to_torch_csr(0)

    # 3. Native SIMD neighborhood sampling for GNN mini-batches
    seed_nodes = np.array([10, 42, 105, 891], dtype=np.uint64)
    sampled_src, sampled_tgt = snap.sample_neighbors(
        relation_index=0, src_nodes=seed_nodes, k=15, seed=42
    )
```

---

## 4. Low-Level VM Bytecode Builder (`impulse_graph.vm`)

For custom register-level `impOps` pipelines (such as `repeat_until_stable`, set intersections, or GraphBLAS `matrix_vector_mul`), use `impulse_graph.vm.QueryBuilder`:

```python
from impulse_graph import Snapshot, vm

with Snapshot("commerce.imps") as snap:
    ctx = vm.VmContext(snap)
    state = vm.VmState()
    state.set_query_context(ctx)

    qb = vm.QueryBuilder()
    query = (
        qb.init_input_node(0)
          .walk_edge(0, 1, 0)
          .repeat_until_stable(1, 2, 0)
          .collect_bitset(3, 2)
          .compile()
    )
    res = query.execute(state, input_param=0)
```

---

## 5. Streaming Snapshot Writer (`Writer`)

For programmatic `.imps` construction in Python (see also `impulse snapshot build` in [Building Snapshots (CLI & Python)](../getting-started/snapshot-builder-reference.md)):

```python
import numpy as np
from impulse_graph import Writer

with Writer("graph.imps") as writer:
    writer.add_domain(domain_id=0, key_type=4, name="User")
    writer.add_relation(
        src_domain_id=0,
        tgt_domain_id=0,
        encoding_type=0,
        node_count=4,
        edge_count=4,
        section_features=0,
        row_offsets=np.array([0, 2, 3, 3, 4], dtype=np.uint32),
        col_indices=np.array([1, 2, 3, 0], dtype=np.uint32),
    )
    writer.finalize()
```
