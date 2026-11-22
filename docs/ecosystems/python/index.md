# Python, Data Science & ML Hub

The `impulse-graph` Python SDK embeds the C++20 `ImpulseVM` kernel via `pybind11` and maps immutable `.imps` binary snapshots directly off-heap. It lets Python data scientists, quantitative researchers, and ML engineers run multi-hop traversals, `openCypher` queries, and PyTorch/SciPy sparse matrix operations without loading edge dictionaries into the Python heap or duplicating graph memory across worker processes.

---

## 1. Guide Map

| Guide | Focus |
| :--- | :--- |
| **[From NetworkX & Parquet in 5 Minutes](../../getting-started/from-networkx-and-parquet.md)** | End-to-end quickstart exporting DataFrames or NetworkX graphs to `.imps` and querying them in Python. |
| **[Snapshots from Parquet & CSV](snapshots-from-parquet-csv.md)** | Complete `manifest.json` reference, `impulse build` pipeline, and CSV/Parquet-to-`.imps` compilation. |
| **[PyTorch GNN Sampling, Embeddings & Vamana Vector Search](gnn-and-vector-search.md)** | Zero-copy `torch.Tensor` views, native C-ABI neighborhood sampling, Section 2.6 Vamana ANN (`0x08`), and two-stage quantized hybrid search. |
| **[Python & PyTorch SDK Reference](../../reference/python-api.md)** | Full API table for `Snapshot`, `DomainView`, `Traversal`, `impulse_graph.vm.QueryBuilder`, and `Writer`. |
| **[Polyglot Workflow](../../getting-started/polyglot-workflow.md)** · **[Ecosystems Overview](../index.md)** | Sharing a single `.imps` artifact across Python ETL, Rust/C++ engines, and Java 25 microservices. |

---

## 2. Installation (Zero JVM or Server Dependencies)

Install the pre-built `impulse-graph` wheel from PyPI. Wheels for Linux (`manylinux` `x86_64`/`aarch64`), macOS (`macosx_11_0_arm64`), and Windows (`win_amd64`) statically embed `libimpulse_graph_static.a` with zero external C++ runtime dependencies:

```bash
pip install impulse-graph==0.10.0
```

To compile multi-million-edge `.parquet`, `.csv`, or `.tsv` tables into `.imps` snapshots from the command line, install the standalone `impulse-graph` (`impulse`) CLI binary from [GitHub Releases](https://github.com/impulse-graph/impulse-graph-core/releases) or Cargo:

```bash
# Optional standalone CLI for Parquet/CSV compilation, RCM optimization, and validation
cargo install --git https://github.com/impulse-graph/impulse-graph-core impulse-cli
alias impulse="impulse-graph"
```

---

## 3. Sub-Millisecond Off-Heap Mounting (`< 1 ms`)

Opening an `.imps` file calls `mmap` (`MAP_SHARED`, read-only) on 128-byte-aligned CSR/CSC topology arrays and Structure-of-Arrays (SoA) attribute columns. No Python `dict` objects are allocated, and native `ImpulseVM` execution releases the Python GIL (`py::gil_scoped_release`):

```python
from impulse_graph import Snapshot

with Snapshot("hetionet.imps") as snap:
    print(f"Domains: {snap.domain_count()}, Relations: {snap.relation_count()}")
```

In empirical benchmarks on the Hetionet biomedical graph (`47K` nodes, `2.25M` edges; see [Benchmarks](../../benchmarks.md#22-multi-language-ffi-binding-overhead-hetionet-biomedical-graph-47k-nodes-225m-edges)):

* **Cold Open Latency**: `< 1 ms` (`0.224 ms`–`0.400 ms`) via `mmap`, vs. `450 ms` for PyTorch Geometric in-memory CSR loading and `1,850 ms` for NetworkX dictionary construction.
* **4-Hop Drug-Repurposing Traversal**: `24.2 µs` mean latency in Python (`impulse-python`), vs. `850.0 µs` (`35x` slower) in PyTorch Geometric CSR and `42,100.0 µs` (`1,739x` slower) in NetworkX.

---

## 4. Domain-Bound Fluent Traversals & Parameterized `openCypher`

Every node domain in Impulse Graph (`User`, `Account`, `Gene`, `Compound`) owns an independent `0 .. N_d - 1` dense integer ID space. Anchor queries to an explicit domain via `snap.domain(...)` so key lookups, relation transitions, and attribute filters resolve against the active domain's catalog:

```python
from impulse_graph import Snapshot

with Snapshot("banking.imps") as snap:
    users = snap.domain("User")

    # 1. Domain-bound Kleisli set traversal:
    #    Resolve "usr_101" -> walk OWNS -> walk TRANSFERRED_TO -> filter active Account domain
    recipient_keys = (
        users.from_key("usr_101")
             .out("OWNS")
             .out("TRANSFERRED_TO")
             .filter("account.balance >= 1000.0")
             .to_key_list()
    )

    # 2. Inspect generated ImpAsm (.impas) register instructions for any pipeline
    asm_listing = (
        users.from_key("usr_101")
             .out("OWNS")
             .out("TRANSFERRED_TO")
             .to_impas()
    )

    # 3. Declarative parameterized openCypher over the same off-heap snapshot
    uid = users.to_dense_id("usr_101")
    account_dense_ids = snap.cypher(
        """
        MATCH (u:User)-[:OWNS]->(src:Account)-[:TRANSFERRED_TO]->(dst:Account)
        WHERE u.id = $uid
        RETURN dst
        """,
        params={"uid": uid},
    )
```

!!! warning "Avoid Client-Side Imperative Point-Lookup Loops"
    Never iterate over node IDs in a Python `for` loop calling single-node neighbor lookups hop-by-hop. Crossing the Python/C boundary per node discards SIMD bitset vectorization and cache locality. Express multi-hop walks, CEL `.filter(...)` predicates, and fixed-point loops (`impulse_graph.vm.QueryBuilder.repeat_until_stable`) inside a single engine pipeline.

---

## 5. Multi-Process Workers & PyTorch `DataLoader` (`0 Bytes` RAM Duplication)

When Python `multiprocessing` or a PyTorch `DataLoader` (`num_workers > 0`) forks worker processes over a standard Python `dict` or NumPy heap array, reference-count updates on Python objects trigger OS Copy-on-Write (`CoW`) page faults—multiplying a `20 GB` graph into `160 GB` of physical RAM across 8 workers.

With `.imps`, pass only the **file path string** to workers and open `Snapshot(path)` lazily inside each worker process. The operating system maps every worker onto the **exact same read-only physical page-cache frames**:

```python
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from impulse_graph import Snapshot


class SubgraphBatchDataset(Dataset):
    def __init__(self, imps_path: str, seed_nodes: np.ndarray, k_neighbors: int = 15):
        self.imps_path = imps_path      # Pickle only the path string across processes
        self.seed_nodes = seed_nodes
        self.k_neighbors = k_neighbors
        self._snap: Snapshot | None = None

    def _ensure_open(self) -> Snapshot:
        if self._snap is None:
            # Mapped read-only (MAP_SHARED) inside each worker process; shares OS page cache
            self._snap = Snapshot(self.imps_path)
        return self._snap

    def __len__(self) -> int:
        return len(self.seed_nodes)

    def __getitem__(self, idx: int):
        snap = self._ensure_open()
        seed = int(self.seed_nodes[idx])
        src, tgt = snap.sample_neighbors(
            relation_index=0, nodes=[seed], k_samples=self.k_neighbors, seed=42 + idx
        )
        return torch.from_numpy(src.astype(np.int64)), torch.from_numpy(tgt.astype(np.int64))


if __name__ == "__main__":
    seeds = np.arange(0, 10_000, dtype=np.uint64)
    ds = SubgraphBatchDataset("citations.imps", seeds, k_neighbors=15)
    # 4 worker processes share one OS page-cache mapping of citations.imps
    loader = DataLoader(ds, batch_size=64, num_workers=4, persistent_workers=True)
```

---

## 6. Zero-Copy NumPy, SciPy CSR & DataFrame Views

All CSR/CSC arrays (`row_offsets`, `col_indices`) and fixed-width SoA attribute columns in `.imps` implement the Python buffer protocol (`memoryview` $\to$ `np.frombuffer`), exposing read-only NumPy and SciPy views directly over mapped pages:

```python
import numpy as np
from impulse_graph import Snapshot

with Snapshot("citations.imps") as snap:
    # 1. Zero-copy uint32 CSR views (no heap allocation)
    row_offsets: np.ndarray = snap.get_row_offsets_array(relation_index=0)
    col_indices: np.ndarray = snap.get_col_indices_array(relation_index=0)

    # 2. Zero-copy SoA edge weight vector [E] or node embedding matrix [N, D]
    edge_count = snap.get_relation(0)["edge_count"]
    weights: np.ndarray = snap.get_attribute_array(
        relation_index=0, attribute_index=0, dtype=np.float32, shape=(edge_count,)
    )

    # 3. Direct interop with SciPy sparse linear algebra, PyTorch, Polars, and PyArrow
    scipy_csr = snap.to_scipy_csr(relation_index=0)
    torch_csr = snap.to_torch_csr(relation_index=0)
    arrow_tbl = snap.to_arrow_table(relation_index=0)
    polars_df = snap.to_polars(relation_index=0)
```

---

## Next Steps

* **[From NetworkX & Parquet in 5 Minutes](../../getting-started/from-networkx-and-parquet.md)** — Convert an existing DataFrame or NetworkX prototype into an `.imps` snapshot.
* **[Snapshots from Parquet & CSV](snapshots-from-parquet-csv.md)** — Author multi-domain `manifest.json` pipelines and optimize cache locality with `--rcm`.
* **[PyTorch GNN Sampling, Embeddings & Vamana Vector Search](gnn-and-vector-search.md)** — Train GNNs on graphs larger than RAM and run embedded two-stage quantized ANN search.
* **[Python & PyTorch SDK Reference](../../reference/python-api.md)** — Complete method signatures and low-level `impulse_graph.vm` register builder.
