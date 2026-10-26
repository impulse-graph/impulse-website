# Building Snapshots (CLI, CSV/Parquet & Python/PyTorch)

If you use **Python, PyTorch, C/C++, Rust, Go, C#, or Node.js**—or simply want to compile `.imps` snapshots from **Apache Parquet, CSV, or TSV** files without writing Java code—the standalone **`impulse` CLI (`impulse-graph-tooling`)** is the fastest way to build, inspect, validate, and optimize snapshots.

!!! tip
    **Looking for the programmatic Java `SnapshotBuilder` & streaming JDBC guide?** See **[Building Snapshots in Java](building-snapshots.md)**. Both the Java `SnapshotBuilder` and the Rust `impulse` CLI produce 100% bitwise-compatible `.imps` files that can be memory-mapped by any language SDK.

---

## 1. How `impulse build` Works

Instead of writing imperative ingestion code, you export your node and edge tables from **DuckDB, Pandas, Polars, PyArrow, Spark, Snowflake, or PostgreSQL** to **Apache Parquet (`.parquet`)** or **CSV/TSV (`.csv`, `.tsv`)**, describe your domains and relations in a declarative `manifest.json`, and run:

```bash
impulse build --manifest manifest.json -o graph.imps
```

Under the hood, `impulse build` automatically:

1. **Assigns Contiguous Dense IDs ($0 \dots N_d-1$) per Domain**: Scans your node files (or derives unique node keys directly from your edge files) and builds an embedded Minimal Perfect Hash (`_domain_index`) table for $O(1)$ key-to-dense-ID resolution at query time.
2. **Sorts Edges into Forward CSR & Reorders Edge Attributes**: Sorts edges by `(src_dense_id, tgt_dense_id)` to build the Compressed Sparse Row (`row_offsets[]`, `col_indices[]`) arrays and reorders all edge attribute columns in lockstep so `edge_attr[k]` aligns with `col_indices[k]`.
3. **Optionally Builds Reverse CSC (`"include_csc": true`)**: Transposes the CSR matrix into Compressed Sparse Column arrays so reverse traversals (`.in(...)` and `<-[]-` in openCypher) run at the exact same speed as forward traversals.
4. **Aligns All Sections to 128 Bytes**: Pads every CSR/CSC array, Structure-of-Arrays (SoA) attribute column, and fixed-width vector embedding to 128-byte boundaries (2 CPU cache lines / AVX-512 / GPU `cuFile` warp alignment) and seals the snapshot with a Page 0 header and SHA-256 footer.

### Installing the `impulse` CLI

```bash
# macOS / Linux (Homebrew)
brew install impulse-graph/tap/impulse-cli

# Or build directly from source (Rust 1.80+)
cargo install --git https://github.com/impulse-graph/impulse-graph-tooling.git
```

---

## 2. Walkthrough 1: From CSV Files to Python Queries

Let's build the exact same **banking graph** (`User -[:OWNS]-> Account -[:TRANSFERRED_TO {amount}]-> Account`) from the [Java Builder Guide](building-snapshots.md), using CSV files and querying it in Python.

```
 (User: "usr_101") ──[:OWNS]──> (Account: "acc_5001") ──[:TRANSFERRED_TO {amount: 2500.00}]──> (Account: "acc_7008")
```

### Step 1: Prepare the CSV Files

Create four CSV files in a `bank_data/` directory:

=== "`bank_data/users.csv`"

    ```csv
    user_id,name,age,risk_score
    usr_101,Alice,34,0.12
    usr_102,Bob,29,0.05
    usr_103,Charlie,52,0.88
    ```

=== "`bank_data/accounts.csv`"

    ```csv
    account_id,balance
    acc_5001,14200.50
    acc_6004,890.00
    acc_7008,53100.00
    ```

=== "`bank_data/owns.csv`"

    ```csv
    user_id,account_id
    usr_101,acc_5001
    usr_102,acc_6004
    usr_103,acc_7008
    ```

=== "`bank_data/transfers.csv`"

    ```csv
    from_account,to_account,amount,timestamp_ms
    acc_5001,acc_6004,450.00,1711929600000
    acc_5001,acc_7008,2500.00,1711933200000
    acc_6004,acc_7008,1200.00,1711936800000
    ```

### Step 2: Create `manifest.json`

Create `bank_data/manifest.json` mapping the two domains (`User` = `0`, `Account` = `1`), their node attributes, and the two directed relations (`OWNS` and `TRANSFERRED_TO`):

```json
{
  "domains": [
    {
      "id": 0,
      "name": "User",
      "key_type": "string",
      "file": "bank_data/users.csv",
      "id_column": "user_id",
      "attributes": [
        { "name": "name", "column": "name", "type": "string" },
        { "name": "age", "column": "age", "type": "int32" },
        { "name": "risk_score", "column": "risk_score", "type": "float32" }
      ]
    },
    {
      "id": 1,
      "name": "Account",
      "key_type": "string",
      "file": "bank_data/accounts.csv",
      "id_column": "account_id",
      "attributes": [
        { "name": "balance", "column": "balance", "type": "float64" }
      ]
    }
  ],
  "relations": [
    {
      "name": "OWNS",
      "src_domain": 0,
      "tgt_domain": 1,
      "file": "bank_data/owns.csv",
      "src_column": "user_id",
      "tgt_column": "account_id",
      "include_csc": true
    },
    {
      "name": "TRANSFERRED_TO",
      "src_domain": 1,
      "tgt_domain": 1,
      "file": "bank_data/transfers.csv",
      "src_column": "from_account",
      "tgt_column": "to_account",
      "include_csc": true,
      "attributes": [
        { "name": "amount", "column": "amount", "type": "float64" },
        { "name": "timestamp_ms", "column": "timestamp_ms", "type": "int64" }
      ]
    }
  ]
}
```

### Step 3: Build, Inspect & Validate

Run `impulse build` to compile `banking.imps`, then verify its 128-byte hardware alignment and schema metadata:

```bash
# 1. Compile CSVs into a zero-copy .imps binary snapshot
impulse build --manifest bank_data/manifest.json -o banking.imps

# 2. Inspect domains, relations, attribute columns, and section offsets
impulse snapshot inspect banking.imps --verbose

# 3. Verify 128-byte alignment, monotonic CSR offsets, and SHA-256 checksum
impulse snapshot validate banking.imps --strict-alignment
```

### Step 4: Memory-Map and Query in Python

Now open `banking.imps` in Python (`pip install impulse-graph`). The file is memory-mapped in `< 1 ms` with zero parsing:

```python
from impulse_graph import Snapshot

with Snapshot("banking.imps") as snap:
    print(f"Domains: {snap.domain_count()}, Relations: {snap.relation_count()}")

    # 1. Fluent Traversal from User dense ID 0 ("usr_101"):
    # Walk OWNS -> walk TRANSFERRED_TO -> return reached Account dense IDs
    reached_accounts = (
        snap.traverse(start_node=0, catalog={"OWNS": 0, "TRANSFERRED_TO": 1})
            .out("OWNS")
            .out("TRANSFERRED_TO")
            .to_list()
    )
    print("Accounts reached from User 0:", reached_accounts)

    # 2. Parameterized openCypher Query over the same memory-mapped snapshot:
    high_value_recipients = snap.cypher(
        """
        MATCH (u:User)-[:OWNS]->(src:Account)-[:TRANSFERRED_TO]->(dst:Account)
        WHERE u.id = $user_id
        RETURN dst
        """,
        params={"user_id": 0},
        catalog={"OWNS": 0, "TRANSFERRED_TO": 1},
    )
    print("Destination Account dense IDs:", high_value_recipients)
```

---

## 3. Walkthrough 2: From Apache Parquet to Zero-Copy PyTorch & GNNs

If your data lives in **Apache Parquet** (exported from PyArrow, Pandas, Polars, DuckDB, or Spark) and your destination is **PyTorch / PyTorch Geometric (PyG)**, `impulse build` reads `.parquet` files natively—including **fixed-size vector embeddings (`FixedSizeListArray`)** and **nullable Arrow validity bitmaps**.

Once compiled into an `.imps` file, your PyTorch training script memory-maps the graph in `< 1 ms` via `torch.from_dlpack()`, sharing a single physical OS page cache across all `DataLoader` workers with **zero RAM duplication**—even on graphs larger than physical system RAM.

### Step 1: Export Node & Edge Tables to Parquet (Python / PyArrow)

Here we generate a synthetic citation graph (`papers.parquet` with 128-dimensional `float32` feature vectors and `citations.parquet` with edge weights):

```python
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

num_papers = 10_000
num_edges = 80_000
feat_dim = 128

# 1. Build papers.parquet with scalar attributes + 128-D float32 embedding column
rng = np.random.default_rng(42)
flat_features = rng.standard_normal(num_papers * feat_dim, dtype=np.float32)
feature_list_array = pa.FixedSizeListArray.from_arrays(pa.array(flat_features), feat_dim)

papers_table = pa.table({
    "paper_id": pa.array([f"paper_{i}" for i in range(num_papers)], type=pa.string()),
    "year": pa.array(rng.integers(2015, 2026, size=num_papers, dtype=np.int32)),
    "label": pa.array(rng.integers(0, 10, size=num_papers, dtype=np.int32)),
    "features": feature_list_array,
})
pq.write_table(papers_table, "papers.parquet")

# 2. Build citations.parquet (directed edges: citing_id -> cited_id)
src_idx = rng.integers(0, num_papers, size=num_edges)
tgt_idx = rng.integers(0, num_papers, size=num_edges)
citations_table = pa.table({
    "citing_id": pa.array([f"paper_{i}" for i in src_idx], type=pa.string()),
    "cited_id": pa.array([f"paper_{i}" for i in tgt_idx], type=pa.string()),
    "weight": pa.array(rng.uniform(0.1, 1.0, size=num_edges).astype(np.float32)),
})
pq.write_table(citations_table, "citations.parquet")
```

### Step 2: Create `citation_manifest.json`

Point `domains` and `relations` directly at the `.parquet` files. Notice `"dimension": 128` on the `features` attribute—`impulse build` writes the 128-dimensional `float32` vectors as a contiguous, 128-byte-aligned `[N, 128]` tensor block inside the `.imps` file:

```json
{
  "domains": [
    {
      "id": 0,
      "name": "Paper",
      "key_type": "string",
      "file": "papers.parquet",
      "format": "parquet",
      "id_column": "paper_id",
      "attributes": [
        { "name": "year", "column": "year", "type": "int32" },
        { "name": "label", "column": "label", "type": "int32" },
        { "name": "features", "column": "features", "type": "float32", "dimension": 128 }
      ]
    }
  ],
  "relations": [
    {
      "name": "CITES",
      "src_domain": 0,
      "tgt_domain": 0,
      "file": "citations.parquet",
      "format": "parquet",
      "src_column": "citing_id",
      "tgt_column": "cited_id",
      "include_csc": true,
      "attributes": [
        { "name": "weight", "column": "weight", "type": "float32" }
      ]
    }
  ]
}
```

### Step 3: Compile & Optimize CSR Locality (`--rcm`)

Compile the Parquet files into an `.imps` snapshot, and optionally run `impulse snapshot optimize --rcm` (Reverse Cuthill-McKee bandwidth reduction) so that densely connected nodes are placed adjacent to one another in memory for higher L2/L3 cache hit rates during GNN message passing:

```bash
# 1. Compile Parquet files into raw .imps snapshot
impulse build --manifest citation_manifest.json -o citations_raw.imps

# 2. Reorder dense IDs with Reverse Cuthill-McKee (RCM) to minimize CSR cache misses
impulse snapshot optimize -i citations_raw.imps -o citations.imps --rcm --csc

# 3. Inspect degree distribution & supernodes
impulse snapshot stats citations.imps --supernode-threshold 500
```

### Step 4: Mount Zero-Copy in PyTorch (`impulse-gnn`)

Now load `citations.imps` in PyTorch. The CSR topology (`row_offsets`, `col_indices`) and node attributes are exposed directly as read-only `torch.Tensor` views over the `mmap` region—no `pd.read_parquet()`, no COO-to-CSR sorting, and zero multi-worker RAM blowup:

```python
import torch
from impulse_gnn import ImpulseGnnDataset, ImpulseNeighborSampler

# 1. Memory-map citations.imps (< 1 ms cold start, 0 bytes of heap allocation)
dataset = ImpulseGnnDataset("citations.imps")
print(f"Nodes: {dataset.node_count:,}, Edges: {dataset.edge_count:,}")

# 2. Zero-copy tensor views pointing directly into the .imps mmap pages
row_offsets: torch.Tensor = dataset.row_offsets   # torch.uint32 [node_count + 1]
col_indices: torch.Tensor = dataset.col_indices   # torch.uint32 [edge_count]

# 3. Sample 2-hop GraphSAGE mini-batches (25 neighbors at hop 1, 10 at hop 2)
#     directly from the C-ABI CSR arrays without building a full-graph PyG Data object
sampler = ImpulseNeighborSampler(dataset, sizes=[25, 10])
seed_nodes = torch.arange(0, 1024, dtype=torch.int32)
subgraphs = sampler.sample(seed_nodes.tolist())

print(f"Sampled {len(subgraphs)} hops; hop-0 edges: {subgraphs[0].shape[1]}")

# 4. Also interoperates zero-copy with SciPy / NetworkX / GraphBLAS:
csr_mat = dataset.to_scipy_csr()
```

!!! tip
    **Want to learn more about PyTorch & GNN training over `.imps` snapshots larger than RAM?** See the **[PyTorch & Graph Neural Networks Showcase](../showcase/gnn.md)**.

---

## 4. `manifest.json` Complete Reference

A `manifest.json` file contains two top-level arrays: `"domains"` and `"relations"`.

### 4.1 `domains[]` Schema

Each object in `"domains"` defines an independent node domain with its own contiguous dense ID space ($0 \dots N_d-1$):

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `id` | `u16` | **Yes** | Unique numeric domain ID (`0`, `1`, `2`, ...). Referenced by `src_domain` and `tgt_domain` in `relations[]`. |
| `name` | `string` | **Yes** | Logical domain name used in queries (e.g., `"User"`, `"Account"`, `"Paper"`). |
| `key_type` | `string` | **Yes** | Data type of the external primary key: `"string"`, `"int64"`, `"uint64"`, `"uuid"`, `"int32"`, or `"uint16"`. |
| `file` | `string` | No | Path to the node table file (`.parquet`, `.pq`, `.csv`, `.tsv`). If omitted, the domain's unique keys and node count are inferred automatically from the edge files that reference this domain. |
| `format` | `string` | No | `"parquet"`, `"csv"`, or `"tsv"`. Auto-detected from the file extension if omitted. |
| `id_column` | `string` | No | Column name containing the primary key in `file`. Defaults to `"id"` (or column `0` in headerless CSVs). |
| `attributes` | `AttributeDef[]` | No | List of node attribute columns to extract from `file` into 128-byte-aligned SoA columns. |

### 4.2 `relations[]` Schema

Each object in `"relations"` defines a directed edge relation from `src_domain` to `tgt_domain`:

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `name` | `string` | No | Relation name used in `.out("NAME")` / `.in("NAME")` and openCypher `[:NAME]`. Defaults to `"REL_{src}_{tgt}"` if omitted. |
| `src_domain` | `u16` | **Yes** | Numeric `id` of the source domain. |
| `tgt_domain` | `u16` | **Yes** | Numeric `id` of the target domain. |
| `file` | `string` | **Yes** | Path to the edge table file (`.parquet`, `.pq`, `.csv`, `.tsv`, `.txt`). |
| `format` | `string` | No | `"parquet"`, `"csv"`, or `"tsv"`. Auto-detected from the file extension if omitted. |
| `src_column` | `string` | No | Column name for the source node key. Defaults to `"src"` (or column `0` in CSV/TSV). |
| `tgt_column` | `string` | No | Column name for the target node key. Defaults to `"tgt"` (or column `1` in CSV/TSV). |
| `include_csc` | `bool` | No | When `true`, builds both forward **CSR** and reverse **CSC** topologies so `.in(...)` reverse walks execute in $O(1)$ offset lookup time. Defaults to `false`. |
| `encoding` | `string` | No | Target adjacency list encoding: `"raw"` (default uncompressed arrays), `"elias_fano"` (monotone gap compression), or `"bic"` (Binary Interpolative Coding). |
| `attributes` | `AttributeDef[]` | No | List of edge attribute columns to extract from `file` and reorder alongside the CSR edges. |

### 4.3 `attributes[]` Schema & Supported Data Types

Both domains and relations accept an `"attributes"` array where each element has:

```json
{
  "name": "amount",
  "column": "transfer_amount_usd",
  "type": "float64",
  "dimension": 1
}
```

* **`name`** *(required)*: Attribute name exposed to queries (`node.amount`, `edge.amount`).
* **`column`** *(required)*: Source column name in the Parquet or CSV/TSV file.
* **`type`** *(optional for Parquet, recommended for CSV)*: Explicit storage type. For Parquet inputs, `impulse build` automatically infers the Impulse type from the Arrow column schema if `"type"` is omitted.
* **`dimension`** *(optional)*: Defaults to `1` (scalar). Set `"dimension": D` (e.g., `128`, `384`, `768`) for fixed-width vector embeddings stored in Parquet `FixedSizeListArray` columns.

| Type String in `manifest.json` | Physical Layout in `.imps` | Parquet / Arrow Source Types |
| :--- | :--- | :--- |
| `"int8"`, `"int16"`, `"int32"`, `"int64"` | Signed 8 / 16 / 32 / 64-bit integer array | `Int8`, `Int16`, `Int32`, `Int64` |
| `"uint8"`, `"uint16"`, `"uint32"`, `"uint64"` | Unsigned 8 / 16 / 32 / 64-bit integer array | `UInt8`, `UInt16`, `UInt32`, `UInt64` |
| `"float16"`, `"float32"`, `"float64"` | IEEE-754 16 / 32 / 64-bit float array | `Float16`, `Float32`, `Float64` |
| `"bool"` / `"boolean"` | Bit-packed boolean array (`1 bit` per element) | `Boolean` |
| `"timestamp_ms"`, `"timestamp_ns"`, `"date32"` | 64-bit epoch timestamp (`ms` / `ns`) or 32-bit days | `Timestamp(Millisecond/Second/Microsecond/Nanosecond)`, `Date32`, `Date64` |
| `"string"` | Variable-length UTF-8 (`VAR_STRING` `0x0B`): per-column 128B-aligned `uint32_t offsets[K+1]` array + contiguous UTF-8 byte blob in Section 4 (note: Section 2 Shared String Pool stores only schema catalog identifiers) | `Utf8`, `LargeUtf8` |
| `"uuid"` | 128-bit (`16-byte`) fixed-width binary UUID (`FIXED_BYTES` `0x0A`, `dim = 16`) | `FixedSizeBinary(16)` or UUID string |
| **Nullable Suffix (`"?"`)** (e.g. `"float64?"`, `"int32?"`) | Prepends a 128-byte-aligned Arrow validity bitmap (`1` = valid, `0` = null) before the data array | Any nullable Parquet column or CSV column with empty cells |

!!! note
    **Primary Key Catalog vs. Programmatic Secondary Indices (`Section 2.6`)**:
    When `impulse build` compiles a `manifest.json`, it automatically builds the primary key lookup index (`_domain_index`) and attribute min/max metadata for each domain. Additional secondary indices (`0x01` Permutation, `0x02` ZoneMap, `0x03` InvertedBitset, `0x04` MinimalPerfectHash, `0x05` Trigram, `0x06` DomainSplitBitset, `0x07` TemporalInterval) can be constructed programmatically via the C-ABI (`impulse_index_build_*` + `impulse_writer_add_index` in `impulse_index.h`) or Rust `SnapshotWriter::add_index`.

---

## 5. Snapshot CLI Lifecycle Cheat Sheet

Beyond `impulse build`, the `impulse` CLI provides a complete toolkit for inspecting, validating, optimizing, diffing, and exporting `.imps` snapshots:

| Command | Example | Purpose |
| :--- | :--- | :--- |
| **`build`** | `impulse build --manifest manifest.json -o graph.imps` | Compiles CSV, TSV, or Parquet node/edge files into a 128-byte-aligned `.imps` snapshot. Pass `-o -` to stream directly to `stdout` (e.g., `impulse build -m manifest.json -o - \| aws s3 cp - s3://bucket/graph.imps`). |
| **`snapshot inspect`** | `impulse snapshot inspect graph.imps --verbose` | Prints Page 0 header flags, domain cardinalities, relation encodings, attribute schemas, and byte offsets (supports `--format json`). |
| **`snapshot validate`** | `impulse snapshot validate graph.imps --strict-alignment` | Verifies magic bytes, 128-byte section alignment, monotonic CSR/CSC offset bounds, and the footer SHA-256 checksum. |
| **`snapshot stats`** | `impulse snapshot stats graph.imps --supernode-threshold 10000` | Computes min/max/mean/p99 out-degree distributions, density, and lists high-degree supernodes per relation. |
| **`snapshot optimize`** | `impulse snapshot optimize -i raw.imps -o opt.imps --rcm --csc` | Reorders domain dense IDs via **Reverse Cuthill-McKee (`--rcm`)** or **Degree Sorting (`--degree-sort`)** to maximize CPU cache locality, and optionally generates missing CSC reverse indices (`--csc`). |
| **`snapshot diff`** | `impulse snapshot diff v1.imps v2.imps` | Compares two `.imps` snapshots and reports added/removed domains, relations, node/edge count deltas, and attribute layout changes. |
| **`snapshot export`** | `impulse snapshot export graph.imps -o out_dir/ --format csv` | Exports the topology and attributes of an `.imps` snapshot back to `csv`, `tsv`, or `jsonl` files. |
| **`snapshot convert-tensors`** | `impulse snapshot convert-tensors -i model.safetensors -o weights.imps --domain Layer` | Converts HuggingFace `.safetensors` or `.npy` tensor archives into 128-byte-aligned `.imps` vector attribute columns. |

---

## 6. Writing a Custom Snapshot Generator (Open `.imps` Binary Specification)

While the `impulse` CLI and the Java `SnapshotBuilder` cover almost all standard pipelines, **the `.imps` Binary Snapshot Format is an open, fully documented C-ABI specification**.

Because an `.imps` file is simply a sequence of 128-byte-aligned little-endian structs and contiguous primitive arrays (`row_offsets[]`, `col_indices[]`, and Structure-of-Arrays attribute columns) with no proprietary compression or complex pointer tables, **it is straightforward to write your own `.imps` generator directly in Python (using `struct`, `numpy`, or `pyarrow`), Rust, C++, or Go**:

1. **Follow the Normative Layout**: Read the **[Binary Snapshot Format Specification (`FORMAT_SPECIFICATION.md`)](../reference/spec/format-specification.md)** for the exact byte offsets of the 4KB Page 0 header (`magic = 0x494D5053`, `version = 0x0009`), Section 2 Shared String Pool, Domain & Relation Descriptors, 128-byte-aligned CSR/CSC arrays, and the 64-byte SHA-256 Footer.
2. **Validate with the CLI**: Any custom generator can be immediately verified against the normative compliance rules using:
   ```bash
   impulse snapshot validate custom_output.imps --strict-alignment
   impulse snapshot inspect custom_output.imps --verbose
   ```
3. **Cross-Check Against Compliance Vectors**: The specification repository includes 36 canonical binary test vectors (`tc01`..`tc36`) covering positive and negative structural invariants.

---

## Next Steps

* **[Changing Data & Live Updates](handling-mutations.md)** — Near-real-time (`< 5 min`) rebuild pipelines, S3/GCS distribution, and atomic Blue/Green memory-map swaps.
* **[Building Snapshots in Java](building-snapshots.md)** — Programmatic Java `SnapshotBuilder` and streaming JDBC `RelationDataSource` API.
* **[Python SDK Reference](../reference/python-api.md)** & **[PyTorch / GNN Showcase](../showcase/gnn.md)** — Complete Python API and zero-copy PyTorch tensor integration.
* **[CLI Reference](../reference/cli.md)** — Full command-line reference including `impulse query`, `impulse compile`, and `impulse run`.
