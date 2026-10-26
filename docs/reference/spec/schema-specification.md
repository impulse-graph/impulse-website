# Schema & Manifest Specification (`.imps.schema.yaml`)

This document defines the declarative YAML/JSON schema and multi-tablespace manifest format (`.imps.schema.yaml` / `manifest.yaml`) used across the Impulse Graph Engine ecosystem.

A schema file serves four roles:

1. **Snapshot Compilation (`impulse snapshot build` & `SnapshotBuilder`)**: Configures per-domain integer widths (`uint16`, `uint32`, `uint64`), key catalogs, CSR/CSC indices, relation multiplicities, and 128-byte-aligned Structure-of-Arrays (SoA) attributes.
2. **Compile-Time Query Validation**: Verifies domain names, relation endpoints (`SrcDomainID` $\to$ `TgtDomainID`), and attribute types before emitting `impOps` bytecode.
3. **Code Generation (`impulse-codegen`, Maven/Gradle plugins)**: Generates strongly-typed domain views and POJOs.
4. **Multi-Tablespace Composite Loading**: Maps logical domains and relations across multiple `.imps` files (supported in the Java 25 engine via `BinarySnapshotLoader.loadFromManifest(Path manifestPath, Arena arena)`, while C-ABI `impulse_snapshot_open` maps single `.imps` files directly and multi-snapshot federated C-ABI queries are targeted for post-`v1.0`).

---

## 1. Complete Schema Example

```yaml
graphName: "EnterpriseKnowledgeGraph"

tablespaces:
  core_identity:
    file: "chunks/core_identity.imps"
  commerce_events:
    file: "chunks/commerce_events.imps"

domains:
  User:
    tablespace: core_identity
    denseId: uint32            # 0..N_d-1 addressing width (uint16 | uint32 | uint64)
    key: uuid                  # External primary key type (int32 | int64 | uuid | string | bytes)
    attributes:
      account_status: { type: "FixedString(8)", nullable: false }
      display_name:   { type: "VarString",      nullable: false }
      embedding:      { type: "Float32",        dimension: 128 }

  Product:
    tablespace: core_identity
    denseId: uint32
    key: string
    attributes:
      price:          { type: "Float32",        nullable: false }
      category_code:  { type: "Int16",          nullable: true }

relations:
  PURCHASED:
    source: User
    target: Product
    tablespace: commerce_events
    direction: [out, in]       # Generates both CSR (forward) and CSC (reverse)
    cardinality: many_to_many  # many_to_many | many_to_one | one_to_many | one_to_one
    attributes:
      timestamp: { type: "TimestampMs" }
      amount:    { type: "Float32" }

virtual_relations:
  ENGAGED_WITH:
    components:
      - PURCHASED
      - VIEWED
      - WISHLISTED
```

---

## 2. Node Domains (`domains`)

Every Node Domain owns an **independent 0-indexed dense integer space $0 \dots N_d-1$**. Dense ID `0` in `User` is distinct from Dense ID `0` in `Product`.

| Property | Allowed Values | Description |
| :--- | :--- | :--- |
| **`denseId` / `idWidth`** | `uint16`, `uint32` *(default)*, `uint64` | Physical integer width used to store dense node IDs for this domain (`uint16`: up to `65,536` nodes; `uint32`: up to `4,294,967,296` nodes; `uint64`: up to $1.84 \times 10^{19}$ nodes). |
| **`key`** | `int32`, `int64`, `uuid`, `string`, `bytes` | External business identifier format indexed in Section 4 (MPHF for `string`/`uuid`; sorted array for integers). |
| **`tablespace`** | `<tablespace_name>` *(optional)* | Physical `.imps` chunk file hosting this domain in multi-file deployments. |
| **`attributes`** | Map of attribute definitions | Contiguous 128-byte-aligned SoA columns attached to nodes in this domain. |

---

## 3. Edge Relations (`relations`) & Multiplicity Layouts

Every directed relation explicitly binds a `source` domain and `target` domain:

| Property | Allowed Values | Physical Storage & Optimizer Impact |
| :--- | :--- | :--- |
| **`source` / `target`** | Domain names | Maps source dense IDs ($0 \dots N_{\text{src}}-1$) to target dense IDs ($0 \dots N_{\text{tgt}}-1$). |
| **`direction`** | `[out]`, `[in]`, `[out, in]` | `out` builds forward **CSR**; `in` builds reverse **CSC** transpose. |
| **`cardinality`** | `many_to_many` *(default)*<br>`many_to_one`<br>`one_to_many`<br>`one_to_one` | - **`many_to_many` (`M:N`)**: Standard CSR/CSC (`row_offsets` + `col_indices`).<br>- **`many_to_one` (`M:1`)**: Omits `csrRowOffsets`; stores flat target array `col_indices[N]` ($O(1)$ lookup, no deduplication needed).<br>- **`one_to_many` (`1:M`)**: Forward CSR; reverse CSC omits offsets.<br>- **`one_to_one` (`1:1`)**: Bi-directional flat direct arrays ($O(1)$ lookup). |
| **`virtual_relations`** | List of `1..65,536` physical relations | Zero-storage super-relation; expands across constituent relations and unions bitsets at query time. |

---

## 4. Attribute Data Types & Physical Limits

| Schema Type | C-ABI Code | Element Size | Physical Storage & Maximum Limits |
| :--- | :--- | :--- | :--- |
| **`Int8` / `UInt8` / `Bool`** | `0x01` | $1 \times D$ bytes | Contiguous 128B-aligned array |
| **`Int16` / `UInt16` / `Float16`** | `0x02` / `0x05` | $2 \times D$ bytes | Contiguous 128B-aligned array |
| **`Int32` / `UInt32` / `Float32`** | `0x03` / `0x06` | $4 \times D$ bytes | Contiguous 128B-aligned array |
| **`Int64` / `UInt64` / `Float64`** | `0x04` / `0x07` | $8 \times D$ bytes | Contiguous 128B-aligned array |
| **`TimestampMs` / `TimestampNs`** | `0x08` / `0x09` | $8 \times D$ bytes | 64-bit Unix epoch timestamp |
| **`FixedString(D)` / `FixedBytes(D)`**| `0x0A` | $D$ bytes | Fixed-stride array ($D = 16$ for UUID; max $D = 2^{32}-1$) |
| **`VarString` / `VarBytes`** | `0x0B` / `0x0C` | Variable | `uint32_t offsets[K+1]` + payload blob (up to **4 GB** per column) |

* **Nullable Columns (`nullable: true`)**: Prepends a 128-byte-aligned Arrow-compatible validity bitmap (`1` = valid, `0` = null) before the data array; non-nullable columns (`nullable: false`) have **0 bits** of bitmap overhead.

---

## 5. Schema Evolution Rules: Name is Identity

In Impulse Graph, the **String Name** of a domain, relation, or attribute (stored in the Section 2 Shared String Table) is the semantic contract; the numeric `DomainID` or `RelationID` (`0..65,535`) is an internal per-snapshot detail resolved when a query is prepared or rebound.

| Schema Change Across Snapshot Rebuilds | Impact on Queries | Safe? |
| :--- | :--- | :--- |
| **Add a new domain, relation, or attribute** | Ignored by existing queries | ✅ **Safe** |
| **Add/remove nodes or edges** | Handled automatically via catalog cardinalities | ✅ **Safe** |
| **Reorder `RelationID` or apply RCM node reordering** | Resolved by name during `prepare` / `rebind` | ✅ **Safe** |
| **Rename or delete a referenced relation/attribute** | Fails fast at query `prepare` time | ❌ **Breaking** |
| **Change a relation's `source` or `target` domain** | Fails domain type-check at `prepare` time | ❌ **Breaking** |
