# Python & PyTorch SDK Reference (`impulse-graph`)

The `impulse-graph` Python SDK embeds the native C++20 `ImpulseVM` kernel via `pybind11` and exposes zero-copy `mmap` access to `.imps` binary snapshots, NumPy array views, and PyTorch `torch.from_dlpack` tensor descriptors.

---

## 1. Installation

```bash
pip install impulse-graph
```

Pre-built wheels (`manylinux_2_28_x86_64`, `manylinux_2_28_aarch64`, `macosx_11_0_arm64`) statically embed `libimpulse_graph_static.a` with zero external runtime dependencies.

---

## 2. Opening Snapshots & Domain-Anchored Traversals

```python
from impulse_graph import Snapshot

with Snapshot("commerce.imps") as snap:
    print("Domains:", snap.domain_count(), "Relations:", snap.relation_count())

    # 1. Domain-anchored fluent traversal with inline CEL filtering
    recommended_skus = (
        snap.domain("User")
            .from_keys(["usr_alice"])
            .out("PURCHASED", filter="edge.amount >= 50.0")
            .in_("PURCHASED")
            .out("PURCHASED")
            .filter("node.in_stock == true")
            .to_keys()
    )

    # 2. Unbounded fixed-point reachability (transitive closure, zero lambdas)
    ancestors = (
        snap.domain("Group")
            .from_key("grp_engineering_west")
            .repeat_until_stable("PARENT_GROUP")
            .to_keys()
    )
```

### `Snapshot` Methods

| Method | Description |
| :--- | :--- |
| **`Snapshot(path: str)`** | Memory-map `.imps` file read-only (`MAP_SHARED`). Supports `with` context manager. |
| **`domain(name: str) -> DomainView`** | Bind traversal anchor to the named domain's $0 \dots N_d-1$ dense ID space. |
| **`domain_count() -> int`** | Total node domains in Section 2 catalog. |
| **`relation_count() -> int`** | Total edge relations in Section 2 directory. |
| **`is_reachable(rel_idx: int, src_id: int, tgt_id: int) -> bool`** | Direct $O(\log d)$ / $O(1)$ CSR adjacency check. |
| **`get_row_offsets_array(rel_idx: int) -> np.ndarray`** | Zero-copy NumPy view over 128-byte-aligned CSR `row_offsets`. |
| **`get_col_indices_array(rel_idx: int) -> np.ndarray`** | Zero-copy NumPy view over 128-byte-aligned CSR `col_indices`. |
| **`get_attribute_dlpack(domain: str, attr: str)`** | Export 128-byte-aligned SoA attribute or vector column via zero-copy DLPack. |
| **`sample_neighbors(rel_idx: int, nodes, k: int, seed: int = 42)`** | Native SIMD $K$-hop neighborhood sampler returning `(row_ptr, col_idx)` NumPy/tensor views. |
| **`prepare(query: str) -> Statement`** | Compile a parameterized `openCypher`, `ImpLog`, `ImpK`, or `ImpScheme` query. |

---

## 3. Zero-Copy PyTorch & NumPy Integration

Because `.imps` aligns all CSR topology arrays and Structure-of-Arrays (SoA) attribute columns to **128-byte boundaries**, PyTorch and NumPy read them directly from the OS page cache with **0 bytes of heap serialization**:

```python
import torch
from impulse_graph import Snapshot

snap = Snapshot("ogbn_papers100M.imps")

# 1. Zero-copy 128-D float32 node embeddings (N x 128) via DLPack
x_embeddings = torch.from_dlpack(snap.get_attribute_dlpack("Paper", "feat_128"))

# 2. Zero-copy CSR topology arrays
row_ptr = torch.from_numpy(snap.get_row_offsets_array(0))
col_idx = torch.from_numpy(snap.get_col_indices_array(0))

# 3. Native SIMD neighborhood sampling for GNN mini-batches (25,000+ batches/sec)
seed_nodes = torch.tensor([10, 42, 105, 891], dtype=torch.int64)
sub_row_ptr, sub_col_idx = snap.sample_neighbors(
    relation_index=0, nodes=seed_nodes, k_samples=15, seed=42
)
```

---

## 4. Parameterized Prepared Statements (`snap.prepare`)

```python
with snap.prepare("""
    MATCH (u:User)-[:PURCHASED]->(p:Product)
    WHERE u._key = $userKey AND p.price <= $maxPrice
    RETURN p._id, p.price
""") as stmt:
    stmt.bind_str("userKey", "usr_alice")
    stmt.bind_float("maxPrice", 99.95)

    result = stmt.execute()
    product_ids = result.column_array(0)   # Zero-copy NumPy uint64 array
    prices      = result.column_array(1)   # Zero-copy NumPy float64 array
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
