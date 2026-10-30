# C-ABI & C++20 Reference (`impulse-cpp`)

The **Impulse Graph Engine C-ABI Kernel** (`impulse-graph-core/impulse-cpp/include/`) provides the zero-dependency native foundation for C, C++20, Python (`pybind11`), Rust (`ffi`), Go (`CGo`), .NET (`P/Invoke`), and Node.js (`N-API`).

!!! info "Generated Doxygen Reference"
    For header-level symbol documentation, open the [**Generated Doxygen HTML Reference (`/doxygen/index.html`)**](/doxygen/index.html).

---

## 1. Header Map & Linkage

| Header File | Scope |
| :--- | :--- |
| **`impulse_format_v0_9.h`** | Packed 1-byte-aligned C-ABI POD structures (`#pragma pack(push, 1)`), feature flags, and enumeration constants for the [Binary Snapshot Format (`.imps`)](spec/format-specification.md). |
| **`impulse_graph.h`** | Snapshot `mmap` loader, domain/relation catalog inspection, direct CSR/CSC/SoA attribute buffer pointers, key catalog resolution, streaming snapshot writer, and SIMD neighbor sampling. |
| **`impulse_vm.h`** | 64-bit bytecode instruction layout (`impulse_instruction_t`), 640-byte execution state frame (`impulse_vm_state_t`), `TYPE_LANE_FRONTIER` (`0x10`) context accessors, in-kernel multi-language compiler, and SQLite-style prepared statements (`impulse_stmt_t`). |
| **`impulse_index.h`** | Secondary index construction and lookup functions (`0x01` Permutation, `0x02` 2-Tier Zone Map, `0x03` Inverted Bitset, `0x04` Minimal Perfect Hash, `0x05` Trigram, `0x06` Domain-Split Bitset, `0x07` Temporal Interval, and `0x08` Vamana ANN in `v0.9.1`). |
| **`impulse_simd.h`** | Dynamic SIMD target dispatch (`AVX-512`, `AVX2`, `ARM-NEON`, `WASM-SIMD128`) for float32 vector operations and sorted `uint32_t` array intersections. |
| **`impulse_vm_fluent.hpp`** | C++20 fluent bytecode builder (`impulse::vm::QueryBuilder`, `CompiledQuery`, `QueryResult`) and domain-bound traversal DSL (`SnapshotView`, `DomainView`, `Traversal`, `MultiLaneBuilder`, `MultiLaneTraversal`, `MultiLaneResult`). |

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
IMPULSE_API impulse_status_t impulse_stmt_bind_roaring(impulse_stmt_t* stmt, const char* param, const uint8_t* bytes, size_t len);
IMPULSE_API impulse_status_t impulse_stmt_bind_int(impulse_stmt_t* stmt, const char* param, int64_t val);
IMPULSE_API impulse_status_t impulse_stmt_bind_uint(impulse_stmt_t* stmt, const char* param, uint64_t val);
IMPULSE_API impulse_status_t impulse_stmt_bind_float(impulse_stmt_t* stmt, const char* param, double val);
IMPULSE_API impulse_status_t impulse_stmt_bind_str(impulse_stmt_t* stmt, const char* param, const char* str);
IMPULSE_API impulse_status_t impulse_stmt_bind_uuid(impulse_stmt_t* stmt, const char* param, const uint8_t uuid_bytes[16]);
IMPULSE_API impulse_status_t impulse_stmt_bind_vector(impulse_stmt_t* stmt, const char* param, const float* data, size_t dim);

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

## 5. C++20 Fluent Bytecode Builder (`impulse_vm_fluent.hpp`)

Provides type-safe C++20 classes (`impulse::vm::QueryBuilder`, `impulse::vm::CompiledQuery`, `impulse::vm::QueryResult`) with automatic register allocation for constructing and executing `impOps` bytecode programs:

```cpp
#include "impulse_graph.h"
#include "impulse_vm_fluent.hpp"
#include <iostream>
#include <vector>

int main() {
    impulse_status_t status = IMPULSE_OK;
    impulse_snapshot_t* snap = impulse_snapshot_open("rbac.imps", &status);
    if (status != IMPULSE_OK || !snap) return 1;

    // 1. Fluent C++20 bytecode builder with fixed-point transitive closure
    using namespace impulse::vm;
    CompiledQuery query = QueryBuilder()
        .inputNode(0)                // R0 = seed user ID
        .walkEdge(/*MEMBER_OF=*/ 0)  // Step to direct groups
        .repeatUntilStable([](QueryBuilder& b) {
            b.walkEdge(/*PARENT_GROUP=*/ 1);
        })
        .collectBitset()
        .compile();

    impulse_vm_context_t* ctx = nullptr;
    QueryResult res = query.execute(snap, /*input_param=*/ 42, &ctx);
    if (res.isOk()) {
        std::cout << "Group 7 reachable: " << res.testBitset(ctx, 7) << "\n";
    }
    if (ctx) impulse_vm_context_destroy(ctx);

    // 2. Prepared statement with caller-allocated workspace buffer
    impulse_stmt_t* stmt = nullptr;
    impulse_stmt_prepare(
        snap,
        "MATCH (u:User)-[:PURCHASED]->(p:Product) WHERE u.id = $userId RETURN p",
        &stmt
    );

    std::vector<uint8_t> workspace(impulse_stmt_buffer_size(stmt));
    impulse_stmt_bind_node(stmt, "$userId", 42);
    impulse_stmt_execute(stmt, workspace.data(), workspace.size());

    const auto* bitset_words = static_cast<const uint64_t*>(impulse_stmt_column_data(stmt, 0));
    std::cout << "Result bitset words: " << impulse_stmt_row_count(stmt) << "\n";

    impulse_stmt_finalize(stmt);
    impulse_snapshot_close(snap);
    return 0;
}
```

### 5.1 Multi-Lane Bit-Sliced & Hybrid Vector Fluent APIs (Planned v0.9.1)

In `v0.9.1`, `impulse_vm_fluent.hpp` and `impulse_vm.h` add support for **Multi-Lane Bit-Sliced Execution (`0xC0..0xC9`)** and **Hybrid Vamana ANN Search & SIMD Reranking (`0xCA..0xCB`)** at three levels:

#### 1. Low-Level `impulse::vm::QueryBuilder` Bytecode Emitters (`0xC0..0xCB`)

```cpp
// Multi-Lane Bit-Sliced Execution (0xC0..0xC9) & Hybrid Vector Search (0xCA..0xCB)
QueryBuilder& laneInitSeeds(uint16_t seed_reg, uint8_t width_flag = 0);                              // 0xC0 OP_LANE_INIT_SEEDS
QueryBuilder& laneInitGroups(uint16_t pairs_reg, uint16_t num_groups);                               // 0xC1 OP_LANE_INIT_GROUPS
QueryBuilder& laneSetEdgeMask(uint16_t pairs_reg, uint16_t relation_id);                             // 0xC2 OP_LANE_SET_EDGE_MASK
QueryBuilder& laneWalkCsr(uint16_t relation_id, bool fixed_point = false);                           // 0xC3 OP_LANE_CSR_WALK
QueryBuilder& laneWalkCsc(uint16_t relation_id, bool fixed_point = false);                           // 0xC4 OP_LANE_CSC_WALK
QueryBuilder& lanePruneMask(uint8_t mode, uint16_t arg0, uint16_t arg1 = 0);                         // 0xC5 OP_LANE_PRUNE_MASK
QueryBuilder& laneFilterQuorum(uint16_t min_quorum, uint16_t mask_reg = 0xFF);                       // 0xC6 OP_LANE_FILTER_QUORUM
QueryBuilder& laneReduceAnd();                                                                       // 0xC7 OP_LANE_REDUCE_AND
QueryBuilder& laneReduceAttr(uint16_t attr_id, uint8_t reduce_op = 0);                               // 0xC8 OP_LANE_REDUCE_ATTR
QueryBuilder& laneSetCover(uint16_t mask_reg = 0xFF, uint8_t mode = 0);                              // 0xC9 OP_LANE_SET_COVER
QueryBuilder& vectorAnnSearch(uint16_t query_reg, uint16_t top_k,
                              uint16_t index_or_attr_id = 0, bool fused_lane_frontier = false);      // 0xCA OP_VECTOR_ANN_SEARCH
QueryBuilder& vectorRerankDot(uint16_t query_reg, uint16_t attr_id = 0, uint8_t metric = 0);         // 0xCB OP_VECTOR_RERANK_DOT
```

#### 2. High-Level Domain-Bound `SnapshotView`, `DomainView`, `MultiLaneBuilder` & `MultiLaneTraversal`

`SnapshotView` wraps an `impulse_snapshot_t*` to provide domain-bound traversals (`snap_view.domain("Gene")`) across both single-lane `Traversal` (including `DomainView::vectorSearch` and `Traversal::rerank`) and multi-lane `MultiLaneBuilder`:

| C++20 Class (`impulse::vm`) | Core Methods |
| :--- | :--- |
| **`SnapshotView`** | `domain(const std::string& domain_name)`, `domain(uint16_t domain_id)`, `raw()` |
| **`DomainView`** | `all()`, `from(node_ids)`, `fromKey(key)`, `fromKeys(keys)`, `vectorSearch(index_or_attr, query_vector, top_k)`, `multiLane()` |
| **`MultiLaneBuilder`** | `fromSeeds(node_ids)`, `fromKeys(keys)`, `fromGroups(concept_groups)`, `fromConceptVectors(index_or_attr, concept_vectors, hits_per_concept)`, `fromOutages(relation, tripped_edge_ids_per_lane)` |
| **`MultiLaneTraversal`** | **Walks**: `out(rel)`, `out(rel, edge_cel)`, `in(rel)`, `in(rel, edge_cel)`, `repeat(n, rel)`, `repeatUntilStable(rel)`<br>**Filters & Pruning**: `filter(node_cel)`, `project(cel)`, `pruneWhere(deny_cel)`, `pruneDeniedBy(deny_rel)`, `pruneHubs(max_degree, min_quorum)`, `whereQuorum(min_lanes)`, `whereMask(required_any_mask, forbidden_mask)`, `mustHitAtLeast(min_lanes, subset_seed_keys)`, `mustAvoidAll(forbidden_seed_keys)`<br>**Terminal Collectors**: `collect()`, `toQuorumTraversal(min_lanes)`, `reducePerLane(node_attr, ReducerOp)`, `argMinNodesPerLane(node_attr)`, `argMaxNodesPerLane(node_attr)`, `argMinKeysPerLane(node_attr)`, `argMaxKeysPerLane(node_attr)`, `checkAllNodesReachedPerLane()`, `toSteinerSubgraph(min_concept_quorum)` |
| **`MultiLaneResult`** | `laneCount()`, `domainNodeCount()`, `laneMaskFor(node_id)`, `lanePopcountFor(node_id)`, `attributionFor(node_id)`, `keyAttributionFor(node_key)`, `nodesWithQuorum(min_lanes)`, `keysWithQuorum(min_lanes)`, `findSetCoverPairs(target_mask)`, `findGreedySetCover(target_mask, max_nodes)` |

```cpp
SnapshotView view(snap);

// 10-gene oncology panel with safety exclusion and 2-drug cocktail cover
MultiLaneResult res = view.domain("Gene").multiLane()
    .fromKeys({"BRCA1", "BRCA2", "EGFR", "MYC", "KRAS", "PIK3CA", "BRAF", "ERBB2",
               "KCNH2_SAFE", "SCN5A_SAFE"})
    .out("INTERACTS_GiG")
    .in("BINDS_CbG")
    .mustHitAtLeast(5, {"BRCA1", "BRCA2", "EGFR", "MYC", "KRAS", "PIK3CA", "BRAF", "ERBB2"})
    .mustAvoidAll({"KCNH2_SAFE", "SCN5A_SAFE"})
    .collect();

auto quorum_drugs   = res.keysWithQuorum(5);
auto cocktail_pairs = res.findSetCoverPairs(0x00FFULL);
```

#### 3. C-ABI `impulse_vm_context_t` Lane Frontier Accessors (`impulse_vm.h`)

For FFI bindings and custom native callers inspecting `TYPE_LANE_FRONTIER` (`0x10`) handles directly:

```c
IMPULSE_API int impulse_vm_context_acquire_lane_frontier(impulse_vm_context_t* ctx);
IMPULSE_API void impulse_vm_context_release_lane_frontier(impulse_vm_context_t* ctx, size_t handle);
IMPULSE_API uint32_t impulse_vm_context_lane_frontier_num_lanes(const impulse_vm_context_t* ctx, size_t handle);
IMPULSE_API uint32_t impulse_vm_context_lane_frontier_width(const impulse_vm_context_t* ctx, size_t handle);
IMPULSE_API uint64_t impulse_vm_context_lane_frontier_active_mask(const impulse_vm_context_t* ctx, size_t handle);
IMPULSE_API size_t impulse_vm_context_lane_frontier_node_count(const impulse_vm_context_t* ctx, size_t handle);
IMPULSE_API const uint64_t* impulse_vm_context_lane_frontier_data(const impulse_vm_context_t* ctx, size_t handle);
```

---

## 6. In-Kernel Multi-Language Compiler & Secondary Index Builder (`impulse_vm.h` & `impulse_index.h`)

### In-Kernel Multi-Frontend Compiler (`impulse_vm.h`)
Compiles `ImpScheme` (`IMPULSE_LANG_IMPSCM = 0`), `ImpK` (`IMPULSE_LANG_IMPK = 1`), `ImpLog` (`IMPULSE_LANG_IMPLOG = 2`), `openCypher` (`IMPULSE_LANG_CYPHER = 3`), or `CEL` (`IMPULSE_LANG_CEL = 4`) strings directly into `impOps` bytecode or `.impas` assembly text:

```c
typedef enum {
    IMPULSE_LANG_IMPSCM = 0,
    IMPULSE_LANG_IMPK   = 1,
    IMPULSE_LANG_IMPLOG = 2,
    IMPULSE_LANG_CYPHER = 3,
    IMPULSE_LANG_CEL    = 4
} impulse_language_t;

IMPULSE_API impulse_status_t impulse_compile_query(
    const impulse_snapshot_t* snapshot,
    const char* script,
    impulse_language_t lang,
    impulse_instruction_t* out_instructions,
    size_t out_capacity,
    size_t* out_count
);

IMPULSE_API impulse_status_t impulse_compile_to_impas(
    const impulse_snapshot_t* snapshot,
    const char* script,
    impulse_language_t lang,
    char* out_impas_buffer,
    size_t out_capacity,
    size_t* out_bytes_written
);

IMPULSE_API impulse_vm_status_t impulse_compile_and_execute(
    const impulse_snapshot_t* snapshot,
    const char* script,
    impulse_language_t lang,
    impulse_vm_state_t* state,
    uint64_t input_seed
);
```

### Secondary Index Construction & Attachment (`impulse_index.h` & `impulse_graph.h`)
Builds secondary index blobs (`0x01` Permutation, `0x02` ZoneMap, `0x03` InvertedBitset, `0x04` MinimalPerfectHash, `0x05` Trigram, `0x06` DomainSplitBitset, `0x07` TemporalInterval) and embeds them into `.imps` Section 2.6:

```c
/* Build secondary index payload in memory (impulse_index.h) */
IMPULSE_API impulse_status_t impulse_index_build_permutation(
    const void* attr_data, size_t element_count, uint8_t type_code,
    void** out_bytes, size_t* out_size
);
IMPULSE_API impulse_status_t impulse_index_build_zone_map(
    const void* attr_data, size_t element_count, uint8_t type_code,
    void** out_bytes, size_t* out_size
);
IMPULSE_API impulse_status_t impulse_index_build_minimal_perfect_hash(
    const char** keys, size_t count,
    void** out_bytes, size_t* out_size
);
IMPULSE_API void impulse_index_free(void* ptr);

/* Attach built index blob to SnapshotWriter (impulse_graph.h) */
IMPULSE_API impulse_status_t impulse_writer_add_index(
    impulse_writer_t* writer,
    uint16_t domain_id,
    uint16_t relation_id,
    uint16_t attribute_index,
    uint8_t index_type,
    const char* index_name,
    const void* index_data,
    uint64_t index_bytes,
    uint64_t payload_feature_mask
);
```
