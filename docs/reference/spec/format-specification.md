# Formal Specification: Impulse-Graph C-ABI Binary Snapshot Format

* **Document Status**: Standard Reference Specification
* **Byte Order**: Little-Endian (`LE`, IEEE 754 & x86-64 / ARM64 Native)
* **Memory Alignment**: 128-Byte SIMD / GPU Boundary (`(len + 127) & ~127`) & 4KB OS Page Boundary (`(offset + 4095) & ~4095`)
* **Integrity Validation**: SHA-256 Checksum (32 Bytes, calculated over payload) & Ed25519 Cryptographic Signature Block

---

## 1. Specification Overview & Modular Design Principles

This document defines the formal binary protocol specification for the **Impulse-Graph C-ABI Binary Snapshot Format**.

The format is organized into **4KB OS page-aligned physical blocks**, structured to support **single-pass S3/cloud streaming uploads**, **$O(1)$ zero-copy `mmap` range loading**, and **AVX-512 / GPU SIMD vectorization**.

### Physical File Layout Overview

```text
┌───────────────────────────────────────────────────────────────────────────────────┐
│ SECTION 1: Snapshot Header (4KB Page 0, Offset 0x0000)                             │
│   ├── Magic ("IMPS"), Version (0x0009), DataOffset (4096)                          │
│   └── GlobalRequiredFeatures, SnapshotUUID, HeaderChecksum                        │
├───────────────────────────────────────────────────────────────────────────────────┤
│ SECTION 2: Catalog & Directory Directory Table (4KB Page 1, Offset 0x1000)         │
│   ├── 1. String Table (Shared Null-Terminated UTF-8 String Pool Blob)              │
│   ├── 2. Domain Catalog Array (Fixed 16-Byte POD Structs)                         │
│   └── 3. Sorted Relation Directory Table (Fixed 128B Entries + 40B Attr Descriptors) │
├───────────────────────────────────────────────────────────────────────────────────┤
│ RELATION BLOCK 1 [MANDATORY, 4KB Aligned]                                         │
│   ├── csrRowOffsets Array (128B Aligned, uint32/uint64)                           │
│   ├── csrColumnIndices Stream (128B Aligned, RAW 0x00 Encoding)                   │
│   ├── cscRowOffsets / cscColumnIndices Arrays (Optional Transpose, 128B Aligned)  │
│   ├── Edge Fixed-width SoA Attribute Arrays (128B Aligned: weights, timestamps...)│
│   └── Edge Var-length Attribute Offsets & Data Blobs (128B Aligned)               │
├───────────────────────────────────────────────────────────────────────────────────┤
│ RELATION BLOCK 2 [MANDATORY, 4KB Aligned]                                         │
│   └── (Contiguous 128B aligned topology & attribute array sequence)               │
├───────────────────────────────────────────────────────────────────────────────────┤
│ NODE DOMAIN BLOCK 1 [OPTIONAL, 4KB Aligned]                                       │
│   ├── Node Fixed-width SoA Attribute Arrays (128B Aligned)                        │
│   └── Node Var-length Attribute Offsets & Data Blobs (128B Aligned)               │
├───────────────────────────────────────────────────────────────────────────────────┤
│ SECTION 4: KEY CATALOG BLOCK [OPTIONAL, 128B Aligned]                             │
│   ├── Minimal Perfect Hash Function (MPHF) or Sorted Array Indices                 │
│   └── (O(1) / O(log N) mapping of external string/int keys to dense Node IDs)     │
├───────────────────────────────────────────────────────────────────────────────────┤
│ FOOTER BLOCK [EOF, 4KB Aligned]                                                   │
│   ├── Unified UTF-8 Key/Value Custom Metadata Stream (Unlimited multi-map)         │
│   ├── Final Catalog & Relation Directory Table Copy (S3 Cloud Range Reader Copy)  │
│   ├── SHA-256 Payload Checksum & Ed25519 Cryptographic Signature Block            │
│   └── 16-Byte Footer Trailer (footer_length [u64] + version [u32] + "IMPS" [u32]) │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Section 1: Snapshot Header Layout (Fixed 4KB Page 0 Baseline)

The snapshot header occupies byte offset `0x00000000` (Page 0). It contains a **64-byte active baseline** aligned to a single CPU cache line, inside a fixed 4096-byte page (`DataOffset = 4096`).

### Header Byte Offset Table

| Byte Offset | Field Name | C-ABI Type | Size | Default / Constant | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `0x0000` – `0x0003` | `Magic` | `uint32_t` | 4 Bytes | `0x494D5053` (`"IMPS"`) | Magic constant identifying Impulse-Graph binary snapshot file. |
| `0x0004` – `0x0005` | `Version` | `uint16_t` | 2 Bytes | `0x0009` (`9`) | Protocol specification version number ( packed `0x0009`). |
| `0x0006` – `0x0009` | `DataOffset` | `uint32_t` | 4 Bytes | `4096` (`0x00001000`) | Fixed constant (`4096`). Section 2 always starts at byte 4096 (Page 1). |
| `0x000A` – `0x000B` | `DomainCount` | `uint16_t` | 2 Bytes | Variable | Total number of node domains in the catalog (up to 65,536). |
| `0x000C` – `0x000D` | `RelationCount` | `uint16_t` | 2 Bytes | Variable | Total number of relations in the matrix (up to 65,536). |
| `0x000E` – `0x0015` | `TimestampMs` | `uint64_t` | 8 Bytes | Epoch Milliseconds | Unix epoch timestamp (milliseconds) when snapshot was created. |
| `0x0016` – `0x001D` | `GlobalRequiredFeatures` | `uint64_t` | 8 Bytes | Bitmask | **Global Feature-in-Use Bitmask** (64-bit feature flags). |
| `0x001E` – `0x0025` | `FooterDirectoryOffset` | `uint64_t` | 8 Bytes | Absolute File Offset | File offset to Footer Directory Table (`0` if Page 1 directory is used). |
| `0x0026` – `0x002D` | `FooterDirectoryBytes` | `uint64_t` | 8 Bytes | Byte Size | Byte size of Footer Directory Table (`0` if omitted). |
| `0x002E` – `0x003D` | `SnapshotUUID` | `uint8_t[16]` | 16 Bytes | Random Binary UUID | Unique 128-bit Binary UUID for this snapshot build artifact. |
| `0x003E` – `0x003F` | `HeaderChecksum` | `uint16_t` | 2 Bytes | CRC-16-CCITT | Fast CRC-16 checksum calculated over bytes `0x0000..0x003D`. |
| `0x0040` – `0x0FFF` | `ReservedPadding` | `uint8_t[4032]` | 4032 Bytes | `0x00 ...` | **Reserved Header Expansion Padding** (Aligns Header to 4KB boundary). |

---

## 3. Section 2: Catalog, String Table & Directory Table Layout

Begins at byte offset `DataOffset` (byte 4096). Contains the **Shared String Table**, node domain definitions, and the **Relation Directory Table**.

### 3.1 Shared String Table (String Pool Heap)
Begins at byte offset `DataOffset` (4096):

* `StringTableBytes` (`uint32_t`, 4B): Total byte size of string pool blob.
* `StringPool` (`byte[StringTableBytes]`): Contiguous null-terminated UTF-8 byte stream starting with `\0` at offset `0`.
  - String offset `0` corresponds to empty string `""`.
  - All domain names, relation names, and attribute names store a 32-bit `name_offset` pointing directly to their null-terminated UTF-8 byte stream in this pool.

### 3.2 Domain Catalog Array (Fixed 16 Bytes per Domain)
Begins immediately after String Table, aligned to a 128-byte boundary. Contains `DomainCount` fixed-size 16-byte records:

| Byte Offset | Field Name | C-ABI Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x0000` – `0x0001` | `DomainID` | `uint16_t` | 2 Bytes | Zero-indexed domain identifier (`0`..`DomainCount - 1`). |
| `0x0002` | `KeyType` | `uint8_t` | 1 Byte | Domain key primitive type enum (`0x01` = INT8..`0x0B` = VAR_STRING). |
| `0x0003` | `Reserved` | `uint8_t` | 1 Byte | `0x00` alignment padding. |
| `0x0004` – `0x0007` | `NameOffset` | `uint32_t` | 4 Bytes | 0-indexed byte offset into String Table (points to null-terminated string, e.g., `"User\0"`). |
| `0x0008` – `0x000F` | `NodeCount` | `uint64_t` | 8 Bytes | Total number of nodes $N$ in this domain. |

### 3.3 Relation Directory Table (Fixed 128 Bytes per Relation)
Begins immediately after Domain Catalog Array, aligned to a 128-byte boundary. Contains `RelationCount` relation descriptors, **sorted primary by `SrcDomainID` and secondary by `TgtDomainID`**:

| Byte Offset | Field Name | C-ABI Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x0000` – `0x0001` | `RelationID` | `uint16_t` | 2 Bytes | Zero-indexed relation identifier (`0`..`RelationCount - 1`). |
| `0x0002` – `0x0003` | `SrcDomainID` | `uint16_t` | 2 Bytes | Domain ID of source nodes. |
| `0x0004` – `0x0005` | `TgtDomainID` | `uint16_t` | 2 Bytes | Domain ID of target nodes. |
| `0x0006` | `EncodingID` | `uint8_t` | 1 Byte | Topology encoding enum (`0x00` = `ENCODING_RAW`, `0x01` = `ZSTD`). |
| `0x0007` | `NodeIDWidth` | `uint8_t` | 1 Byte | Byte width of target node IDs (`0x02` = `uint16_t`, `0x04` = `uint32_t`, `0x08` = `uint64_t`). |
| `0x0008` | `EdgeIndexWidth` | `uint8_t` | 1 Byte | Byte width of CSR row offsets (`0x04` = `uint32_t`, `0x08` = `uint64_t`). |
| `0x0009` – `0x000B` | `Reserved1` | `uint8_t[3]` | 3 Bytes | `0x00` alignment padding. |
| `0x000C` – `0x000F` | `NameOffset` | `uint32_t` | 4 Bytes | 0-indexed byte offset into String Table (points to null-terminated string, e.g., `"FOLLOWS\0"`). |
| `0x0010` – `0x0017` | `NodeCount` | `uint64_t` | 8 Bytes | Number of source nodes ($N$) in relation matrix. |
| `0x0018` – `0x001F` | `EdgeCount` | `uint64_t` | 8 Bytes | Total number of directed edges ($E$) in relation matrix. |
| `0x0020` – `0x0027` | `SectionFeatures` | `uint64_t` | 8 Bytes | Per-relation feature bitmask (bit 0 = CSC, bit 1 = weighted, bit 2 = virtual relation, bits 3..4 = multiplicity). |
| `0x0028` – `0x002F` | `CsrRowOffOffset` | `uint64_t` | 8 Bytes | Absolute file offset to `csrRowOffsets` array (128B aligned; `0` if Virtual or `M:1`/`1:1`). |
| `0x0030` – `0x0037` | `CsrRowOffBytes` | `uint64_t` | 8 Bytes | Byte size of `csrRowOffsets` array ($= (N + 1) \times \text{EdgeIndexWidth}$; `0` if Virtual or `M:1`/`1:1`). |
| `0x0038` – `0x003F` | `CsrColIdxOffset` | `uint64_t` | 8 Bytes | Absolute file offset to `csrColumnIndices` array (128B aligned; `0` if Virtual). |
| `0x0040` – `0x0047` | `CsrColIdxBytes` | `uint64_t` | 8 Bytes | Byte size of `csrColumnIndices` array ($= E \times \text{NodeIDWidth}$; `0` if Virtual). |
| `0x0048` – `0x004F` | `CscRowOffOffset` | `uint64_t` | 8 Bytes | Absolute file offset to optional `cscRowOffsets` array (`0` if omitted, Virtual, or `1:M`/`1:1`). |
| `0x0050` – `0x0057` | `CscRowOffBytes` | `uint64_t` | 8 Bytes | Byte size of `cscRowOffsets` array (`0` if omitted, Virtual, or `1:M`/`1:1`). |
| `0x0058` – `0x005F` | `CscColIdxOffset` | `uint64_t` | 8 Bytes | Absolute file offset to optional `cscColumnIndices` array (`0` if omitted or Virtual). |
| `0x0060` – `0x0067` | `CscColIdxBytes` | `uint64_t` | 8 Bytes | Byte size of `cscColumnIndices` array (`0` if omitted or Virtual). |
| `0x0068` – `0x0069` | `AttrCount` | `uint16_t` | 2 Bytes | Number of edge attributes defined for this relation (`0` if Virtual). |

#### 3.3.2 Virtual Super-Relation C-ABI Payload (`Reserved2` Overload & Overflow Rules)

When `IMP_REL_FEATURE_VIRTUAL` (`Bit 2`) is enabled in `SectionFeatures`:

* **Inline Fast Path ($1 \le \text{component\_count} \le 10$)**:
  Bytes `0x006A` – `0x007F` (22 bytes) in the `RelationDirectoryEntry` are overloaded to store the constituent relation payload directly inside the fixed 128-byte entry (zero extra file reads or memory allocations):

```c
struct ImpulseVirtualRelationPayload {
    uint16_t component_count;    // Number of constituent physical relation IDs (1 <= C <= 10)
    uint16_t component_ids[10];  // Inline array of constituent physical RelationIDs (padded with 0x0000)
};
```

* **Overflow Extended Path ($\text{component\_count} > 10$, up to 65,536)**:
  For large virtual relations composed of more than 10 physical relations:

  1. `component_ids[0]` is set to `0xFFFF` (Overflow Sentinel Flag).
  2. `CsrColIdxOffset` (8-byte `uint64_t`) stores a 128B-aligned absolute file offset to an off-heap array of `uint16_t component_ids[component_count]`.
  3. `CsrColIdxBytes` stores the byte size ($= \text{component\_count} \times 2$).
* **Maximum Theoretical Capacity**: Up to **65,536 physical relations** per virtual super-relation (matching the overall `.imps` relation limit).

---

#### 3.3.3 Per-Relation Feature Bitmask (`SectionFeatures` 64-bit Layout)

The `SectionFeatures` field defines C-ABI flags and structural contracts for topology storage:

```c
#define IMP_REL_FEATURE_CSC (1ULL << 0) // Bit 0: CSC Transpose Index Present
#define IMP_REL_FEATURE_WEIGHTED (1ULL << 1) // Bit 1: Edge Weights Present
#define IMP_REL_FEATURE_VIRTUAL (1ULL << 2) // Bit 2: Virtual Super-Relation (No physical arrays on disk)

// Multiplicity Bitmask (Bits 3..4)
#define IMP_REL_CARDINALITY_MASK (3ULL << 3) // Bitmask for relation multiplicity (Bits 3..4)
#define IMP_REL_CARDINALITY_M_N (0ULL << 3) // Many-to-Many (Default full CSR/CSC layout)
#define IMP_REL_CARDINALITY_M_1 (1ULL << 3) // Many-to-One (Flat target array, CsrRowOffBytes = 0)
#define IMP_REL_CARDINALITY_1_M (2ULL << 3) // One-to-Many (Forward CSR, reverse flat CSC array)
#define IMP_REL_CARDINALITY_1_1 (3ULL << 3) // One-to-One (Flat bi-directional direct arrays)
```

---

### 3.4 Attribute Descriptor Structure (Fixed 44 Bytes)

Every node attribute and edge attribute is defined by a fixed 44-byte POD struct:

| Byte Offset | Field Name | C-ABI Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x0000` – `0x0003` | `NameOffset` | `uint32_t` | 4 Bytes | 0-indexed byte offset into String Table (points to null-terminated string, e.g., `"weight\0"`). |
| `0x0004` | `TypeCode` | `uint8_t` | 1 Byte | Base Primitive Type (`Bits 0..6`) + `0x80` Nullability Flag (`Bit 7`). |
| `0x0005` | `Reserved1` | `uint8_t` | 1 Byte | `0x00` alignment padding. |
| `0x0006` – `0x0007` | `Reserved2` | `uint16_t` | 2 Bytes | `0x00` alignment padding. |
| `0x0008` – `0x000B` | `Dimension` | `uint32_t` | 4 Bytes | Element dimension $D$ ($1$ for scalar, $D \ge 1$ for fixed vectors, $0$ for variable-length). |
| `0x000C` – `0x0013` | `DataOffset` | `uint64_t` | 8 Bytes | 128B-aligned absolute file offset to attribute data array / payload blob. |
| `0x0014` – `0x001B` | `DataBytes` | `uint64_t` | 8 Bytes | Total byte size of attribute data array / payload blob. |
| `0x001C` – `0x0023` | `OffsetsOffset` | `uint64_t` | 8 Bytes | 128B-aligned absolute file offset to `uint32_t offsets[]` array (`0` for fixed-width). |
| `0x0024` – `0x002B` | `OffsetsBytes` | `uint64_t` | 8 Bytes | Total byte size of `uint32_t offsets[]` array ($= (K + 1) \times 4$; `0` for fixed-width). |

---

## 4. Topology & Attribute Specification

### 4.1 Topology Mechanics & Multiplicity Optimizations

* **Many-to-Many (`IMP_REL_CARDINALITY_M_N`)**: Topology is standard CSR (`csrRowOffsets` + `csrColumnIndices`). Target $k$ of node $i$ is read at `csrColumnIndices[csrRowOffsets[i] + k]`.
* **Many-to-One (`IMP_REL_CARDINALITY_M_1`)**: Every source node has at most 1 target node. `csrRowOffsets` is omitted (`CsrRowOffBytes = 0`). `csrColumnIndices` becomes a flat direct array of length $N$. Target node ID for source node $i$ is read directly at `csrColumnIndices[i]` (where `MAX_UINT` indicates no edge).
* **One-to-Many (`IMP_REL_CARDINALITY_1_M`)**: Forward CSR is standard (`csrRowOffsets` + `csrColumnIndices`). Reverse CSC transpose omits `cscRowOffsets` (`CscRowOffBytes = 0`), storing a flat direct source node ID array in `cscColumnIndices`.
* **One-to-One (`IMP_REL_CARDINALITY_1_1`)**: Both `csrRowOffsets` and `cscRowOffsets` are omitted. Forward and reverse traversals use flat direct arrays in $O(1)$ single-hop dereferences.
* **Virtual Super-Relations (`IMP_REL_FEATURE_VIRTUAL`)**: Contains no physical topology arrays. `ImpulseVM` resolves the relation by expanding traversals over `component_ids[0 .. component_count - 1]` and unioning intermediate bitsets via `OP_SET_UNION` or `OP_CSC_WALK_MULTI`.
* **Optional CSC Transpose**: An incoming transpose index (`cscRowOffsets` + `cscColumnIndices`) may be included for bidirectional traversals.
* **Explicit Reverse Relations**: Reverse relations (e.g. `MEMBER_OF_REVERSE`) are represented explicitly as first-class catalog relations.

### 4.2 Attribute Storage Architecture (Structure of Arrays)

Attributes are partitioned into fixed-length primitives, fixed-width vectors, and variable-length payloads stored in **Structure of Arrays (SoA)** layout.

#### Bitwise Nullability Flag & Base Type Mask
Attribute data types are encoded in an 8-bit field (`uint8_t type_code`):

```c
#define IMPULSE_TYPE_MASK     0x7F  // Bits 0..6: Base Primitive Type (Up to 128 base types)
#define IMPULSE_NULLABLE_FLAG 0x80  // Bit 7: Nullability Flag (1 = Nullable with Validity Bitmap, 0 = Non-Null)

// Bitwise evaluation in C-ABI parsers
uint8_t base_type   = descriptor->type_code & IMPULSE_TYPE_MASK;
bool is_nullable = (descriptor->type_code & IMPULSE_NULLABLE_FLAG) != 0;
```

* **Non-Nullable (`is_nullable == false`, Bit 7 = 0)**: Zero validity bitmap overhead. 100% of memory is allocated to contiguous data values.
* **Nullable (`is_nullable == true`, Bit 7 = 1)**: A 128-byte aligned **Validity Bitmap** (`uint64_t validity_bitmap[(K + 63) / 64]`) is placed at `DataOffset`. The validity bitmap MUST be strictly padded with `0x00` to the nearest 128-byte boundary. The actual data payload array begins immediately after the padded bitmap, guaranteeing that the data array remains strictly 128-byte aligned for hardware SIMD load instructions. ($1\text{ bit per entity}$, Bit $i=1 \rightarrow$ valid value, Bit $i=0 \rightarrow$ null).

#### Base Data Type Table (`0x00` .. `0x7F` Base Codes):
| Base Code (`0x7F`) | Base Type Name | Non-Null Code | Nullable Code (`0x80`) | Dimension (`dim`) | Memory Layout |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `0x01` | `INT8` | `0x01` | `0x81` | $\ge 1$ | $1 \times \text{dim}$ Bytes (`int8_t` / `uint8_t`) |
| `0x02` | `INT16` | `0x02` | `0x82` | $\ge 1$ | $2 \times \text{dim}$ Bytes (`int16_t` / `uint16_t`) |
| `0x03` | `INT32` | `0x03` | `0x83` | $\ge 1$ | $4 \times \text{dim}$ Bytes (`int32_t` / `uint32_t`) |
| `0x04` | `INT64` | `0x04` | `0x84` | $\ge 1$ | $8 \times \text{dim}$ Bytes (`int64_t` / `uint64_t`) |
| `0x05` | `FLOAT16` | `0x05` | `0x85` | $\ge 1$ | $2 \times \text{dim}$ Bytes (bfloat16 / fp16) |
| `0x06` | `FLOAT32` | `0x06` | `0x86` | $\ge 1$ | $4 \times \text{dim}$ Bytes (IEEE 754 float, **edge weights**) |
| `0x07` | `FLOAT64` | `0x07` | `0x87` | $\ge 1$ | $8 \times \text{dim}$ Bytes (IEEE 754 double, high precision) |
| `0x08` | `TIMESTAMP_MS` | `0x08` | `0x88` | $\ge 1$ | $8 \times \text{dim}$ Bytes (uint64 epoch ms) |
| `0x09` | `TIMESTAMP_NS` | `0x09` | `0x89` | $\ge 1$ | $8 \times \text{dim}$ Bytes (uint64 epoch ns) |
| `0x0A` | `FIXED_BYTES` | `0x0A` | `0x8A` | $\ge 1$ | $\text{dim}$ Bytes (dim=16 for UUID, dim=32 for SHA-256) |
| `0x0B` | `VAR_STRING` | `0x0B` | `0x8B` | Ignored (`0`) | Variable UTF-8 (`uint32_t offsets[]` + Data Blob) |
| `0x0C` | `VAR_BYTES` | `0x0C` | `0x8C` | Ignored (`0`) | Variable Binary (`uint32_t offsets[]` + Data Blob) |
| `0x0D` | `INTERVAL_SEC_32` | `0x0D` | `0x8D` | $\ge 1$ | 8 Bytes packed struct (`uint32_t start_sec`, `uint32_t duration_sec`) |
| `0x0E` | `INTERVAL_MS_64` | `0x0E` | `0x8E` | $\ge 1$ | 16 Bytes packed struct (`uint64_t start_ms`, `uint64_t duration_ms`) |

---

### 3.4 Section 2.6: Secondary Index Directory Table (Fixed 64 Bytes per Index)
Begins immediately after Relation Directory Table, aligned to a 128-byte boundary. Contains `IndexCount` generic secondary index descriptors:

| Byte Offset | Field Name | C-ABI Type | Size | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x0000` – `0x0003` | `IndexID` | `uint32_t` | 4 Bytes | Zero-indexed secondary index identifier (`0`..`IndexCount - 1`). |
| `0x0004` – `0x0005` | `DomainID` | `uint16_t` | 2 Bytes | Target Node Domain ID. |
| `0x0006` – `0x0007` | `RelationID` | `uint16_t` | 2 Bytes | Target Relation ID (`0xFFFF` for Node Domain attributes). |
| `0x0008` – `0x0009` | `AttributeIndex` | `uint16_t` | 2 Bytes | 0-indexed Attribute index within target relation or node domain. |
| `0x000A` | `IndexType` | `uint8_t` | 1 Byte | Generic Index Type enum (`0x01` = Permutation, `0x02` = ZoneMap, `0x03` = InvertedBitSet, `0x04` = MPHF, `0x05` = Trigram, `0x06` = DomainSplit, `0x07` = TemporalInterval). |
| `0x000B` | `Reserved1` | `uint8_t` | 1 Byte | `0x00` alignment padding. |
| `0x000C` – `0x000F` | `NameOffset` | `uint32_t` | 4 Bytes | 0-indexed byte offset into String Table (e.g., `"idx_user_email\0"`). |
| `0x0010` – `0x0017` | `DataOffset` | `uint64_t` | 8 Bytes | Absolute 128B-aligned file offset to index data payload blob. |
| `0x0018` – `0x001F` | `DataBytes` | `uint64_t` | 8 Bytes | Total byte size of index data payload blob. |
| `0x0020` – `0x0027` | `PayloadFeatureMask` | `uint64_t` | 8 Bytes | Generic Index Feature Bitmask (e.g. hash seed, metric flags). |
| `0x0028` – `0x003F` | `ReservedPadding` | `uint8_t[24]` | 24 Bytes | Reserved for future index engine parameters (`0x00`). |

---

### 4.4 Optional Snapshot Topology & Topology Inspection Opcodes (`0x19` .. `0x1C`)

In accordance with the Impulse Graph Engine physical snapshot format specification, **all structural topology representations (CSR, CSC, COO) and Key Catalogs are fully optional**:

* **CSR (Forward Out-Edges $u \to v$)**: Optional. Opcodes `OP_CSR_*` fail-fast with `IMPULSE_VM_ERR_NULL_SNAPSHOT` if absent.
* **CSC (Reverse In-Edges $v \leftarrow u$)**: Optional. Opcodes `OP_CSC_*` fail-fast with `IMPULSE_VM_ERR_NULL_SNAPSHOT` if absent.
* **COO (Coordinate Edge List $[E, 2]$)**: Optional. Opcodes `OP_COO_*` fail-fast with `IMPULSE_VM_ERR_NULL_SNAPSHOT` if absent.
* **Key Catalogs (Dense Node ID $\leftrightarrow$ String Key / UUID)**: Optional. Opcodes `OP_MAP_KEYS_TO_DENSE` fail-fast if absent.

To enable dynamic adaptive query execution without runtime exception traps, `ImpulseVM` provides 4 dedicated **Topology Inspection Opcodes**:

| Opcode ID | Instruction Signature | Description | Result & Flags |
| :--- | :--- | :--- | :--- |
| **`0x19`** | **`OP_HAS_CSR R_DST, REL_ID`** | Inspects if relation `REL_ID` has CSR forward offsets installed | `R_DST = 1` if present, `0` if absent.<br>Sets `ZF = 0` (present) or `ZF = 1` (absent). |
| **`0x1A`** | **`OP_HAS_CSC R_DST, REL_ID`** | Inspects if relation `REL_ID` has CSC reverse offsets installed | `R_DST = 1` if present, `0` if absent.<br>Sets `ZF = 0` (present) or `ZF = 1` (absent). |
| **`0x1B`** | **`OP_HAS_COO R_DST, REL_ID`** | Inspects if relation `REL_ID` has COO edge list installed | `R_DST = 1` if present, `0` if absent.<br>Sets `ZF = 0` (present) or `ZF = 1` (absent). |
| **`0x1C`** | **`OP_HAS_KEY_CATALOG R_DST, DOMAIN_ID`** | Inspects if domain `DOMAIN_ID` has String/UUID key catalog installed | `R_DST = 1` if present, `0` if absent.<br>Sets `ZF = 0` (present) or `ZF = 1` (absent). |
| **`0x1D`** | **`OP_DENSE_WALK R_DST, R_SRC, REL_ID`** | Dense bitmask grid matrix traversal | Traverses `ENCODING_DENSE` bitmask grid relation. |
| **`0x1E`** | **`OP_CREATE_SCRATCH_INDEX DOMAIN, ATTR, TYPE`** | Idempotently creates secondary index in transient scratch memory | Builds scratch index in RAM / `.imps.idx` sidecar if absent. |
| **`0x1F`** | **`OP_DROP_SCRATCH_INDEX DOMAIN, ATTR, TYPE`** | Idempotently drops secondary index from transient scratch memory | Frees transient scratch index. |
| **`0x20`** | **`OP_HAS_DENSE R_DST, REL_ID`** | Inspects if relation `REL_ID` is encoded as a `ENCODING_DENSE` bitmask grid | `R_DST = 1` if present, `0` if absent.<br>Sets `ZF = 0` (present) or `ZF = 1` (absent). |

---

### 4.3 Detailed Physical Storage Rules for Attributes

Attribute storage layout depends on whether the attribute is fixed-width (scalar / vector) or variable-length.

#### 1. Fixed-Width Primitives & Vector Attributes ($D \ge 1$)
* **Location**: Edge attributes sit in the **Relation Block** immediately following topology arrays; Node attributes sit in **Node Domain Blocks**.
* **Offset & Alignment**: Data array begins at absolute file offset `DataOffset`, aligned to a 128-byte boundary.
* **Element Indexing**: Element $i$ ($0 \le i < K$, where $K = E$ for edges or $K = N$ for nodes) starts at byte offset:
  $$\text{ByteOffset}(i) = \text{DataOffset} + (i \times D \times \text{sizeof(BaseType)})$$

#### 2. Variable-Length String & Binary Attributes (`VAR_STRING` 0x0B, `VAR_BYTES` 0x0C)
* **Offsets Array**: Stored at 128B-aligned `OffsetsOffset` containing an array of $K + 1$ 32-bit unsigned integers (`uint32_t offsets[K + 1]`), where `offsets[0] = 0`.
* **Data Payload Blob**: Stored at 128B-aligned `DataOffset` containing the raw concatenated UTF-8 text or binary bytes.
* **Slice Extraction**: Payload bytes for element $i$ are extracted from `DataOffset + offsets[i]` with byte length `offsets[i + 1] - offsets[i]`.
---

## 5. Section 4: Key Catalogs & ID Mappings

Section 4 stores the off-heap index structures required to resolve external business keys (Strings, UUIDs, Integers) to internal dense `0` to `N-1` Node IDs, and vice-versa. 

In accordance with the physical specification, $O(N)$ linear scans or heap allocations for key resolution are prohibited. All mappings MUST be performed in $O(1)$ or $O(\log N)$ using 128-byte aligned zero-copy memory mapped structures.

### 6.1 Dense ID to Key Resolution ($O(1)$ Array Lookup)
The forward mapping (Dense ID $\to$ External Key) is implemented natively by storing the keys as a standard **Node Domain Attribute** (often implicitly named `_key` or identified via `IndexType = 0xFFFF`).

- For fixed-width keys (e.g. `INT64`), the dense ID is simply used to directly index the 128B-aligned `data_ptr` array ($O(1)$ lookup).
- For variable-length keys (e.g. `VAR_STRING`, `UUID128`), the dense ID indexes the `offsets_ptr` array to locate the slice within the `data_ptr` blob ($O(1)$ lookup).

### 6.2 Key to Dense ID Resolution ($O(1) / O(\log N)$ Reverse Index)
The reverse mapping (External Key $\to$ Dense ID) requires a **Secondary Index Directory Entry** targeting the Node Domain. 

The structural format of the Section 4 index block depends on the `key_type` defined in the Domain Catalog:

* **Variable Length Strings & UUIDs (`VAR_STRING`, `UUID128`)**:
  - Requires **IndexType `0x04` (IMP_INDEX_MINIMAL_PERFECT_HASH)**. 
  - Resolves string keys to dense IDs in $O(1)$ time with $\approx 2-3$ bits/key overhead.
* **Fixed-Width Integers (`INT32`, `INT64`)**:
  - Requires **IndexType `0x01` (IMP_INDEX_PERMUTATION)** or a direct sorted array.
  - Resolves integer keys to dense IDs in $O(\log N)$ time via binary search.

---

## 6. Footer Block & S3 Streaming Upload Specification

### 6.1 Single-Pass S3 Ingestion
For unseekable S3 multi-part uploads, signatures, SHA-256 digests, and catalog directories are serialized into the **Footer Block at EOF**.

### 6.2 16-Byte Footer Trailer Specification
Every compliant snapshot MUST terminate with exactly 16 bytes at EOF:

```c
typedef struct impulse_footer_trailer {
    uint64_t footer_length;    // 8 Bytes: Byte size of Footer Block
    uint32_t spec_version;     // 4 Bytes: Protocol version (0x0009)
    uint32_t footer_magic;     // 4 Bytes: "IMPS" (0x494D5053)
} impulse_footer_trailer_t;     // Exactly 16 Bytes at EOF
```

---

## 7. Hardware Alignment & C-ABI Macros

```c
// 128-Byte Alignment for AVX-512 SIMD & GPU Warp Coalescing
#define IMPULSE_ALIGN_128(offset) (((offset) + 127ULL) & ~127ULL)

// 4KB Page Alignment for OS Virtual Memory Area (VMA) Isolation
#define IMPULSE_ALIGN_4K(offset) (((offset) + 4095ULL) & ~4095ULL)
```

