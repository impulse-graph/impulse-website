# C-ABI & C++20 Reference (`impulse-cpp`)

The **Impulse Graph Engine C-ABI Kernel** (`impulse-graph-core/impulse-cpp/include/`) provides the zero-dependency native foundation for C, C++20, Python (`pybind11`), Rust (`ffi`), Go (`CGo`), .NET (`P/Invoke`), and Node.js (`N-API`).

!!! info "Generated Doxygen Reference"
    For header-level symbol documentation, open the [**Generated Doxygen HTML Reference (`/doxygen/index.html`)**](/doxygen/index.html).

---

## 1. Header Map & Linkage

| Header File | Scope |
| :--- | :--- |
| **`impulse_format.h`** | Packed 1-byte-aligned C-ABI POD structures (`#pragma pack(push, 1)`), feature flags, and enumeration constants for the [Binary Snapshot Format (`.imps`)](spec/format-specification.md). |
| **`impulse_graph.h`** | Snapshot `mmap` loader, domain/relation catalog inspection, direct CSR/CSC/SoA attribute buffer pointers, key catalog resolution, streaming snapshot writer, and SIMD neighbor sampling. |
| **`impulse_vm.h`** | 64-bit bytecode instruction layout (`impulse_instruction_t`), 640-byte execution state frame (`impulse_vm_state_t`), in-kernel multi-language compiler, and SQLite-style prepared statements (`impulse_stmt_t`). |
| **`impulse_index.h`** | Secondary index construction and lookup functions (Permutation, 2-Tier Zone Map, Inverted Bitset, Minimal Perfect Hash, Trigram, Domain-Split Bitset, Temporal Interval). |
| **`impulse_simd.h`** | Dynamic SIMD target dispatch (`AVX-512`, `AVX2`, `ARM-NEON`, `WASM-SIMD128`) for float32 vector operations and sorted `uint32_t` array intersections. |
| **`impulse_vm_fluent.hpp`** | Header-only C++20 RAII wrappers (`impulse::Snapshot`, `impulse::DomainView`, `impulse::Statement`, `impulse::Writer`). |

---

## 2. Snapshot Lifecycle & Zero-Copy Buffer Accessors (`impulse_graph.h`)

```c
/* 1. Open and memory-map (.imps) file */
IMPULSE_API impulse_snapshot_t* impulse_snapshot_open(
    const char* file_path,
    impulse_status_t* out_status
);
IMPULSE_API void impulse_snapshot_close(impulse_snapshot_t* snapshot);

/* 2. Catalog inspection */
IMPULSE_API uint16_t impulse_snapshot_domain_count(const impulse_snapshot_t* snapshot);
IMPULSE_API uint16_t impulse_snapshot_relation_count(const impulse_snapshot_t* snapshot);

/* 3. Direct zero-copy CSR & CSC buffer pointers (128-byte aligned) */
IMPULSE_API impulse_status_t impulse_snapshot_get_relation_buffers(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    const uint32_t** out_offsets,
    const uint32_t** out_targets,
    uint64_t* out_node_count,
    uint64_t* out_edge_count
);

IMPULSE_API impulse_status_t impulse_snapshot_get_relation_csc_buffers(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    const uint32_t** out_csc_offsets,
    const uint32_t** out_csc_targets,
    uint64_t* out_csc_row_count,
    uint64_t* out_csc_edge_count
);

/* 4. Direct zero-copy SoA attribute column pointers (128-byte aligned) */
IMPULSE_API impulse_status_t impulse_snapshot_get_attribute_buffers(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    uint16_t attribute_index,
    const void** out_data,
    uint64_t* out_data_bytes,
    const void** out_offsets,
    uint64_t* out_offsets_bytes,
    uint8_t* out_type_code,
    uint32_t* out_dimension
);

/* 5. Bi-directional Key Catalog resolution & SIMD neighbor sampling */
IMPULSE_API impulse_status_t impulse_snapshot_resolve_key(
    const impulse_snapshot_t* snapshot,
    uint16_t domain_id,
    const void* key_bytes,
    size_t key_len,
    uint32_t* out_node_id
);

IMPULSE_API impulse_status_t impulse_snapshot_resolve_dense_id(
    const impulse_snapshot_t* snapshot,
    uint16_t domain_id,
    uint32_t node_id,
    const void** out_key_bytes,
    size_t* out_key_len
);

IMPULSE_API bool impulse_snapshot_is_reachable(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    uint64_t src_id,
    uint64_t tgt_id
);

IMPULSE_API impulse_status_t impulse_snapshot_sample_neighbors(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    const uint64_t* src_nodes,
    size_t num_nodes,
    int k_samples,
    uint64_t seed,
    uint64_t* out_src,
    uint64_t* out_tgt,
    size_t out_capacity,
    size_t* out_count
);
```

---

## 3. Prepared Statements & Caller-Provided Buffer C-ABI (`impulse_vm.h`)

Compiles any supported query dialect (`openCypher`, `ImpScheme`, `ImpLog`, `ImpK`, `CEL`) once and executes it inside a **Caller-Provided Memory Buffer** (`impulse_stmt_buffer_size`) with zero internal `malloc` calls:

```c
typedef struct impulse_stmt impulse_stmt_t;

/* 1. Prepare & Exact Buffer Sizing */
IMPULSE_API impulse_status_t impulse_stmt_prepare(
    const impulse_snapshot_t* snapshot,
    const char* query_text,
    impulse_stmt_t** out_stmt
);
IMPULSE_API size_t impulse_stmt_buffer_size(const impulse_stmt_t* stmt);
IMPULSE_API void impulse_stmt_finalize(impulse_stmt_t* stmt);

/* 2. Parameter Bindings */
IMPULSE_API impulse_status_t impulse_stmt_bind_node(impulse_stmt_t* stmt, const char* param, uint64_t node_id);
IMPULSE_API impulse_status_t impulse_stmt_bind_nodes(impulse_stmt_t* stmt, const char* param, const uint64_t* node_ids, size_t count);
IMPULSE_API impulse_status_t impulse_stmt_bind_bitset(impulse_stmt_t* stmt, const char* param, const uint64_t* words, size_t word_count);
IMPULSE_API impulse_status_t impulse_stmt_bind_int(impulse_stmt_t* stmt, const char* param, int64_t val);
IMPULSE_API impulse_status_t impulse_stmt_bind_float(impulse_stmt_t* stmt, const char* param, double val);
IMPULSE_API impulse_status_t impulse_stmt_bind_str(impulse_stmt_t* stmt, const char* param, const char* str);
IMPULSE_API impulse_status_t impulse_stmt_bind_uuid(impulse_stmt_t* stmt, const char* param, const uint8_t uuid_bytes[16]);

/* 3. Execute in Caller-Provided Buffer & Read Contiguous Arrow-Aligned Columns */
IMPULSE_API impulse_status_t impulse_stmt_execute(impulse_stmt_t* stmt, void* buffer, size_t buffer_size);
IMPULSE_API size_t impulse_stmt_row_count(const impulse_stmt_t* stmt);
IMPULSE_API uint32_t impulse_stmt_column_count(const impulse_stmt_t* stmt);
IMPULSE_API const void* impulse_stmt_column_data(const impulse_stmt_t* stmt, uint32_t col_idx);
IMPULSE_API bool impulse_stmt_column_is_null(const impulse_stmt_t* stmt, uint32_t col_idx, size_t row_idx);
```

---

## 4. Single-Pass Streaming Snapshot Writer (`impulse_writer_t`)

Writes `.imps` files directly to local disk or unseekable cloud streams (`impulse_write_fn` callback for S3/GCS multipart uploads) in $O(\text{chunk})$ RAM:

```c
IMPULSE_API impulse_writer_t* impulse_writer_create(const char* output_file_path, uint64_t global_features);
IMPULSE_API impulse_writer_t* impulse_writer_create_stream(impulse_write_fn write_cb, void* user_data, uint64_t global_features);
IMPULSE_API impulse_status_t impulse_writer_add_domain(impulse_writer_t* writer, uint16_t domain_id, uint8_t key_type, const char* name);
IMPULSE_API impulse_status_t impulse_writer_add_relation(
    impulse_writer_t* writer,
    uint16_t src_domain_id, uint16_t tgt_domain_id,
    uint8_t encoding_id, uint64_t node_count, uint64_t edge_count, uint64_t section_features,
    const void* row_offsets_data, uint64_t row_offsets_bytes,
    const void* col_indices_data, uint64_t col_indices_bytes
);
IMPULSE_API impulse_status_t impulse_writer_add_attribute(
    impulse_writer_t* writer, uint16_t relation_index, const char* name,
    uint8_t type_code, uint32_t dimension,
    const void* data, uint64_t data_bytes, const void* offsets, uint64_t offsets_bytes
);
IMPULSE_API impulse_status_t impulse_writer_finalize(impulse_writer_t* writer);
IMPULSE_API void impulse_writer_destroy(impulse_writer_t* writer);
```

---

## 5. C++20 Header-Only Wrapper (`impulse_vm_fluent.hpp`)

Provides zero-overhead C++20 RAII classes (`impulse::Snapshot`, `impulse::Statement`) over the C-ABI:

```cpp
#include "impulse_graph.h"
#include "impulse_vm_fluent.hpp"
#include <iostream>
#include <vector>

int main() {
    impulse::Snapshot snap("rbac.imps");

    // 1. Domain-anchored fluent traversal with transitive closure (zero lambdas)
    auto reachable_groups = snap.domain("User")
        .from_key("usr_alice")
        .out("MEMBER_OF")
        .repeat_until_stable("PARENT_GROUP")
        .to_bitset();

    // 2. Prepared statement with caller-allocated workspace buffer
    auto stmt = snap.prepare(
        "MATCH (u:User)-[:PURCHASED]->(p:Product) "
        "WHERE u._key = $userKey AND p.price <= $maxPrice "
        "RETURN p._id, p.price"
    );

    std::vector<uint8_t> workspace(stmt.buffer_size());

    stmt.bind_str("userKey", "usr_alice");
    stmt.bind_float("maxPrice", 99.95);
    stmt.execute(workspace.data(), workspace.size());

    const auto* product_ids = stmt.column_data<uint64_t>(0);
    const auto* prices      = stmt.column_data<double>(1);
    for (size_t i = 0; i < stmt.row_count(); ++i) {
        std::cout << "Product " << product_ids[i] << ": $" << prices[i] << "\n";
    }
    return 0;
}
```
