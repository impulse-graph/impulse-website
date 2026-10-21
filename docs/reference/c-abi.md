# C-ABI Kernel & VM Reference

This document provides the complete reference for the **Impulse Graph Engine C-ABI Kernel (v0.9.0)** defined across the C headers in `impulse-graph-core/impulse-cpp/include/`.

All language bindings (Java FFM, Rust FFI, Python `pybind11`, Go `CGo`, .NET `P/Invoke`, Node.js `N-API`) bind directly to these C-ABI structures and entrypoints.

!!! info "Generated Doxygen Reference"
    For interactive header-level source documentation and cross-referenced symbol graphs, open the [**Generated Doxygen HTML Reference (`/doxygen/index.html`)**](/doxygen/index.html).

---

## 1. Header Map & Linkage

| Header File | Scope |
| :--- | :--- |
| **`impulse_format_v0_9.h`** | Packed 1-byte-aligned C-ABI POD structures (`#pragma pack(push, 1)`), feature flags, and enumeration constants for Binary Snapshot Format v0.9.0. |
| **`impulse_graph.h`** | Snapshot `mmap` loader, domain/relation catalog inspection, direct CSR/CSC/attribute buffer pointers, key catalog resolution, streaming snapshot writer, delta layers, and SIMD neighbor sampling. |
| **`impulse_vm.h`** | 64-bit bytecode instruction layout (`impulse_instruction_t`), 640-byte execution state frame (`impulse_vm_state_t`), off-heap context handle pool (`impulse_vm_context_t`), AOT validator, in-kernel multi-language compiler, and SQLite-style prepared statement & Arrow column projection API (`impulse_stmt_t`). |
| **`impulse_index.h`** | Secondary non-vector index construction and lookup functions (Permutation, 2-Tier Zone Map, Inverted Bitset, Minimal Perfect Hash, Trigram, Domain-Split Bitset, Temporal Interval). |
| **`impulse_simd.h`** | Dynamic SIMD target dispatch (`AVX-512`, `AVX2`, `ARM-NEON`, `WASM-SIMD128`) for float32 vector operations and sorted `uint32_t` array intersections. |
| **`impulse_math_ops.h`** | 54-function analytical vector math catalog (`MATH_FUNC_ABS`..`MATH_FUNC_ISFINITE`) for unary, binary, and ternary SIMD evaluations. |

All exported symbols use `IMPULSE_API` (`__attribute__((visibility("default")))` on POSIX; `__declspec(dllexport)` / `__declspec(dllimport)` on Windows) inside `extern "C"` blocks.

---

## 2. Binary Format Layout & POD Structures (`impulse_format_v0_9.h`)

### 2.1 Protocol Constants & Feature Bitmasks

```c
#define IMPULSE_MAGIC                        0x494D5053  /* 'I' 'M' 'P' 'S' (Little-Endian) */
#define IMPULSE_VERSION_MAJOR                0
#define IMPULSE_VERSION_MINOR                9
#define IMPULSE_VERSION_PACKED               9
#define IMPULSE_DEFAULT_DATA_OFFSET          4096        /* Page 0 fixed baseline */

/* Global Feature Flags (Header required_features bitmask) */
#define IMPULSE_GLOBAL_FEAT_4KB_PAGE_ALIGNED 0x0000000000000001ULL
#define IMPULSE_GLOBAL_FEAT_CRYPTO_SIGNED    0x0000000000000002ULL
#define IMPULSE_GLOBAL_FEAT_FOOTER_CATALOG   0x0000000000000004ULL

/* Section Feature Flags (Relation section_features bitmask) */
#define IMPULSE_SECTION_FEAT_RAW_UINT32      0x0000000000000001ULL
#define IMPULSE_SECTION_FEAT_DELTA_VBYTE     0x0000000000000002ULL
#define IMPULSE_SECTION_FEAT_RAW_UINT16      0x0000000000000004ULL
#define IMPULSE_SECTION_FEAT_SIMDCOMP        0x0000000000000010ULL
```

### 2.2 Status, Key Type, Encoding & Index Enumerations

```c
typedef enum impulse_status {
    IMPULSE_OK                              = 0,
    IMPULSE_ERR_INVALID_MAGIC               = 1,
    IMPULSE_ERR_UNSUPPORTED_VERSION         = 2,
    IMPULSE_ERR_UNSUPPORTED_GLOBAL_FEATURE  = 3,
    IMPULSE_ERR_UNSUPPORTED_SECTION_FEATURE = 4,
    IMPULSE_ERR_CORRUPT_CHECKSUM            = 5,
    IMPULSE_ERR_IO_FAILURE                  = 6,
    IMPULSE_ERR_INVALID_ARGUMENT            = 7,
    IMPULSE_ERR_SIGNATURE_MISMATCH          = 8,
    IMPULSE_ERR_BUFFER_OVERFLOW             = 9
} impulse_status_t;

typedef enum impulse_key_type_t_v0_9 {
    IMPULSE_KEY_TYPE_INT8_V0_9       = 1,
    IMPULSE_KEY_TYPE_INT16_V0_9      = 2,
    IMPULSE_KEY_TYPE_INT32_V0_9      = 3,
    IMPULSE_KEY_TYPE_INT64_V0_9      = 4,
    IMPULSE_KEY_TYPE_UINT8_V0_9      = 5,
    IMPULSE_KEY_TYPE_UINT16_V0_9     = 6,
    IMPULSE_KEY_TYPE_UINT32_V0_9     = 7,
    IMPULSE_KEY_TYPE_UINT64_V0_9     = 8,
    IMPULSE_KEY_TYPE_FLOAT32_V0_9    = 9,
    IMPULSE_KEY_TYPE_FLOAT64_V0_9    = 10,
    IMPULSE_KEY_TYPE_VAR_STRING_V0_9 = 11,
    IMPULSE_KEY_TYPE_UUID128_V0_9    = 12
} impulse_key_type_t_v0_9_t;

typedef enum impulse_encoding_type_t_v0_9 {
    IMPULSE_ENC_RAW_UINT32_V0_9     = 0,
    IMPULSE_ENC_DELTA_VBYTE_V0_9    = 1,
    IMPULSE_ENC_RAW_UINT16_V0_9     = 2,
    IMPULSE_ENC_HYBRID_16_32_V0_9   = 3,
    IMPULSE_ENC_SIMDCOMP_V0_9       = 4,
    IMPULSE_ENC_SLICED_ELLPACK_V0_9 = 5,
    IMPULSE_ENC_TPU_BCOO_V0_9       = 6,
    IMPULSE_ENC_RAW_UINT64_V0_9     = 7,
    IMPULSE_ENC_ROARING_BITMAP_V0_9 = 8
} impulse_encoding_type_t_v0_9_t;

typedef enum impulse_index_type_t {
    IMP_INDEX_NONE                 = 0,
    IMP_INDEX_PERMUTATION          = 1,
    IMP_INDEX_ZONE_MAP             = 2,
    IMP_INDEX_INVERTED_BITSET      = 3,
    IMP_INDEX_MINIMAL_PERFECT_HASH = 4,
    IMP_INDEX_TRIGRAM_3GRAM        = 5,
    IMP_INDEX_DOMAIN_SPLIT_BITSET  = 6,
    IMP_INDEX_TEMPORAL_INTERVAL    = 7
} impulse_index_type_t;
```

### 2.3 Binary Snapshot POD Structures (`#pragma pack(push, 1)`)

```c
/* Section 1: Fixed 4KB Baseline Snapshot Header (4096 Bytes) */
typedef struct impulse_snapshot_header_v0_9_t {
    uint32_t magic;                   /* 0x494D5053 ('IMPS') */
    uint16_t version;                 /* 0x0009 */
    uint32_t data_offset;             /* Offset where Section 2 payload begins (4096) */
    uint16_t domain_count;            /* Total node domains in catalog */
    uint16_t relation_count;          /* Total relations in directory */
    uint64_t timestamp_ms;            /* Unix epoch timestamp (ms) */
    uint64_t required_features;       /* Global feature bitmask */
    uint64_t footer_directory_offset; /* File offset to Footer Directory Table */
    uint64_t footer_directory_bytes;  /* Byte length of Footer Directory Table */
    uint8_t  snapshot_uuid[16];       /* 128-bit binary UUID */
    uint16_t header_checksum;         /* CRC-16-CCITT over bytes 0x00..0x3D */
    uint16_t index_count;             /* Total secondary indices */
    uint8_t  header_padding[4030];    /* Reserved padding to 4096 bytes */
} impulse_snapshot_header_v0_9_t;

/* Section 2: Domain Catalog Entry (16 Bytes) */
typedef struct impulse_domain_catalog_entry_v0_9_t {
    uint16_t domain_id;               /* 0-indexed domain ID */
    uint8_t  key_type;                /* impulse_key_type_t_v0_9 */
    uint8_t  reserved;
    uint32_t name_offset;             /* Offset into Shared String Table */
    uint64_t node_count;              /* Cardinality N_d (dense IDs 0..N_d-1) */
} impulse_domain_catalog_entry_v0_9_t;

/* Section 2: Relation Directory Entry (128 Bytes) */
typedef struct impulse_relation_directory_entry_v0_9_t {
    uint16_t relation_id;             /* 0-indexed relation ID */
    uint16_t src_domain_id;           /* Source domain ID */
    uint16_t tgt_domain_id;           /* Target domain ID */
    uint8_t  encoding_id;             /* impulse_encoding_type_t_v0_9 */
    uint8_t  node_id_width;           /* Node ID width in bits (16, 32, 64) */
    uint8_t  edge_index_width;        /* Edge index width in bits (32, 64) */
    uint8_t  reserved1[3];
    uint32_t name_offset;             /* Offset into Shared String Table */
    uint64_t node_count;              /* Source domain node count */
    uint64_t edge_count;              /* Total directed edges */
    uint64_t section_features;        /* Section feature bitmask */
    uint64_t csr_row_off_offset;      /* 128B-aligned CSR row_offsets file offset */
    uint64_t csr_row_off_bytes;       /* CSR row_offsets byte length */
    uint64_t csr_col_idx_offset;      /* 128B-aligned CSR col_indices file offset */
    uint64_t csr_col_idx_bytes;       /* CSR col_indices byte length */
    uint64_t csc_row_off_offset;      /* 128B-aligned CSC row_offsets file offset */
    uint64_t csc_row_off_bytes;       /* CSC row_offsets byte length */
    uint64_t csc_col_idx_offset;      /* 128B-aligned CSC col_indices file offset */
    uint64_t csc_col_idx_bytes;       /* CSC col_indices byte length */
    uint16_t attr_count;              /* Number of attached attribute descriptors */
    uint8_t  reserved2[22];           /* Expansion padding to 128 bytes */
} impulse_relation_directory_entry_v0_9_t;

/* Section 2: Attribute Descriptor Entry (44 Bytes) */
typedef struct impulse_attribute_descriptor_v0_9_t {
    uint32_t name_offset;             /* Offset into Shared String Table */
    uint8_t  type_code;               /* Primitive type enum */
    uint8_t  reserved1;
    uint16_t reserved2;
    uint32_t dimension;               /* 1 for scalar, >1 for fixed-width vector */
    uint64_t data_offset;             /* 128B-aligned payload offset */
    uint64_t data_bytes;              /* Payload byte length */
    uint64_t offsets_offset;          /* Var-string offsets array offset (0 if fixed) */
    uint64_t offsets_bytes;           /* Var-string offsets byte length */
} impulse_attribute_descriptor_v0_9_t;

/* Section 2.6: Secondary Index Directory Entry (64 Bytes) */
typedef struct impulse_index_directory_entry_v0_9_t {
    uint32_t index_id;                /* 0-indexed secondary index ID */
    uint16_t domain_id;               /* Target domain ID */
    uint16_t relation_id;             /* Target relation ID (0xFFFF for domain attribute) */
    uint16_t attribute_index;         /* 0-indexed attribute index */
    uint8_t  index_type;              /* impulse_index_type_t (0x01..0x07) */
    uint8_t  reserved1;
    uint32_t name_offset;             /* Offset into Shared String Table */
    uint64_t data_offset;             /* 128B-aligned file offset to index payload */
    uint64_t data_bytes;              /* Index payload byte size */
    uint64_t payload_feature_mask;    /* Index feature bitmask */
    uint8_t  reserved_padding[24];    /* Padding to 64 bytes */
} impulse_index_directory_entry_v0_9_t;

/* 16-Byte Footer Trailer at EOF */
typedef struct impulse_footer_trailer_v0_9_t {
    uint64_t footer_length;           /* Byte size of Footer Block */
    uint32_t spec_version;            /* 0x0009 */
    uint32_t footer_magic;            /* 0x494D5053 ('IMPS') */
} impulse_footer_trailer_v0_9_t;
```

---

## 3. Snapshot Kernel API (`impulse_graph.h`)

### 3.1 Opaque Handles

```c
typedef struct impulse_snapshot    impulse_snapshot_t;
typedef struct impulse_writer      impulse_writer_t;
typedef struct impulse_delta_layer impulse_delta_layer_t;
typedef int32_t (*impulse_write_fn)(const void* data, size_t bytes, void* user_data);
```

### 3.2 Snapshot Lifecycle & Catalog Inspection

```c
/* Open and memory-map (.imps) file */
IMPULSE_API impulse_snapshot_t* impulse_snapshot_open(
    const char* file_path,
    impulse_status_t* out_status
);

/* Unmap memory and close file descriptor */
IMPULSE_API void impulse_snapshot_close(impulse_snapshot_t* snapshot);

/* Header & catalog metadata */
IMPULSE_API uint32_t impulse_snapshot_magic(const impulse_snapshot_t* snapshot);
IMPULSE_API uint16_t impulse_snapshot_version(const impulse_snapshot_t* snapshot);
IMPULSE_API uint16_t impulse_snapshot_domain_count(const impulse_snapshot_t* snapshot);
IMPULSE_API uint16_t impulse_snapshot_relation_count(const impulse_snapshot_t* snapshot);
IMPULSE_API uint64_t impulse_snapshot_max_node_count(const impulse_snapshot_t* snapshot);

IMPULSE_API impulse_status_t impulse_snapshot_get_domain_entry(
    const impulse_snapshot_t* snapshot,
    uint16_t domain_index,
    impulse_domain_catalog_entry_t* out_entry,
    const char** out_name
);

IMPULSE_API impulse_status_t impulse_snapshot_get_relation_entry(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    impulse_relation_directory_entry_t* out_entry
);

IMPULSE_API impulse_status_t impulse_snapshot_get_metadata(
    const impulse_snapshot_t* snapshot,
    const char* key,
    char* out_val,
    size_t out_capacity
);

IMPULSE_API const char* impulse_get_last_error(void);
```

### 3.3 Direct Zero-Copy Buffer Accessors

```c
/* Raw byte slice at arbitrary file offset */
IMPULSE_API const void* impulse_snapshot_get_buffer(
    const impulse_snapshot_t* snapshot,
    uint64_t offset,
    uint64_t size
);

/* Direct CSR (forward) row_offsets & col_indices pointers */
IMPULSE_API impulse_status_t impulse_snapshot_get_relation_buffers(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    const uint32_t** out_offsets,
    const uint32_t** out_targets,
    uint64_t* out_node_count,
    uint64_t* out_edge_count
);

/* Direct CSC (reverse) row_offsets & col_indices pointers */
IMPULSE_API impulse_status_t impulse_snapshot_get_relation_csc_buffers(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    const uint32_t** out_csc_offsets,
    const uint32_t** out_csc_targets,
    uint64_t* out_csc_row_count,
    uint64_t* out_csc_edge_count
);

/* Direct SoA attribute column data & var-length offset pointers */
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

/* Secondary index payload inspection */
IMPULSE_API uint16_t impulse_snapshot_get_index_count(const impulse_snapshot_t* snapshot);
IMPULSE_API impulse_status_t impulse_snapshot_get_index(
    const impulse_snapshot_t* snapshot,
    uint16_t index_idx,
    uint32_t* index_id,
    uint16_t* domain_id,
    uint16_t* relation_id,
    uint16_t* attribute_index,
    uint8_t* index_type,
    const char** index_name,
    const void** index_data,
    uint64_t* index_bytes
);
```

### 3.4 Key Catalog Resolution, Reachability & Neighbor Sampling

```c
/* Resolve external primary key bytes -> internal 0-indexed dense node ID */
IMPULSE_API impulse_status_t impulse_snapshot_resolve_key(
    const impulse_snapshot_t* snapshot,
    uint16_t domain_id,
    const void* key_bytes,
    size_t key_len,
    uint32_t* out_node_id
);

/* Resolve internal 0-indexed dense node ID -> external primary key bytes */
IMPULSE_API impulse_status_t impulse_snapshot_resolve_dense_id(
    const impulse_snapshot_t* snapshot,
    uint16_t domain_id,
    uint32_t node_id,
    const void** out_key_bytes,
    size_t* out_key_len
);

/* O(log d) binary search / O(1) reachability check on relation_index */
IMPULSE_API bool impulse_snapshot_is_reachable(
    const impulse_snapshot_t* snapshot,
    uint16_t relation_index,
    uint64_t src_id,
    uint64_t tgt_id
);

/* SIMD neighborhood sampling for GNN mini-batches (k_samples = -1 for full expansion) */
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

### 3.5 Single-Pass Streaming Snapshot Writer & Delta Compaction

```c
/* Streaming Writer Lifecycle */
IMPULSE_API impulse_writer_t* impulse_writer_create(const char* output_file_path, uint64_t global_features);
IMPULSE_API impulse_writer_t* impulse_writer_create_stream(impulse_write_fn write_cb, void* user_data, uint64_t global_features);
IMPULSE_API impulse_status_t  impulse_writer_add_domain(impulse_writer_t* writer, uint16_t domain_id, uint8_t key_type, const char* name);
IMPULSE_API impulse_status_t  impulse_writer_add_relation(
    impulse_writer_t* writer,
    uint16_t src_domain_id,
    uint16_t tgt_domain_id,
    uint8_t encoding_id,
    uint64_t node_count,
    uint64_t edge_count,
    uint64_t section_features,
    const void* row_offsets_data, uint64_t row_offsets_bytes,
    const void* col_indices_data, uint64_t col_indices_bytes
);
IMPULSE_API impulse_status_t  impulse_writer_add_attribute(
    impulse_writer_t* writer,
    uint16_t relation_index,
    const char* name,
    uint8_t type_code,
    uint32_t dimension,
    const void* data, uint64_t data_bytes,
    const void* offsets, uint64_t offsets_bytes
);
IMPULSE_API impulse_status_t  impulse_writer_add_index(
    impulse_writer_t* writer,
    uint16_t domain_id,
    uint16_t relation_id,
    uint16_t attribute_index,
    uint8_t index_type,
    const char* index_name,
    const void* index_data, uint64_t index_bytes,
    uint64_t payload_feature_mask
);
IMPULSE_API impulse_status_t  impulse_writer_set_metadata(impulse_writer_t* writer, const char* key, const char* value);
IMPULSE_API impulse_status_t  impulse_writer_finalize(impulse_writer_t* writer);
IMPULSE_API void              impulse_writer_destroy(impulse_writer_t* writer);

/* Live Overlay Delta Layer & Compaction */
IMPULSE_API impulse_delta_layer_t* impulse_delta_layer_create(uint16_t src_domain_id, uint16_t tgt_domain_id, const char* relation_name);
IMPULSE_API impulse_status_t       impulse_delta_layer_add_edge(impulse_delta_layer_t* delta, uint64_t src_node, uint64_t tgt_node);
IMPULSE_API impulse_status_t       impulse_delta_layer_tombstone_edge(impulse_delta_layer_t* delta, uint64_t src_node, uint64_t tgt_node);
IMPULSE_API bool                   impulse_delta_layer_is_tombstoned(const impulse_delta_layer_t* delta, uint64_t src_node, uint64_t tgt_node);
IMPULSE_API void                   impulse_delta_layer_destroy(impulse_delta_layer_t* delta);

IMPULSE_API impulse_status_t impulse_snapshot_compact_to_file(
    const impulse_snapshot_t* base_snapshot,
    impulse_delta_layer_t** deltas,
    size_t delta_count,
    const char* output_file_path
);

IMPULSE_API impulse_status_t impulse_snapshot_compact_to_stream(
    const impulse_snapshot_t* base_snapshot,
    impulse_delta_layer_t** deltas,
    size_t delta_count,
    impulse_write_fn write_cb,
    void* user_data
);
```

---

## 4. Bytecode VM, In-Kernel Compiler & Prepared Statements (`impulse_vm.h`)

### 4.1 Instruction & Execution State Frame Structures

Every `impOps` instruction is a fixed 8-byte aligned struct (`impulse_instruction_t`), and every VM execution frame is a 640-byte cache-line-aligned struct (`impulse_vm_state_t`) identical between C++ and Java FFM:

```c
/* Fixed 64-bit (8-Byte) Instruction Layout */
typedef struct IMPULSE_ALIGN(8) {
    uint8_t  opcode;    /* Opcode byte (0x00..0x95) */
    uint8_t  flags;     /* Modifier flags (HALT_ON_EMPTY, INPUT_SEED, ACCUMULATE, INVERT, OFFHEAP) */
    uint16_t dst_reg;   /* Destination register index (R0..R63) */
    uint32_t payload;   /* Source register, relation ID, jump offset, or immediate constant */
} impulse_instruction_t;

/* 640-Byte, 64-Byte Aligned VM Execution State Frame */
typedef struct IMPULSE_ALIGN(64) {
    uint32_t pc;                         /* Byte 0..3:   Program Counter */
    uint32_t reserved;                   /* Byte 4..7:   Alignment padding */
    uint64_t flags;                      /* Byte 8..15:  Status flags (ZF, LT, GT, EQ, ST) */
    uint64_t registers[64];              /* Byte 16..527: 64-bit general registers R0..R63 */
    uint8_t  register_types[64];         /* Byte 528..591: Type tags (impulse_register_type_t) */
    impulse_vm_context_t* query_context; /* Byte 592..599: Off-heap execution context pointer */
    uint32_t call_stack[8];              /* Byte 600..631: Subroutine return address stack */
    uint32_t call_stack_depth;           /* Byte 632..635: Active call stack depth */
    uint32_t reserved_padding2;          /* Byte 636..639: Padding to 640 bytes */
} impulse_vm_state_t;
```

#### Register Type Tags (`impulse_register_type_t`) & Status Codes (`impulse_vm_status_t`)

```c
typedef enum {
    TYPE_NULL          = 0x00,
    TYPE_INT64         = 0x01,
    TYPE_NODE_ID       = 0x02,
    TYPE_RELATION_ID   = 0x03,
    TYPE_BITSET_HANDLE = 0x04,
    TYPE_NODE_VECTOR   = 0x05,
    TYPE_CSR_SPAN      = 0x06,
    TYPE_BOOLEAN       = 0x07,
    TYPE_FLOAT         = 0x08,
    TYPE_DOUBLE        = 0x09,
    TYPE_VALUE_MAP     = 0x0A,
    TYPE_STRING_VECTOR = 0x0B,
    TYPE_FLOAT_VECTOR  = 0x0C,
    TYPE_DOUBLE_VECTOR = 0x0D,
    TYPE_UINT64_VECTOR = 0x0E
} impulse_register_type_t;

typedef enum {
    IMPULSE_VM_OK                   = 0,
    IMPULSE_VM_ERR_INVALID_OPCODE   = 1,
    IMPULSE_VM_ERR_OUT_OF_BOUNDS    = 2,
    IMPULSE_VM_ERR_NULL_SNAPSHOT    = 3,
    IMPULSE_VM_ERR_STACK_OVERFLOW   = 4,
    IMPULSE_VM_ERR_STACK_UNDERFLOW  = 5,
    IMPULSE_VM_ERR_INVALID_REGISTER = 6,
    IMPULSE_VM_ERR_USER_THROW       = 7,
    IMPULSE_VM_ERR_ASSERTION_FAILED = 8,
    IMPULSE_VM_ERR_TRAP             = 9,
    IMPULSE_VM_ERR_RESERVED_OPCODE  = 10,
    IMPULSE_VM_ERR_BUFFER_OVERFLOW  = 11,
    IMPULSE_VM_ERR_FLOATING_POINT   = 12,
    IMPULSE_VM_ERR_GAS_EXHAUSTED    = 13
} impulse_vm_status_t;
```

### 4.2 AOT Bytecode Validator, Executor & Off-Heap Context Pool

```c
/* Static single-pass abstract register type validator */
IMPULSE_API impulse_vm_status_t impulse_vm_validate(
    const impulse_instruction_t* bytecode,
    size_t instruction_count
);

/* Execute bytecode array against a VM state frame */
IMPULSE_API impulse_vm_status_t impulse_vm_execute(
    const impulse_instruction_t* bytecode,
    size_t instruction_count,
    impulse_vm_state_t* vm_state,
    uint64_t input_param
);

/* Execute and materialize output bitset directly into a caller-allocated word buffer */
IMPULSE_API size_t impulse_vm_get_required_buffer_size(
    const impulse_snapshot_t* snapshot,
    uint16_t domain_id
);

IMPULSE_API impulse_vm_status_t impulse_vm_execute_to_buffer(
    const impulse_instruction_t* bytecode,
    size_t instruction_count,
    impulse_vm_state_t* vm_state,
    uint64_t input_param,
    uint16_t target_domain_id,
    uint16_t result_reg,
    uint64_t* out_words,
    size_t out_words_capacity,
    size_t* out_words_written
);

/* Off-heap context lifecycle & handle management */
IMPULSE_API impulse_vm_context_t* impulse_vm_context_create(const impulse_snapshot_t* snapshot);
IMPULSE_API void                  impulse_vm_context_destroy(impulse_vm_context_t* ctx);
IMPULSE_API void                  impulse_vm_context_set_fuel(impulse_vm_context_t* ctx, uint64_t fuel);

IMPULSE_API int      impulse_vm_context_acquire_bitset(impulse_vm_context_t* ctx);
IMPULSE_API void     impulse_vm_context_release_bitset(impulse_vm_context_t* ctx, size_t handle);
IMPULSE_API void     impulse_vm_context_bitset_add(impulse_vm_context_t* ctx, size_t handle, uint64_t node_id);
IMPULSE_API bool     impulse_vm_context_bitset_test(const impulse_vm_context_t* ctx, size_t handle, uint64_t node_id);
IMPULSE_API void     impulse_vm_context_bitset_fill(impulse_vm_context_t* ctx, size_t handle, uint64_t count);
IMPULSE_API uint64_t impulse_vm_context_bitset_get_word(const impulse_vm_context_t* ctx, size_t handle, size_t word_idx);
```

### 4.3 Unified In-Kernel Compiler C-ABI

Compiles any supported frontend dialect (`ImpScheme`, `ImpK`, `ImpLog`, `openCypher`, `CEL`) into 8-byte `impOps` instructions or `.impas` assembly text using snapshot catalog statistics:

```c
typedef enum {
    IMPULSE_LANG_IMPSCM = 0,  /* ImpScheme S-Expression IR (.impscm) */
    IMPULSE_LANG_IMPK   = 1,  /* ImpK Array/Vector DSL (.impk) */
    IMPULSE_LANG_IMPLOG = 2,  /* ImpLog Datalog DSL (.implog) */
    IMPULSE_LANG_CYPHER = 3,  /* openCypher Pattern Matcher */
    IMPULSE_LANG_CEL    = 4   /* Google Common Expression Language */
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

### 4.4 Canonical SQLite-Style Prepared Statement & Arrow Column C-ABI

Provides a stateful prepared statement workflow (`prepare` $\to$ `bind_*` $\to$ `execute` $\to$ `column_*` $\to$ `finalize`) with Apache Arrow-compatible contiguous columnar result buffers:

```c
typedef struct impulse_stmt impulse_stmt_t;

typedef struct impulse_column_desc {
    char            name[32];           /* Column identifier */
    uint8_t         type_code;          /* IMPULSE_KEY_TYPE_* */
    uint8_t         element_size;       /* Byte size of element (e.g. 8 for uint64, 4 for float32) */
    bool            is_nullable;        /* False if guaranteed non-null */
    uint8_t         reserved;
    uint32_t        dimension;          /* 1 for scalars, >1 for vector embeddings */
    size_t          byte_offset_in_buf; /* Offset within caller buffer */
    const void*     data_ptr;           /* Direct pointer to contiguous column array */
    const uint64_t* null_bitmap;        /* Arrow validity bitmap (NULL if non-nullable) */
} impulse_column_desc_t;

typedef struct impulse_execution_result {
    impulse_vm_status_t status;
    size_t              row_count;
    uint32_t            column_count;
    uint32_t            reserved;
    size_t              total_bytes_written;
    const void*         data_ptr;
    uint64_t            scalar_value;
} impulse_execution_result_t;

/* 1. Prepare & Sizing */
IMPULSE_API impulse_status_t impulse_stmt_prepare(
    const impulse_snapshot_t* snapshot,
    const char* query_text,
    impulse_stmt_t** out_stmt
);
IMPULSE_API size_t impulse_stmt_buffer_size(const impulse_stmt_t* stmt);
IMPULSE_API void   impulse_stmt_finalize(impulse_stmt_t* stmt);

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

/* 3. Execute & Zero-Copy Column Accessors */
IMPULSE_API impulse_status_t impulse_stmt_execute(impulse_stmt_t* stmt, void* buffer, size_t buffer_size);
IMPULSE_API size_t           impulse_stmt_row_count(const impulse_stmt_t* stmt);
IMPULSE_API uint32_t         impulse_stmt_column_count(const impulse_stmt_t* stmt);
IMPULSE_API const char*      impulse_stmt_column_name(const impulse_stmt_t* stmt, uint32_t col_idx);
IMPULSE_API uint8_t          impulse_stmt_column_type(const impulse_stmt_t* stmt, uint32_t col_idx);
IMPULSE_API uint32_t         impulse_stmt_column_dim(const impulse_stmt_t* stmt, uint32_t col_idx);
IMPULSE_API const void*      impulse_stmt_column_data(const impulse_stmt_t* stmt, uint32_t col_idx);
IMPULSE_API bool             impulse_stmt_column_is_null(const impulse_stmt_t* stmt, uint32_t col_idx, size_t row_idx);

/* One-Line Convenience Execution */
IMPULSE_API impulse_status_t impulse_exec(
    const impulse_snapshot_t* snapshot,
    const char* query_text,
    uint64_t seed_node,
    impulse_execution_result_t* out_result
);
```

---

## 5. Secondary Non-Vector Index C-ABI (`impulse_index.h`)

Section 2.6 of Binary Snapshot Specification v0.9.0 supports 7 secondary index formats for attribute filtering and key lookup:

| Index Type Enum | Code | Builder Function | Query Function |
| :--- | :--- | :--- | :--- |
| `IMP_INDEX_PERMUTATION` | `0x01` | `impulse_index_build_permutation` | `impulse_index_permutation_range_query` |
| `IMP_INDEX_ZONE_MAP` | `0x02` | `impulse_index_build_zone_map` | `impulse_index_zone_map_filter` |
| `IMP_INDEX_INVERTED_BITSET` | `0x03` | `impulse_index_build_inverted_bitset` | `impulse_index_inverted_bitset_lookup` |
| `IMP_INDEX_MINIMAL_PERFECT_HASH` | `0x04` | `impulse_index_build_minimal_perfect_hash` | `impulse_index_minimal_perfect_hash_lookup` |
| `IMP_INDEX_TRIGRAM_3GRAM` | `0x05` | `impulse_index_build_trigram` | `impulse_index_trigram_search` |
| `IMP_INDEX_DOMAIN_SPLIT_BITSET` | `0x06` | `impulse_index_build_domain_split` | `impulse_index_domain_split_lookup` |
| `IMP_INDEX_TEMPORAL_INTERVAL` | `0x07` | `impulse_index_build_temporal_interval` | `impulse_index_temporal_interval_query` |

Buffers returned via `void** out_bytes` by any `impulse_index_build_*` function are released with `impulse_index_free(void* ptr)`.

---

## 6. SIMD & Vector Math C-ABI (`impulse_simd.h`, `impulse_math_ops.h`)

### 6.1 Dynamic SIMD Kernels

```c
IMPULSE_API const char*      impulse_simd_get_target_name(void);
IMPULSE_API float            impulse_simd_dot_product_f32(const float* a, const float* b, size_t len);
IMPULSE_API float            impulse_simd_reduce_sum_f32(const float* a, size_t len);
IMPULSE_API impulse_status_t impulse_simd_vector_sum_f32(const float* a, const float* b, float* out, size_t len);
IMPULSE_API impulse_status_t impulse_simd_vector_scale_f32(float* a, float scalar, size_t len);
IMPULSE_API impulse_status_t impulse_simd_vector_mul_f32(float* a, const float* b, size_t len);
IMPULSE_API impulse_status_t impulse_simd_intersect_sorted_u32(
    const uint32_t* a, size_t len_a,
    const uint32_t* b, size_t len_b,
    uint32_t* out_intersection,
    size_t* out_count
);
```

### 6.2 Analytical Vector Math Function IDs (`impulse_math_func_id_t`)

Used by `OP_VEC_MATH_UNARY` (`0x2D`), `OP_VEC_MATH_BINARY` (`0x2E`), and `OP_VEC_MATH_TERNARY` (`0x2F`):

| Category | Function IDs (`0x01`..`0x36`) |
| :--- | :--- |
| **Algebraic & Roots (`0x01`..`0x07`)** | `MATH_FUNC_ABS`, `MATH_FUNC_SQRT`, `MATH_FUNC_RSQRT`, `MATH_FUNC_CBRT`, `MATH_FUNC_POW`, `MATH_FUNC_HYPOT`, `MATH_FUNC_LERP` |
| **Exponential & Log (`0x08`..`0x0F`)** | `MATH_FUNC_EXP`, `MATH_FUNC_EXP2`, `MATH_FUNC_EXP10`, `MATH_FUNC_EXPM1`, `MATH_FUNC_LOG`, `MATH_FUNC_LOG2`, `MATH_FUNC_LOG10`, `MATH_FUNC_LOG1P` |
| **Trigonometric (`0x10`..`0x17`)** | `MATH_FUNC_SIN`, `MATH_FUNC_COS`, `MATH_FUNC_TAN`, `MATH_FUNC_ASIN`, `MATH_FUNC_ACOS`, `MATH_FUNC_ATAN`, `MATH_FUNC_ATAN2`, `MATH_FUNC_SINC` |
| **Hyperbolic (`0x18`..`0x1D`)** | `MATH_FUNC_SINH`, `MATH_FUNC_COSH`, `MATH_FUNC_TANH`, `MATH_FUNC_ASINH`, `MATH_FUNC_ACOSH`, `MATH_FUNC_ATANH` |
| **Rounding & Clamping (`0x1E`..`0x24`)** | `MATH_FUNC_FLOOR`, `MATH_FUNC_CEIL`, `MATH_FUNC_TRUNC`, `MATH_FUNC_ROUND`, `MATH_FUNC_CLAMP`, `MATH_FUNC_COPYSIGN`, `MATH_FUNC_FMOD` |
| **Neural Activations (`0x25`..`0x2A`)** | `MATH_FUNC_RELU`, `MATH_FUNC_LEAKY_RELU`, `MATH_FUNC_SIGMOID`, `MATH_FUNC_GELU`, `MATH_FUNC_SILU`, `MATH_FUNC_SOFTPLUS` |
| **Special & Statistics (`0x2B`..`0x2D`)** | `MATH_FUNC_ERF`, `MATH_FUNC_ERFC`, `MATH_FUNC_LGAMMA` |
| **Bitwise (`0x2E`..`0x32`)** | `MATH_FUNC_POPCOUNT`, `MATH_FUNC_CLZ`, `MATH_FUNC_CTZ`, `MATH_FUNC_ROTL`, `MATH_FUNC_ROTR` |
| **IEEE 754 Sanitizers (`0x33`..`0x36`)** | `MATH_FUNC_SAFE_DIV`, `MATH_FUNC_ISNAN`, `MATH_FUNC_ISINF`, `MATH_FUNC_ISFINITE` |
