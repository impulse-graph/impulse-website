# Impulse Graph Python SDK & Bytecode VM API Reference

The `impulse-graph` Python SDK provides high-performance zero-copy access to binary graph snapshots (`.imps`) and embeds the native **Impulse C++ Bytecode Virtual Machine Engine** via pybind11 bindings.

---

## Installation

Install `impulse-graph` from PyPI:

```bash
pip install impulse-graph
```

Requires Python `>= 3.8` and a C++20 compliant compiler environment if building from source distribution (`sdist`).

---

## Core Snapshot & Writer API

### `Snapshot`

Represents an immutable, zero-copy memory-mapped graph snapshot file (`.imps`).

```python
from impulse_graph import Snapshot

with Snapshot("power_grid.imps") as snap:
    print("Domains:", snap.domain_count())
    print("Relations:", snap.relation_count())
    print("Is edge (rel 0, src 42, tgt 100) reachable?", snap.is_reachable(0, 42, 100))

    # Inspect CSR topology buffers zero-copy as NumPy arrays
    row_offsets = snap.get_row_offsets_array(relation_index=0)
    col_indices = snap.get_col_indices_array(relation_index=0)
```

#### Methods

- **`Snapshot(path: str)`**: Open `.imps` snapshot file via `mmap`.
- **`close()`**: Unmap physical memory and release file descriptors.
- **`domain_count() -> int`**: Return total count of registered domains in snapshot catalog.
- **`relation_count() -> int`**: Return total count of relations.
- **`get_relation(index: int) -> dict`**: Get metadata dictionary for relation entry (node count, edge count, offsets).
- **`is_reachable(relation_index: int, src_id: int, tgt_id: int) -> bool`**: Sub-microsecond edge existence query.
- **`get_row_offsets_array(relation_index: int) -> np.ndarray`**: Zero-copy NumPy view of CSR row offsets.
- **`get_col_indices_array(relation_index: int) -> np.ndarray`**: Zero-copy NumPy view of CSR column indices.
- **`sample_neighbors(relation_index: int, nodes: list | np.ndarray, k_samples: int, seed: int = 42) -> tuple[np.ndarray, np.ndarray]`**: Zero-copy SIMD neighborhood sampler for GNN training.
- **`execute_query(query: vm.CompiledQuery, input_param: int = 0) -> vm.QueryResult`**: Execute a compiled C++ VM bytecode query directly against the snapshot.

---

### `Writer`

Streaming compiler for constructing C-ABI v2.4 binary snapshots.

```python
from impulse_graph import Writer

with Writer("my_graph.imps") as writer:
    writer.add_domain(domain_id=0, key_type=4, name="User")
    writer.add_relation(
        src_domain_id=0,
        tgt_domain_id=0,
        encoding_type=0,
        node_count=4,
        edge_count=4,
        section_features=0,
        row_offsets=[0, 2, 3, 3, 4],
        col_indices=[1, 2, 3, 0]
    )
    writer.finalize()
```

---

## Bytecode Virtual Machine API (`impulse_graph.vm`)

The `impulse_graph.vm` module exposes the native C++ Virtual Machine Engine and its fluent query builder pipeline.

### `QueryBuilder`

Fluent API for emitting raw 64-bit opcode instructions (`impulse_instruction_t`).

```python
from impulse_graph import vm

# Construct a 2-hop traversal query
qb = vm.QueryBuilder()
query = (
    qb
    .input_node(dst_reg=0)
    .walk_edge(relation_id=0)
    .walk_edge(relation_id=1)
    .collect_array()
    .compile()
)
```

#### Method Categories

##### Inputs & Constants
- **`input_node(dst_reg: int = 0)`**: Load seed node ID from `input_param` into `dst_reg`.
- **`input_set(dst_reg: int = 0)`**: Load input bitset handle into `dst_reg`.
- **`load_const_int(value: int, dst_reg: int = 0)`**: Load 64-bit integer constant.
- **`load_const_float(value: float, dst_reg: int = 0)`**: Load float constant.
- **`load_keys(keys: List[str], dst_reg: int = 0)`**: Load string key list for dense mapping.

##### Graph Walks & Filters
- **`walk_edge(relation_id: int, flags: int = 0)`**: Perform CSR forward traversal along relation.
- **`walk_edge_filtered(relation_id: int, filter_id: int)`**: Walk edges matching attribute predicate.
- **`walk_degree(relation_id: int)`**: Compute node out-degree along relation.
- **`walk_csc(relation_id: int)`**: Reverse incoming edge traversal using CSC topology.
- **`filter_node(filter_id: int)`**: Filter node bitset by property predicate.

##### Set & Vector Operations
- **`union_with(src_reg: int)`**: Bitset union operation.
- **`intersect_with(src_reg: int)`**: Bitset intersection operation.
- **`difference_with(src_reg: int)`**: Bitset difference operation.
- **`cardinality()`**: Count set bits in bitset register.
- **`vector_mul_attr(attr_reg: int)`**: Element-wise vector multiplication with attribute array.
- **`vector_reduce_sum()`**: Sum reduce float vector into scalar register.

##### Analytics & GraphBLAS
- **`matrix_vector_mul(matrix_reg: int, semiring_id: int = 0)`**: GraphBLAS matrix-vector product.
- **`afforest()`**: Afforest connected components algorithm opcode.
- **`brandes_forward()` / `brandes_backward()`**: Brandes betweenness centrality sweeps.
- **`sample_neighbors(relation_id: int, k_samples: int, seed: int = 0)`**: SIMD neighborhood sampling opcode.
- **`rebac_check(permission_id: int)`**: Zanzibar Relationship-Based Access Control check opcode.

##### Control Flow & Iteration
- **`repeat(count: int, body: Callable[[QueryBuilder], None])`**: Unroll fixed iteration loop (e.g. PageRank / K-hop).
- **`repeat_until_stable(body: Callable[[QueryBuilder], None])`**: Iterate until set generation converges (FLAGS STABLE bit).
- **`jmp(instruction_offset: int)`**: Unconditional jump.
- **`jz(instruction_offset: int)`** / **`jnz(instruction_offset: int)`**: Conditional jump on Zero Flag.

##### Terminal Collection
- **`collect_bitset()`**: Terminate query returning output BitSet handle.
- **`collect_array()`**: Terminate query returning contiguous node index array.
- **`compile() -> CompiledQuery`**: Finalize bytecode emission into an executable `CompiledQuery`.

---

### `CompiledQuery`

Immutable compiled query program ready for execution.

```python
result = compiled_query.execute(snapshot=snap, input_param=42)
```

- **`execute(snapshot: Snapshot, input_param: int = 0) -> QueryResult`**: Execute query with new thread-local context lifecycle.
- **`execute_with_context(ctx: VmContext, state: VmState, input_param: int = 0) -> QueryResult`**: Execute query using pre-allocated off-heap context and state frame.
- **`instruction_count() -> int`**: Return total emitted 64-bit opcode count.
- **`result_register() -> int`**: Target output register index.

---

### `QueryResult`

Execution output wrapper.

- **`is_ok() -> bool`**: Returns `True` if execution status is `IMPULSE_VM_OK`.
- **`status -> int`**: Return `VmStatus` integer code.
- **`result_register -> int`**: Register ID holding output value.
- **`result_type -> int`**: `RegisterType` enum tag (`TYPE_NODE_VECTOR`, `TYPE_BITSET_HANDLE`, etc.).
- **`as_int() -> int`**: Extract 64-bit integer payload.
- **`as_float() -> float`**: Extract 32-bit float payload.
- **`as_double() -> float`**: Extract 64-bit double payload.
- **`test_bitset(ctx: VmContext, node_id: int) -> bool`**: Test membership of `node_id` in output bitset handle.

---

### `VmContext`

Off-heap context pool managing handles for bitsets, float vectors, double vectors, and value maps.

```python
with vm.VmContext() as ctx:
    bs_handle = ctx.acquire_bitset()
    ctx.bitset_add(bs_handle, node_id=42)
    assert ctx.bitset_test(bs_handle, node_id=42) is True
    ctx.release_bitset(bs_handle)
```

---

## PyPI Package Artifacts

`impulse-graph` binary wheels contain static-linked C++20 core engine binaries and SIMD kernels.

| Artifact Type | Package Format | Target Platform |
| :--- | :--- | :--- |
| **Source Distribution** | `impulse-graph-2.4.0.tar.gz` | Universal (`sdist`) |
| **macOS ARM64 Wheel** | `impulse_graph-2.4.0-cp314-cp314-macosx_..._arm64.whl` | macOS 11.0+ (Apple Silicon) |
| **Linux Wheel** | `impulse_graph-2.4.0-cp314-cp314-manylinux_2_28_x86_64.whl` | glibc 2.28+ x86_64 |
